"""
Knowledge Base Indexer: Indexes markdown files for hybrid search.

Combines FTS5 keyword search with vector embeddings for semantic matching.
Hybrid scoring: 0.7 * vector_similarity + 0.3 * keyword_rank (BM25).
Uses fastembed for local-only embeddings (no API calls, no data leaving the machine).
Falls back to FTS5-only search when fastembed is not installed.

Index stored in SQLite for persistence across restarts.
"""

import logging
import sqlite3
import struct
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Embedding model (lazy-loaded)
_embedder = None
_embedder_available = None


def _get_conn(db_path: Path) -> sqlite3.Connection:
    """Get a SQLite connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _init_index_db(db_path: Path):
    """Create the index tables."""
    conn = _get_conn(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kb_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            title TEXT,
            system_key TEXT,
            content TEXT,
            embedding BLOB,
            file_mtime REAL DEFAULT 0,
            last_indexed TEXT
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts
        USING fts5(path, title, content, system_key, content='kb_files', content_rowid='id')
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS kb_ai AFTER INSERT ON kb_files BEGIN
            INSERT INTO kb_fts(rowid, path, title, content, system_key)
            VALUES (new.id, new.path, new.title, new.content, new.system_key);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS kb_ad AFTER DELETE ON kb_files BEGIN
            INSERT INTO kb_fts(kb_fts, rowid, path, title, content, system_key)
            VALUES ('delete', old.id, old.path, old.title, old.content, old.system_key);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS kb_au AFTER UPDATE ON kb_files BEGIN
            INSERT INTO kb_fts(kb_fts, rowid, path, title, content, system_key)
            VALUES ('delete', old.id, old.path, old.title, old.content, old.system_key);
            INSERT INTO kb_fts(rowid, path, title, content, system_key)
            VALUES (new.id, new.path, new.title, new.content, new.system_key);
        END
    """)
    conn.commit()
    conn.close()


def _get_embedder():
    """Get the fastembed embedding model (lazy-loaded, optional)."""
    global _embedder, _embedder_available
    if _embedder_available is False:
        return None
    if _embedder is not None:
        return _embedder
    try:
        from fastembed import TextEmbedding

        _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        _embedder_available = True
        logger.info("Fastembed loaded: BAAI/bge-small-en-v1.5 (local embeddings active)")
        return _embedder
    except ImportError:
        _embedder_available = False
        logger.info("Fastembed not installed — FTS5-only search (pip install fastembed for hybrid)")
        return None
    except Exception as e:
        _embedder_available = False
        logger.warning(f"Fastembed failed to load: {e} — FTS5-only search")
        return None


def _embed_text(text: str) -> bytes | None:
    """Embed text and return as bytes (for SQLite BLOB storage)."""
    embedder = _get_embedder()
    if embedder is None:
        return None
    try:
        embeddings = list(embedder.embed([text[:2000]]))
        vec = embeddings[0]
        return struct.pack(f"{len(vec)}f", *vec)
    except Exception as e:
        logger.warning(f"Embedding failed: {e}")
        return None


def _bytes_to_vec(data: bytes) -> list[float]:
    """Convert BLOB bytes back to a float vector."""
    count = len(data) // 4
    return list(struct.unpack(f"{count}f", data))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _detect_system(path: str, systems_config: dict = None) -> str:
    """Detect which system a file belongs to from its path."""
    path_lower = path.lower()
    if systems_config:
        for key, conf in systems_config.items():
            sys_dir = conf.get("system_dir", "").lower()
            if sys_dir and sys_dir in path_lower:
                return key
    # Default: extract from path structure (systems/<key>/...)
    parts = Path(path).parts
    if len(parts) >= 2 and parts[0] == "systems":
        return parts[1]
    return "shared"


def _extract_title(content: str, path: str) -> str:
    """Extract the first heading from markdown content, or use filename."""
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return Path(path).stem.replace("-", " ").title()


def _build_search_dirs(kb_path: Path) -> list[str]:
    """
    Auto-discover FABRIC directories to index from all systems.
    No hardcoded paths — scans the systems/ directory dynamically.
    """
    dirs = []
    systems_dir = kb_path / "systems"
    if systems_dir.exists():
        for system_dir in systems_dir.iterdir():
            if system_dir.is_dir() and not system_dir.name.startswith("."):
                for fabric_dir in ["F-foundations", "A-agents", "B-brain", "R-routines", "I-insights"]:
                    subdir = system_dir / fabric_dir
                    if subdir.exists():
                        dirs.append(str(subdir.relative_to(kb_path)))

    # Also index shared/ directory
    shared_dir = kb_path / "shared"
    if shared_dir.exists():
        dirs.append("shared")

    return dirs


def index_kb_files(kb_root: str, db_path: Path = None, force: bool = False) -> int:
    """
    Walk all .md files in KB directories, index their content and embeddings.
    Uses incremental indexing — only re-indexes files whose mtime changed.

    Args:
        kb_root: Root path of the knowledge base
        db_path: Path for the index database. Defaults to <kb_root>/kb_index.db
        force: If True, re-index all files regardless of mtime

    Returns:
        Number of files indexed.
    """
    kb_path = Path(kb_root)
    if db_path is None:
        db_path = kb_path / "kb_index.db"

    _init_index_db(db_path)
    conn = _get_conn(db_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0

    # Load existing mtimes for incremental check
    existing_mtimes = {}
    if not force:
        try:
            rows = conn.execute("SELECT path, file_mtime FROM kb_files").fetchall()
            existing_mtimes = {r["path"]: r["file_mtime"] or 0 for r in rows}
        except Exception:
            pass

    # Auto-discover directories to index
    search_dirs = _build_search_dirs(kb_path)

    file_data = []
    skipped = 0

    for search_dir in search_dirs:
        dir_path = kb_path / search_dir
        if not dir_path.exists():
            continue

        for md_file in dir_path.rglob("*.md"):
            try:
                rel_path = str(md_file.relative_to(kb_path))
                current_mtime = md_file.stat().st_mtime

                if not force and rel_path in existing_mtimes:
                    if current_mtime <= existing_mtimes[rel_path]:
                        skipped += 1
                        continue

                content = md_file.read_text(encoding="utf-8")
                title = _extract_title(content, rel_path)
                system_key = _detect_system(rel_path)
                indexed_content = content[:5000]
                file_data.append((rel_path, title, system_key, indexed_content, current_mtime))
            except Exception as e:
                logger.warning(f"Failed to read {md_file}: {e}")

    if not file_data:
        conn.close()
        logger.info(f"KB index: 0 files changed ({skipped} unchanged)")
        return 0

    # Batch embed if available
    embedder = _get_embedder()
    embeddings_map = {}
    if embedder and file_data:
        try:
            texts = [f"{title} {content[:2000]}" for _, title, _, content, _ in file_data]
            vectors = list(embedder.embed(texts))
            for i, (rel_path, _, _, _, _) in enumerate(file_data):
                vec = vectors[i]
                embeddings_map[rel_path] = struct.pack(f"{len(vec)}f", *vec)
            logger.info(f"Generated embeddings for {len(vectors)} files")
        except Exception as e:
            logger.warning(f"Batch embedding failed: {e}")

    # Upsert changed files
    for rel_path, title, system_key, indexed_content, file_mtime in file_data:
        try:
            embedding_blob = embeddings_map.get(rel_path)
            existing = conn.execute("SELECT id FROM kb_files WHERE path = ?", (rel_path,)).fetchone()
            if existing:
                if embedding_blob:
                    conn.execute(
                        "UPDATE kb_files SET title=?, content=?, system_key=?, embedding=?, file_mtime=?, last_indexed=? WHERE path=?",
                        (title, indexed_content, system_key, embedding_blob, file_mtime, now, rel_path),
                    )
                else:
                    conn.execute(
                        "UPDATE kb_files SET title=?, content=?, system_key=?, file_mtime=?, last_indexed=? WHERE path=?",
                        (title, indexed_content, system_key, file_mtime, now, rel_path),
                    )
            else:
                conn.execute(
                    "INSERT INTO kb_files (path, title, system_key, content, embedding, file_mtime, last_indexed) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (rel_path, title, system_key, indexed_content, embedding_blob, file_mtime, now),
                )
            count += 1
        except Exception as e:
            logger.warning(f"Failed to index {rel_path}: {e}")

    conn.commit()
    conn.close()
    mode = "hybrid (vector+keyword)" if embeddings_map else "keyword-only (FTS5)"
    logger.info(f"Indexed {count} KB files ({skipped} unchanged) [{mode}]")
    return count


def semantic_search(
    query: str,
    system_key: str = None,
    top_k: int = 5,
    db_path: Path = None,
    kb_root: str = None,
) -> list[dict]:
    """
    Hybrid search: combines vector similarity (0.7) with FTS5 keyword rank (0.3).

    Args:
        query: Search query
        system_key: Filter by system (optional)
        top_k: Maximum results
        db_path: Path to index database
        kb_root: KB root for default db_path

    Returns:
        List of dicts with path, title, system_key, snippet, score.
    """
    if db_path is None:
        from realize_core.config import KB_PATH

        db_path = KB_PATH / "kb_index.db"

    _init_index_db(db_path)
    conn = _get_conn(db_path)

    fts_results = _fts_search(conn, query, system_key, top_k=top_k * 2)
    query_embedding = _embed_text(query)

    if query_embedding is not None:
        vector_results = _vector_search(conn, query_embedding, system_key, top_k=top_k * 2)
        results = _merge_hybrid(fts_results, vector_results, top_k)
        conn.close()
        return results

    conn.close()
    return fts_results[:top_k]


def _fts_search(conn, query: str, system_key: str = None, top_k: int = 10) -> list[dict]:
    """FTS5 keyword search with BM25 ranking."""
    try:
        if system_key:
            rows = conn.execute(
                "SELECT path, title, system_key, snippet(kb_fts, 2, '>>>', '<<<', '...', 50) as snippet, rank "
                "FROM kb_fts WHERE kb_fts MATCH ? AND system_key = ? ORDER BY rank LIMIT ?",
                (query, system_key, top_k),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT path, title, system_key, snippet(kb_fts, 2, '>>>', '<<<', '...', 50) as snippet, rank "
                "FROM kb_fts WHERE kb_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, top_k),
            ).fetchall()

        results = []
        if rows:
            min_rank = min(r["rank"] for r in rows)
            max_rank = max(r["rank"] for r in rows)
            rank_range = max_rank - min_rank if max_rank != min_rank else 1.0
            for row in rows:
                norm_score = 1.0 - ((row["rank"] - min_rank) / rank_range) if rank_range else 1.0
                results.append(
                    {
                        "path": row["path"],
                        "title": row["title"],
                        "system_key": row["system_key"],
                        "snippet": row["snippet"],
                        "keyword_score": norm_score,
                    }
                )
        return results

    except sqlite3.OperationalError:
        sql = "SELECT path, title, system_key, substr(content, 1, 200) as snippet FROM kb_files WHERE content LIKE ? OR title LIKE ?"
        params = [f"%{query}%", f"%{query}%"]
        if system_key:
            sql += " AND system_key = ?"
            params.append(system_key)
        sql += " LIMIT ?"
        params.append(top_k)
        rows = conn.execute(sql, params).fetchall()
        return [{**dict(row), "keyword_score": 0.5} for row in rows]


def _vector_search(conn, query_blob: bytes, system_key: str = None, top_k: int = 10) -> list[dict]:
    """Vector similarity search using stored embeddings."""
    query_vec = _bytes_to_vec(query_blob)

    sql = "SELECT path, title, system_key, embedding, substr(content, 1, 200) as snippet FROM kb_files WHERE embedding IS NOT NULL"
    params = []
    if system_key:
        sql += " AND system_key = ?"
        params.append(system_key)
    rows = conn.execute(sql, params).fetchall()

    scored = []
    for row in rows:
        if row["embedding"]:
            doc_vec = _bytes_to_vec(row["embedding"])
            sim = _cosine_similarity(query_vec, doc_vec)
            scored.append(
                {
                    "path": row["path"],
                    "title": row["title"],
                    "system_key": row["system_key"],
                    "snippet": row["snippet"],
                    "vector_score": sim,
                }
            )

    scored.sort(key=lambda x: x["vector_score"], reverse=True)
    return scored[:top_k]


def _merge_hybrid(
    fts_results: list[dict],
    vector_results: list[dict],
    top_k: int,
    vector_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> list[dict]:
    """Merge FTS5 and vector results with weighted scoring."""
    merged: dict[str, dict] = {}

    for r in fts_results:
        path = r["path"]
        merged[path] = {**r, "vector_score": 0.0}

    for r in vector_results:
        path = r["path"]
        if path in merged:
            merged[path]["vector_score"] = r.get("vector_score", 0.0)
        else:
            merged[path] = {**r, "keyword_score": 0.0}

    for entry in merged.values():
        entry["score"] = vector_weight * entry.get("vector_score", 0.0) + keyword_weight * entry.get(
            "keyword_score", 0.0
        )

    results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)

    for r in results:
        r.pop("keyword_score", None)
        r.pop("vector_score", None)

    return results[:top_k]
