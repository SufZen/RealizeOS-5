"""
Synapse — Multi-Tier Knowledge & Tool Indexing.

The connective tissue between FABRIC (durable knowledge) and agents (consumers).
Pre-computed, hierarchically-summarized, semantically-indexed projection
optimized for low-token, high-recall agent consumption.

Four tiers:
  L1 — Hot TOC: every entity id, type, title, summary, tags, refs (~5-10K tokens/venture)
  L2 — Hybrid Search: FTS5 + optional embeddings (BM25 + cosine)
  L3 — Tool Catalog: tools/skills ranked for context
  L4 — Mission Memory: per-mission compressed state
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from realize_core.fabric.synapse_db import SynapseDB
from realize_core.fabric.crud import scan_venture
from realize_core.fabric.entity import FabricEntity

logger = logging.getLogger(__name__)


class Synapse:
    """
    Agent-facing knowledge index built from FABRIC.

    All data is derived from markdown files on disk. Blow away the SQLite
    database → rebuild from FABRIC. No separate truth source.
    """

    def __init__(self, db_path: Path | str = "synapse.db"):
        self.db = SynapseDB(db_path)

    def close(self) -> None:
        """Close the database connection."""
        self.db.close()

    # ─── Indexing ──────────────────────────────────────────────────────

    def index_venture(self, venture_dir: Path, venture: str = "") -> int:
        """
        Full reindex of a venture: scan all markdown files, populate L1 + L2.

        Returns number of entities indexed.
        """
        venture = venture or venture_dir.name
        entities = scan_venture(venture_dir, venture=venture)

        # Clear existing data for this venture
        self.db.clear_venture(venture)

        for entity in entities:
            self.db.upsert_entity(entity)

        logger.info(f"Indexed venture '{venture}': {len(entities)} entities")
        return len(entities)

    def index_entity(self, entity: FabricEntity) -> None:
        """Index or re-index a single entity."""
        self.db.upsert_entity(entity)

    def remove_entity(self, entity_id: str) -> None:
        """Remove a single entity from the index."""
        self.db.delete_entity(entity_id)

    # ─── L1: Hot TOC ──────────────────────────────────────────────────

    def toc(self, venture: str | None = None) -> list[dict]:
        """
        Get the L1 Table of Contents.

        Returns a list of summary dicts for all entities in scope.
        This is always loaded into agent context — the key design move
        that eliminates ~80% of unnecessary RAG retrievals.
        """
        return self.db.get_toc(venture=venture)

    # ─── L2: Hybrid Search ────────────────────────────────────────────

    def search(
        self,
        query: str,
        scope: str | None = None,
        entity_type: str | None = None,
        n: int = 10,
    ) -> list[dict]:
        """
        Hybrid search across entities using FTS5 (BM25).

        Args:
            query: Search query text.
            scope: Venture key to limit search scope.
            entity_type: Filter by entity type.
            n: Max results.

        Returns:
            Ranked list of matching entity summaries.
        """
        return self.db.fts_search(query, scope=scope, entity_type=entity_type, limit=n)

    # ─── Graph Queries ────────────────────────────────────────────────

    def get(self, entity_id: str, depth: int = 0) -> dict | None:
        """
        Get a single entity by ID, optionally with neighbors.

        Args:
            entity_id: The entity ID to look up.
            depth: How many levels of neighbors to include (0 = entity only).

        Returns:
            Entity dict with optional 'neighbors' field, or None.
        """
        entity = self.db.get_entity(entity_id)
        if entity is None:
            return None

        if depth > 0:
            entity["neighbors"] = self.neighbors(entity_id, depth=depth)

        return entity

    def neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        types: list[str] | None = None,
    ) -> list[dict]:
        """Get entities connected to this one via references."""
        return self.db.get_neighbors(entity_id, depth=depth, types=types)

    def by_type(
        self,
        entity_type: str,
        scope: str | None = None,
    ) -> list[dict]:
        """Get all entities of a given type."""
        return self.db.get_by_type(entity_type, scope=scope)

    def by_tag(
        self,
        tag: str,
        scope: str | None = None,
    ) -> list[dict]:
        """Get all entities with a given tag."""
        return self.db.get_by_tag(tag, scope=scope)

    def recent(
        self,
        scope: str | None = None,
        n: int = 10,
    ) -> list[dict]:
        """Get recently modified entities."""
        return self.db.get_recent(scope=scope, limit=n)

    def orphans(self, scope: str | None = None) -> list[dict]:
        """Get entities with zero inbound references."""
        return self.db.get_orphans(scope=scope)

    # ─── L4: Mission Memory ───────────────────────────────────────────

    def mission_memory(self, mission_id: str) -> dict | None:
        """Get compressed state for an active mission."""
        return self.db.get_mission_memory(mission_id)

    def update_mission_memory(
        self,
        mission_id: str,
        summary: str,
        decisions: list[str] | None = None,
        blockers: list[str] | None = None,
    ) -> None:
        """Update the compressed state for a mission."""
        self.db.upsert_mission_memory(
            mission_id=mission_id,
            summary=summary,
            decisions=decisions or [],
            blockers=blockers or [],
        )

    # ─── Stats ────────────────────────────────────────────────────────

    def stats(self, venture: str | None = None) -> dict:
        """Get index statistics."""
        return self.db.get_stats(venture=venture)
