"""
Synapse SQLite Database Layer.

Manages the derived graph projection stored in SQLite.
Tables: entities, tags, refs, mission_memory, entities_fts (FTS5).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from realize_core.fabric.entity import FabricEntity

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
-- Core entity index (L1)
CREATE TABLE IF NOT EXISTS entities (
    id           TEXT PRIMARY KEY,
    type         TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL DEFAULT '',
    slug         TEXT NOT NULL DEFAULT '',
    venture      TEXT NOT NULL DEFAULT '',
    path         TEXT NOT NULL DEFAULT '',
    summary      TEXT NOT NULL DEFAULT '',
    layer        TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL DEFAULT 'manual',
    created_by   TEXT NOT NULL DEFAULT '',
    confidence   REAL NOT NULL DEFAULT 1.0,
    verified     INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    last_updated TEXT NOT NULL DEFAULT '',
    refs_json    TEXT NOT NULL DEFAULT '[]',
    tags_json    TEXT NOT NULL DEFAULT '[]',
    frontmatter_json TEXT NOT NULL DEFAULT '{}'
);

-- Tags (many-to-many)
CREATE TABLE IF NOT EXISTS tags (
    entity_id TEXT NOT NULL,
    tag       TEXT NOT NULL,
    source    TEXT NOT NULL DEFAULT 'frontmatter',
    PRIMARY KEY (entity_id, tag)
);

-- References (directed graph edges)
CREATE TABLE IF NOT EXISTS refs (
    from_entity TEXT NOT NULL,
    to_entity   TEXT NOT NULL,
    ref_type    TEXT NOT NULL DEFAULT 'wikilink',
    source_path TEXT NOT NULL DEFAULT '',
    context     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (from_entity, to_entity)
);

-- Mission memory (L4)
CREATE TABLE IF NOT EXISTS mission_memory (
    mission_id   TEXT PRIMARY KEY,
    summary      TEXT NOT NULL DEFAULT '',
    decisions    TEXT NOT NULL DEFAULT '[]',
    blockers     TEXT NOT NULL DEFAULT '[]',
    last_updated TEXT NOT NULL DEFAULT ''
);

-- FTS5 for full-text search (L2) — standalone table
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    id, title, summary, body, venture, type,
    tokenize='porter unicode61'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_entities_venture ON entities(venture);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_refs_to ON refs(to_entity);
"""


class SynapseDB:
    """SQLite database for the Synapse knowledge index."""

    def __init__(self, db_path: Path | str = "synapse.db"):
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self) -> None:
        """Create tables if they don't exist."""
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ─── Entity CRUD ──────────────────────────────────────────────────

    def upsert_entity(self, entity: FabricEntity) -> None:
        """Insert or update an entity in the index."""
        now = datetime.now().isoformat()

        # Build a summary from body (first 200 chars)
        summary = entity.body[:200].strip().replace("\n", " ")
        if len(entity.body) > 200:
            summary += "…"

        self._conn.execute(
            """INSERT OR REPLACE INTO entities
               (id, type, title, slug, venture, path, summary, layer,
                source, created_by, confidence, verified, content_hash,
                last_updated, refs_json, tags_json, frontmatter_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entity.id or entity.slug or str(entity.path),
                entity.type,
                entity.title,
                entity.slug,
                entity.venture,
                str(entity.path or ""),
                summary,
                entity.fabric_layer,
                entity.source,
                entity.created_by,
                entity.confidence,
                1 if entity.verified else 0,
                entity.content_hash,
                now,
                json.dumps(entity.refs),
                json.dumps(entity.tags),
                json.dumps(entity.frontmatter, default=str),
            ),
        )

        # Update tags table
        entity_key = entity.id or entity.slug
        self._conn.execute("DELETE FROM tags WHERE entity_id = ?", (entity_key,))
        for tag in entity.tags:
            self._conn.execute(
                "INSERT OR IGNORE INTO tags (entity_id, tag, source) VALUES (?, ?, ?)",
                (entity_key, tag, "frontmatter"),
            )

        # Update refs table
        self._conn.execute("DELETE FROM refs WHERE from_entity = ?", (entity_key,))
        for ref in entity.refs:
            self._conn.execute(
                "INSERT OR IGNORE INTO refs (from_entity, to_entity, ref_type, source_path) VALUES (?, ?, ?, ?)",
                (entity_key, ref, "auto", str(entity.path or "")),
            )

        # Update FTS — delete old entry first, then insert
        try:
            self._conn.execute(
                "DELETE FROM entities_fts WHERE id = ?",
                (entity_key,),
            )
            self._conn.execute(
                "INSERT INTO entities_fts (id, title, summary, body, venture, type) VALUES (?, ?, ?, ?, ?, ?)",
                (entity_key, entity.title, summary, entity.body[:2000], entity.venture, entity.type),
            )
        except sqlite3.OperationalError:
            pass  # FTS may not be available

        self._conn.commit()

    def delete_entity(self, entity_id: str) -> None:
        """Remove an entity from the index."""
        self._conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        self._conn.execute("DELETE FROM tags WHERE entity_id = ?", (entity_id,))
        self._conn.execute("DELETE FROM refs WHERE from_entity = ?", (entity_id,))
        self._conn.execute("DELETE FROM refs WHERE to_entity = ?", (entity_id,))
        self._conn.commit()

    def clear_venture(self, venture: str) -> None:
        """Remove all entities for a venture."""
        # Get entity IDs first
        rows = self._conn.execute(
            "SELECT id FROM entities WHERE venture = ?", (venture,)
        ).fetchall()
        ids = [row["id"] for row in rows]

        if ids:
            placeholders = ",".join("?" * len(ids))
            self._conn.execute(f"DELETE FROM tags WHERE entity_id IN ({placeholders})", ids)
            self._conn.execute(f"DELETE FROM refs WHERE from_entity IN ({placeholders})", ids)
            self._conn.execute(f"DELETE FROM refs WHERE to_entity IN ({placeholders})", ids)
            # Clean FTS entries
            try:
                self._conn.execute(f"DELETE FROM entities_fts WHERE id IN ({placeholders})", ids)
            except sqlite3.OperationalError:
                pass
            self._conn.execute("DELETE FROM entities WHERE venture = ?", (venture,))

        self._conn.commit()

    # ─── L1: TOC Queries ──────────────────────────────────────────────

    def get_toc(self, venture: str | None = None) -> list[dict]:
        """Get L1 Table of Contents."""
        if venture:
            rows = self._conn.execute(
                "SELECT id, type, title, slug, venture, layer, tags_json, refs_json, source, confidence, verified "
                "FROM entities WHERE venture = ? ORDER BY type, title",
                (venture,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, type, title, slug, venture, layer, tags_json, refs_json, source, confidence, verified "
                "FROM entities ORDER BY venture, type, title"
            ).fetchall()

        return [
            {
                "id": r["id"],
                "type": r["type"],
                "title": r["title"],
                "slug": r["slug"],
                "venture": r["venture"],
                "layer": r["layer"],
                "tags": json.loads(r["tags_json"]),
                "refs": json.loads(r["refs_json"]),
                "source": r["source"],
                "confidence": r["confidence"],
                "verified": bool(r["verified"]),
            }
            for r in rows
        ]

    def get_entity(self, entity_id: str) -> dict | None:
        """Get a single entity by ID."""
        row = self._conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    # ─── L2: Search ───────────────────────────────────────────────────

    def fts_search(
        self,
        query: str,
        scope: str | None = None,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Full-text search using FTS5."""
        try:
            if scope and entity_type:
                rows = self._conn.execute(
                    "SELECT id, title, summary, venture, type, rank "
                    "FROM entities_fts WHERE entities_fts MATCH ? AND venture = ? AND type = ? "
                    "ORDER BY rank LIMIT ?",
                    (query, scope, entity_type, limit),
                ).fetchall()
            elif scope:
                rows = self._conn.execute(
                    "SELECT id, title, summary, venture, type, rank "
                    "FROM entities_fts WHERE entities_fts MATCH ? AND venture = ? "
                    "ORDER BY rank LIMIT ?",
                    (query, scope, limit),
                ).fetchall()
            elif entity_type:
                rows = self._conn.execute(
                    "SELECT id, title, summary, venture, type, rank "
                    "FROM entities_fts WHERE entities_fts MATCH ? AND type = ? "
                    "ORDER BY rank LIMIT ?",
                    (query, entity_type, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id, title, summary, venture, type, rank "
                    "FROM entities_fts WHERE entities_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (query, limit),
                ).fetchall()

            return [dict(r) for r in rows]
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS search failed: {e}")
            return []

    # ─── Graph Queries ────────────────────────────────────────────────

    def get_neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        types: list[str] | None = None,
    ) -> list[dict]:
        """Get entities connected via references."""
        visited = set()
        result = []
        self._walk_neighbors(entity_id, depth, types, visited, result)
        return result

    def _walk_neighbors(
        self,
        entity_id: str,
        depth: int,
        types: list[str] | None,
        visited: set,
        result: list,
    ) -> None:
        if depth <= 0 or entity_id in visited:
            return
        visited.add(entity_id)

        # Outbound refs
        outbound = self._conn.execute(
            "SELECT to_entity FROM refs WHERE from_entity = ?", (entity_id,)
        ).fetchall()

        # Inbound refs
        inbound = self._conn.execute(
            "SELECT from_entity FROM refs WHERE to_entity = ?", (entity_id,)
        ).fetchall()

        neighbor_ids = {r[0] for r in outbound} | {r[0] for r in inbound}

        for nid in neighbor_ids:
            if nid in visited:
                continue
            entity = self.get_entity(nid)
            if entity is None:
                continue
            if types and entity["type"] not in types:
                continue
            result.append(entity)
            if depth > 1:
                self._walk_neighbors(nid, depth - 1, types, visited, result)

    def get_by_type(self, entity_type: str, scope: str | None = None) -> list[dict]:
        """Get all entities of a given type."""
        if scope:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE type = ? AND venture = ? ORDER BY title",
                (entity_type, scope),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE type = ? ORDER BY venture, title",
                (entity_type,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_tag(self, tag: str, scope: str | None = None) -> list[dict]:
        """Get all entities with a given tag."""
        if scope:
            rows = self._conn.execute(
                "SELECT e.* FROM entities e JOIN tags t ON e.id = t.entity_id "
                "WHERE t.tag = ? AND e.venture = ? ORDER BY e.title",
                (tag, scope),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT e.* FROM entities e JOIN tags t ON e.id = t.entity_id "
                "WHERE t.tag = ? ORDER BY e.venture, e.title",
                (tag,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_recent(self, scope: str | None = None, limit: int = 10) -> list[dict]:
        """Get recently updated entities."""
        if scope:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE venture = ? ORDER BY last_updated DESC LIMIT ?",
                (scope, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM entities ORDER BY last_updated DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_orphans(self, scope: str | None = None) -> list[dict]:
        """Get entities with zero inbound references."""
        if scope:
            rows = self._conn.execute(
                "SELECT e.* FROM entities e "
                "LEFT JOIN refs r ON e.id = r.to_entity "
                "WHERE r.to_entity IS NULL AND e.venture = ? "
                "ORDER BY e.title",
                (scope,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT e.* FROM entities e "
                "LEFT JOIN refs r ON e.id = r.to_entity "
                "WHERE r.to_entity IS NULL "
                "ORDER BY e.venture, e.title"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ─── L4: Mission Memory ───────────────────────────────────────────

    def get_mission_memory(self, mission_id: str) -> dict | None:
        """Get mission memory entry."""
        row = self._conn.execute(
            "SELECT * FROM mission_memory WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "mission_id": row["mission_id"],
            "summary": row["summary"],
            "decisions": json.loads(row["decisions"]),
            "blockers": json.loads(row["blockers"]),
            "last_updated": row["last_updated"],
        }

    def upsert_mission_memory(
        self,
        mission_id: str,
        summary: str,
        decisions: list[str],
        blockers: list[str],
    ) -> None:
        """Insert or update mission memory."""
        now = datetime.now().isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO mission_memory
               (mission_id, summary, decisions, blockers, last_updated)
               VALUES (?, ?, ?, ?, ?)""",
            (mission_id, summary, json.dumps(decisions), json.dumps(blockers), now),
        )
        self._conn.commit()

    # ─── Stats ────────────────────────────────────────────────────────

    def get_stats(self, venture: str | None = None) -> dict:
        """Get index statistics."""
        if venture:
            entity_count = self._conn.execute(
                "SELECT COUNT(*) FROM entities WHERE venture = ?", (venture,)
            ).fetchone()[0]
            tag_count = self._conn.execute(
                "SELECT COUNT(DISTINCT tag) FROM tags t JOIN entities e ON t.entity_id = e.id WHERE e.venture = ?",
                (venture,),
            ).fetchone()[0]
            ref_count = self._conn.execute(
                "SELECT COUNT(*) FROM refs r JOIN entities e ON r.from_entity = e.id WHERE e.venture = ?",
                (venture,),
            ).fetchone()[0]
        else:
            entity_count = self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            tag_count = self._conn.execute("SELECT COUNT(DISTINCT tag) FROM tags").fetchone()[0]
            ref_count = self._conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]

        type_counts = {}
        rows = self._conn.execute(
            "SELECT type, COUNT(*) as cnt FROM entities " +
            ("WHERE venture = ? " if venture else "") +
            "GROUP BY type ORDER BY cnt DESC",
            (venture,) if venture else (),
        ).fetchall()
        for row in rows:
            type_counts[row["type"]] = row["cnt"]

        return {
            "entity_count": entity_count,
            "tag_count": tag_count,
            "ref_count": ref_count,
            "type_counts": type_counts,
        }

    # ─── Helpers ──────────────────────────────────────────────────────

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a sqlite3.Row to a regular dict."""
        d = dict(row)
        # Parse JSON fields
        for json_field in ("tags_json", "refs_json", "frontmatter_json"):
            if json_field in d:
                try:
                    d[json_field.replace("_json", "")] = json.loads(d.pop(json_field))
                except (json.JSONDecodeError, TypeError):
                    d[json_field.replace("_json", "")] = []
        d["verified"] = bool(d.get("verified", 0))
        return d
