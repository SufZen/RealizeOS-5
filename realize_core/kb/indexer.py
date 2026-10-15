"""
Knowledge Base Indexer: Indexes markdown files for hybrid search.

Combines FTS5 keyword search with vector embeddings for semantic matching.
Hybrid scoring: 0.7 * vector_similarity + 0.3 * keyword_rank (BM25).
Uses fastembed for local-only embeddings (no API calls, no data leaving the machine)
with a multilingual model (``KB_EMBED_MODEL``; ``none`` turns embeddings off).
Falls back to FTS5-only search when the model can't load.

Keyword search uses a trigram FTS5 index and a sanitised OR query
(:mod:`realize_core.utils.fts`), so questions in any language and with any
punctuation are safe and match documents in that language.

Index stored in SQLite for persistence across restarts.
"""

import logging
import os
import sqlite3
import struct
from datetime import datetime
from pathlib import Path, PurePath

from realize_core.utils.fts import build_match_query, fts_tokenizer, match_terms, short_tokens

logger = logging.getLogger(__name__)

#: Index schema version (``PRAGMA user_version``). 2: trigram FTS tokenizer.
KB_SCHEMA_VERSION = 2

#: Default embedding model: multilingual (Hebrew included), 384 dimensions.
#: fastembed doesn't ship ``intfloat/multilingual-e5-small``; this is the
#: closest model it supports. ``KB_EMBED_MODEL`` overrides it.
DEFAULT_EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
#: ``KB_EMBED_MODEL`` values that turn embeddings off (keyword search only).
_EMBED_OFF = frozenset({"", "none", "off", "0", "false"})

# Embedding model (lazy-loaded)
_embedder = None
_embedder_available = None
_embedder_model = None

# Max file size for indexing (1 MB) — skip larger files to prevent memory issues
MAX_INDEX_FILE_SIZE = 1_048_576

# Supported file extensions for indexing
SUPPORTED_EXTENSIONS = {"*.md", "*.yaml", "*.yml", "*.txt"}


def _get_conn(db_path: Path) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and busy_timeout."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


_FTS_TRIGGERS = ("kb_ai", "kb_ad", "kb_au")


def _create_fts(conn: sqlite3.Connection) -> None:
    """Create the FTS table (current tokenizer) and the triggers that keep it in sync."""
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts
        USING fts5(path, title, content, system_key, content='kb_files', content_rowid='id',
                   tokenize='{fts_tokenizer()}')
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
    # Only the indexed columns: clearing or writing an embedding leaves the FTS index alone.
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS kb_au AFTER UPDATE OF path, title, content, system_key ON kb_files BEGIN
            INSERT INTO kb_fts(kb_fts, rowid, path, title, content, system_key)
            VALUES ('delete', old.id, old.path, old.title, old.content, old.system_key);
            INSERT INTO kb_fts(rowid, path, title, content, system_key)
            VALUES (new.id, new.path, new.title, new.content, new.system_key);
        END
    """)


def _init_index_db(db_path: Path):
    """Create the index tables, migrating an older index to the current schema.

    Below :data:`KB_SCHEMA_VERSION`, or when the tokenizer recorded in
    ``kb_meta`` isn't the one this SQLite gets (:func:`fts_tokenizer`), the FTS
    table and its triggers are recreated and rebuilt from ``kb_files``. The
    embedding-model check is not here: it runs on the index path only
    (:func:`_sync_embed_model`), so a search never clears vectors.
    """
    conn = _get_conn(db_path)
    try:
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
        conn.execute("CREATE TABLE IF NOT EXISTS kb_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()

        if _fts_outdated(conn):
            conn.execute("BEGIN IMMEDIATE")
            # Another process may have rebuilt it while this one waited for the lock.
            if _fts_outdated(conn):
                tokenizer = fts_tokenizer()
                for trigger in _FTS_TRIGGERS:
                    conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                conn.execute("DROP TABLE IF EXISTS kb_fts")
                _create_fts(conn)
                conn.execute("INSERT INTO kb_fts(kb_fts) VALUES('rebuild')")
                conn.execute("INSERT OR REPLACE INTO kb_meta (key, value) VALUES ('fts_tokenizer', ?)", (tokenizer,))
                conn.execute(f"PRAGMA user_version = {KB_SCHEMA_VERSION}")
                logger.info("KB index at schema v%d, FTS rebuilt (tokenizer: %s)", KB_SCHEMA_VERSION, tokenizer)
        else:
            _create_fts(conn)
        conn.commit()
    finally:
        conn.close()


def _sync_embed_model(db_path: Path) -> None:
    """Index path only: when the embedding model changed, clear stored vectors.

    The next index run then embeds every file again with the current model.
    Searches never call this, so a process with another ``KB_EMBED_MODEL``
    (say, a CLI with embeddings off next to the server) can't wipe the vectors.
    """
    model = embed_model_name()
    if not model:
        return
    conn = _get_conn(db_path)
    try:
        if _stored_embed_model(conn) != model:
            cleared = conn.execute("UPDATE kb_files SET embedding = NULL WHERE embedding IS NOT NULL").rowcount
            conn.execute("INSERT OR REPLACE INTO kb_meta (key, value) VALUES ('embed_model', ?)", (model,))
            conn.commit()
            if cleared:
                logger.info("KB embedding model is now %s: %d stored vectors will be re-embedded", model, cleared)
    finally:
        conn.close()


def _stored_embed_model(conn: sqlite3.Connection) -> str | None:
    """The embedding model the stored vectors were made with (None if never recorded)."""
    row = conn.execute("SELECT value FROM kb_meta WHERE key = 'embed_model'").fetchone()
    return row["value"] if row else None


def _schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _fts_outdated(conn: sqlite3.Connection) -> bool:
    """True when ``kb_fts`` predates the current schema or was built with another tokenizer.

    The tokenizer depends on the SQLite version (:func:`fts_tokenizer`), so a
    SQLite upgrade moves the index to the better tokenizer on the next open.
    """
    if _schema_version(conn) < KB_SCHEMA_VERSION:
        return True
    row = conn.execute("SELECT value FROM kb_meta WHERE key = 'fts_tokenizer'").fetchone()
    return row is None or row["value"] != fts_tokenizer()


def embed_model_name() -> str | None:
    """The configured embedding model (``KB_EMBED_MODEL``), or None when embeddings are off."""
    name = os.environ.get("KB_EMBED_MODEL", DEFAULT_EMBED_MODEL).strip()
    return None if name.lower() in _EMBED_OFF else name


def _uses_e5_prefixes(model: str | None) -> bool:
    """E5 models expect ``query: `` / ``passage: `` before the text."""
    return bool(model) and "e5" in model.rsplit("/", 1)[-1].lower()


def _query_text(text: str) -> str:
    return f"query: {text}" if _uses_e5_prefixes(embed_model_name()) else text


def _passage_text(text: str) -> str:
    return f"passage: {text}" if _uses_e5_prefixes(embed_model_name()) else text


def _get_embedder():
    """Get the fastembed embedding model (lazy-loaded, optional).

    A model that can't load is logged once; search stays keyword-only.
    """
    global _embedder, _embedder_available, _embedder_model
    model = embed_model_name()
    if model != _embedder_model:
        _embedder, _embedder_available, _embedder_model = None, None, model
    if model is None or _embedder_available is False:
        return None
    if _embedder is not None:
        return _embedder
    try:
        from fastembed import TextEmbedding

        _embedder = TextEmbedding(model_name=model)
        _embedder_available = True
        logger.info("Fastembed loaded: %s (local embeddings active)", model)
        return _embedder
    except ImportError:
        _embedder_available = False
        logger.warning("Fastembed not installed — FTS5-only search (pip install fastembed for hybrid)")
        return None
    except Exception as e:
        _embedder_available = False
        logger.warning("Embedding model %s failed to load: %s — FTS5-only search", model, e)
        return None


def _embed_text(text: str) -> bytes | None:
    """Embed a search query and return it as bytes (for SQLite BLOB storage)."""
    embedder = _get_embedder()
    if embedder is None:
        return None
    try:
        embeddings = list(embedder.embed([_query_text(text[:2000])]))
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
    """Detect which system a file belongs to from its path.

    A venture's configured ``system_dir`` wins (the longest one the file is
    under); otherwise ``systems/<key>/...`` gives the key, else ``shared``.
    """
    posix = PurePath(path).as_posix().lower()
    if systems_config:
        best_key, best_len = None, 0
        for key, conf in systems_config.items():
            sys_dir = PurePath(str(conf.get("system_dir") or "")).as_posix().lower().strip("/")
            if sys_dir in ("", ".") or len(sys_dir) <= best_len:
                continue
            if posix == sys_dir or posix.startswith(sys_dir + "/"):
                best_key, best_len = key, len(sys_dir)
        if best_key is not None:
            return best_key
    # Default: extract from path structure (systems/<key>/...)
    parts = PurePath(path).parts
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


_FABRIC_DIRS = ("F-foundations", "A-agents", "B-brain", "R-routines", "I-insights")


def _build_search_dirs(kb_path: Path, systems_config: dict | None = None) -> list[str]:
    """
    Auto-discover FABRIC directories to index from all systems.
    No hardcoded paths — scans the systems/ directory dynamically, plus each
    configured venture's ``system_dir`` when it lives elsewhere in the KB.
    """
    dirs = []
    system_dirs: list[Path] = []
    systems_dir = kb_path / "systems"
    if systems_dir.exists():
        system_dirs = [d for d in systems_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    for conf in (systems_config or {}).values():
        sys_dir = kb_path / str(conf.get("system_dir") or "")
        if sys_dir == kb_path or sys_dir in system_dirs or not sys_dir.is_dir() or not _is_safe_path(sys_dir, kb_path):
            continue
        system_dirs.append(sys_dir)
    for system_dir in system_dirs:
        for fabric_dir in _FABRIC_DIRS:
            subdir = system_dir / fabric_dir
            if subdir.exists():
                dirs.append(str(subdir.relative_to(kb_path)))

    # Also index shared/ directory
    shared_dir = kb_path / "shared"
    if shared_dir.exists():
        dirs.append("shared")

    return dirs


def _is_safe_path(path: Path, root: Path) -> bool:
    """Check that a path is within root and not a symlink loop."""
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _escape_like(query: str) -> str:
    """Escape special characters for SQLite LIKE patterns."""
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def index_kb_files(
    kb_root: str,
    db_path: Path = None,
    force: bool = False,
    systems_config: dict | None = None,
) -> int:
    """
    Walk supported files in KB directories, index their content and embeddings.
    Uses incremental indexing — only re-indexes files whose mtime changed (or
    that still need a vector from the current embedding model).

    Args:
        kb_root: Root path of the knowledge base
        db_path: Path for the index database. Defaults to <kb_root>/kb_index.db when
            that folder is writable, else DATA_PATH/kb_index.db
        force: If True, re-index all files regardless of mtime
        systems_config: Venture configs (``build_systems_dict``): a venture with a
            custom ``system_dir`` is indexed under its own key

    Returns:
        Number of files indexed.
    """
    kb_path = Path(kb_root)
    if db_path is None:
        from realize_core.config import persisted_path

        db_path = persisted_path("kb_index.db", kb_path, state=False)

    _init_index_db(db_path)
    _sync_embed_model(db_path)
    conn = _get_conn(db_path)
    try:
        return _do_index(conn, kb_path, force, systems_config)
    finally:
        conn.close()


def _do_index(conn: sqlite3.Connection, kb_path: Path, force: bool, systems_config: dict | None = None) -> int:
    """Internal indexing implementation with guaranteed connection cleanup."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0

    # Load existing mtimes for incremental check
    existing_mtimes = {}
    existing_keys: dict[str, str] = {}
    # Unchanged files without a vector (model changed, or indexed while embeddings were off)
    missing_vectors: set[str] = set()
    if not force:
        try:
            rows = conn.execute(
                "SELECT path, file_mtime, system_key, embedding IS NULL AS no_vec FROM kb_files"
            ).fetchall()
            existing_mtimes = {r["path"]: r["file_mtime"] or 0 for r in rows}
            existing_keys = {r["path"]: r["system_key"] for r in rows}
            missing_vectors = {r["path"] for r in rows if r["no_vec"]}
        except Exception:
            pass
    # Loads the model only when an unchanged file needs a vector.
    re_embed = bool(missing_vectors) and _get_embedder() is not None

    # Auto-discover directories to index
    search_dirs = _build_search_dirs(kb_path, systems_config)

    file_data = []
    skipped = 0
    seen_paths: set[str] = set()

    for search_dir in search_dirs:
        dir_path = kb_path / search_dir
        if not dir_path.exists():
            continue

        for ext_pattern in SUPPORTED_EXTENSIONS:
            for found_file in dir_path.rglob(ext_pattern):
                try:
                    # Symlink safety: ensure resolved path is within kb_path
                    if found_file.is_symlink() and not _is_safe_path(found_file, kb_path):
                        logger.debug("Skipping symlink outside KB root: %s", found_file)
                        continue

                    # Skip files larger than MAX_INDEX_FILE_SIZE
                    file_size = found_file.stat().st_size
                    if file_size > MAX_INDEX_FILE_SIZE:
                        logger.debug("Skipping large file (%d bytes): %s", file_size, found_file)
                        continue

                    rel_path = str(found_file.relative_to(kb_path))

                    # Deduplicate (a file might match multiple patterns)
                    if rel_path in seen_paths:
                        continue
                    seen_paths.add(rel_path)

                    current_mtime = found_file.stat().st_mtime

                    system_key = _detect_system(rel_path, systems_config)
                    if not force and rel_path in existing_mtimes:
                        needs_vector = re_embed and rel_path in missing_vectors
                        # A venture's system_dir config can move a file to another key.
                        moved = existing_keys.get(rel_path) != system_key
                        if current_mtime <= existing_mtimes[rel_path] and not needs_vector and not moved:
                            skipped += 1
                            continue

                    # Read with encoding error fallback
                    try:
                        content = found_file.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        try:
                            content = found_file.read_text(encoding="utf-8", errors="replace")
                            logger.debug("Read with replacement chars: %s", found_file)
                        except Exception:
                            logger.warning("Failed to read file with any encoding: %s", found_file)
                            continue

                    title = _extract_title(content, rel_path)
                    indexed_content = content[:5000]
                    file_data.append((rel_path, title, system_key, indexed_content, current_mtime))
                except Exception as e:
                    logger.warning(f"Failed to read {found_file}: {e}")

    # Clean up stale entries (files that no longer exist on disk)
    try:
        all_indexed = conn.execute("SELECT path FROM kb_files").fetchall()
        for row in all_indexed:
            indexed_path = row["path"]
            full_path = kb_path / indexed_path
            if not full_path.exists():
                conn.execute("DELETE FROM kb_files WHERE path = ?", (indexed_path,))
                logger.debug("Removed stale index entry: %s", indexed_path)
    except Exception as e:
        logger.warning(f"Failed to clean stale entries: {e}")

    if not file_data:
        conn.commit()  # Commit any stale entry deletions
        logger.info(f"KB index: 0 files changed ({skipped} unchanged)")
        return 0

    # Batch embed if available
    embedder = _get_embedder()
    embeddings_map = {}
    if embedder and file_data:
        try:
            texts = [_passage_text(f"{title} {content[:2000]}") for _, title, _, content, _ in file_data]
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
                    # The old vector described the old content: clear it so a later run re-embeds.
                    conn.execute(
                        "UPDATE kb_files SET title=?, content=?, system_key=?, embedding=NULL, file_mtime=?, last_indexed=? WHERE path=?",
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
        from realize_core.config import KB_PATH, persisted_path

        db_path = persisted_path("kb_index.db", KB_PATH, state=False)

    _init_index_db(db_path)
    conn = _get_conn(db_path)

    try:
        fts_results = _fts_search(conn, query, system_key, top_k=top_k * 2)
        # Vectors made by another model are not comparable with this query's embedding.
        same_model = _stored_embed_model(conn) == embed_model_name()
        query_embedding = _embed_text(query) if same_model else None

        if query_embedding is not None:
            vector_results = _vector_search(conn, query_embedding, system_key, top_k=top_k * 2)
            return _merge_hybrid(fts_results, vector_results, top_k)

        return fts_results[:top_k]
    finally:
        conn.close()


def _fts_search(conn, query: str, system_key: str = None, top_k: int = 10) -> list[dict]:
    """FTS5 keyword search with BM25 ranking.

    The query never reaches ``MATCH`` raw: :func:`build_match_query` quotes
    every term and joins them with ``OR``. Words too short for trigrams, or an
    FTS error, fall back to a ``LIKE`` search with the same venture filter.
    """
    match = build_match_query(query)
    if match is None:
        return _like_search(conn, short_tokens(query), system_key, top_k)
    sql = (
        "SELECT path, title, system_key, snippet(kb_fts, 2, '>>>', '<<<', '...', 50) AS snippet, "
        "bm25(kb_fts) AS score FROM kb_fts WHERE kb_fts MATCH ?"
    )
    params: list = [match]
    if system_key:
        sql += " AND system_key = ?"
        params.append(system_key)
    sql += " ORDER BY score LIMIT ?"
    params.append(top_k)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning("KB FTS search failed (%s): using LIKE search", e)
        return _like_search(conn, match_terms(query) + short_tokens(query), system_key, top_k)

    if not rows:
        return _like_search(conn, short_tokens(query), system_key, top_k)

    # bm25: lower is better. Min-max normalise so the best match scores 1.0.
    scores = [row["score"] for row in rows]
    best, spread = min(scores), max(scores) - min(scores)
    return [
        {
            "path": row["path"],
            "title": row["title"],
            "system_key": row["system_key"],
            "snippet": row["snippet"],
            "keyword_score": 1.0 - (row["score"] - best) / spread if spread else 1.0,
        }
        for row in rows
    ]


def _like_search(conn, terms: list[str], system_key: str = None, top_k: int = 10) -> list[dict]:
    """Substring search of content and title for any of ``terms``, within ``system_key`` when given."""
    if not terms:
        return []
    clauses: list[str] = []
    params: list = []
    for term in terms:
        pattern = f"%{_escape_like(term)}%"
        clauses.append("content LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'")
        params += [pattern, pattern]
    # Parenthesised: the venture filter must apply to every alternative.
    sql = (
        "SELECT path, title, system_key, substr(content, 1, 200) AS snippet "
        f"FROM kb_files WHERE ({' OR '.join(clauses)})"
    )
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
