"""
Persistent Memory Store for RealizeOS (SQLite).

Stores memories, conversations, sessions, episodes, and LLM usage as searchable records.
Schema: memories(id, system_key, category, content, tags, created_at)
Categories: feedback | decision | learning | preference | entity
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

logger = logging.getLogger(__name__)

# Retention policy defaults
MEMORY_RETENTION_DAYS = 90
MEMORY_MIN_PER_CATEGORY = 50

# Database path — configurable
DB_PATH: Path | None = None


def _resolve_db_path() -> Path:
    """Resolve the database path from config or default."""
    global DB_PATH
    if DB_PATH is None:
        from realize_core.config import DATA_PATH

        DB_PATH = DATA_PATH / "memory.db"
    return DB_PATH


def _get_conn() -> sqlite3.Connection:
    """Get a SQLite connection with row factory."""
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def db_connection():
    """Context manager for safe SQLite connections with auto-commit/rollback/close."""
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the memory database and create tables if needed."""
    with db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_key TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(content, system_key, category, content='memories', content_rowid='id')
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, system_key, category)
                VALUES (new.id, new.content, new.system_key, new.category);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, system_key, category)
                VALUES ('delete', old.id, old.content, old.system_key, old.category);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, system_key, category)
                VALUES ('delete', old.id, old.content, old.system_key, old.category);
                INSERT INTO memories_fts(rowid, content, system_key, category)
                VALUES (new.id, new.content, new.system_key, new.category);
            END
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_name TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                topic_id TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_lookup
            ON conversations(bot_name, user_id, created_at)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                system_key TEXT NOT NULL,
                user_id TEXT NOT NULL,
                brief TEXT NOT NULL,
                task_type TEXT NOT NULL,
                active_agent TEXT NOT NULL,
                stage TEXT NOT NULL,
                pipeline TEXT NOT NULL,
                pipeline_index INTEGER DEFAULT 0,
                context_files TEXT DEFAULT '[]',
                drafts TEXT DEFAULT '[]',
                review TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(system_key, user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                tenant_id TEXT DEFAULT 'default',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interaction_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT,
                feedback_signal TEXT,
                created_at TEXT NOT NULL
            )
        """)

    logger.info(f"Memory database initialized at {_resolve_db_path()}")


def store_memory(system_key: str, category: str, content: str, tags: list[str] = None):
    """Store a memory record, skipping near-duplicates."""
    with db_connection() as conn:
        # Duplicate detection: check for very similar content in same system/category
        existing = conn.execute(
            "SELECT content FROM memories WHERE system_key = ? AND category = ? "
            "ORDER BY created_at DESC LIMIT 20",
            (system_key, category),
        ).fetchall()
        for row in existing:
            if SequenceMatcher(None, content, row["content"]).ratio() > 0.85:
                logger.debug("Skipping near-duplicate memory: %s...", content[:50])
                return

        conn.execute(
            "INSERT INTO memories (system_key, category, content, tags, created_at) VALUES (?, ?, ?, ?, ?)",
            (system_key, category, content, json.dumps(tags or []), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )


def search_memories(query: str, system_key: str = None, limit: int = 5) -> list[dict]:
    """Search memories using FTS5."""
    with db_connection() as conn:
        if system_key:
            rows = conn.execute(
                "SELECT m.* FROM memories m JOIN memories_fts f ON m.id = f.rowid "
                "WHERE memories_fts MATCH ? AND m.system_key = ? LIMIT ?",
                (query, system_key, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT m.* FROM memories m JOIN memories_fts f ON m.id = f.rowid WHERE memories_fts MATCH ? LIMIT ?",
                (query, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def log_llm_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    tenant_id: str = "default",
):
    """Log an LLM API call for cost tracking."""
    try:
        with db_connection() as conn:
            conn.execute(
                "INSERT INTO llm_usage (model, input_tokens, output_tokens, cost_usd, tenant_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (model, input_tokens, output_tokens, cost_usd, tenant_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
    except Exception as e:
        logger.debug(f"Failed to log LLM usage: {e}")


def get_feedback_signals(task_type: str, days: int = 30) -> dict:
    """
    Get aggregated feedback signals for a task type.

    Returns:
        Dict mapping signal name to count, e.g. {"positive": 5, "negative": 2, "reset": 1}
    """
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with db_connection() as conn:
            rows = conn.execute(
                "SELECT feedback_signal, COUNT(*) as c FROM interaction_log "
                "WHERE task_type = ? AND created_at >= ? AND feedback_signal IS NOT NULL "
                "GROUP BY feedback_signal",
                (task_type, cutoff),
            ).fetchall()
        return {row["feedback_signal"]: row["c"] for row in rows}
    except Exception:
        return {}


def get_usage_stats(tenant_id: str = "default", days: int = 30) -> dict:
    """Get usage statistics for a tenant."""
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with db_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as calls, SUM(input_tokens) as inp, "
                "SUM(output_tokens) as outp, SUM(cost_usd) as cost "
                "FROM llm_usage WHERE tenant_id = ? AND created_at >= ?",
                (tenant_id, cutoff),
            ).fetchone()
        return {
            "total_calls": row["calls"] or 0,
            "total_input_tokens": row["inp"] or 0,
            "total_output_tokens": row["outp"] or 0,
            "total_cost_usd": round(row["cost"] or 0.0, 4),
        }
    except Exception:
        return {"total_calls": 0, "total_input_tokens": 0, "total_output_tokens": 0, "total_cost_usd": 0.0}


def prune_old_memories(
    retention_days: int = MEMORY_RETENTION_DAYS,
    min_per_category: int = MEMORY_MIN_PER_CATEGORY,
) -> int:
    """
    Remove memories older than retention_days, keeping at least
    min_per_category entries per system_key/category pair.

    Returns:
        Number of records deleted.
    """
    cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
    deleted = 0

    try:
        with db_connection() as conn:
            # Find system_key/category pairs with old rows
            pairs = conn.execute(
                "SELECT DISTINCT system_key, category FROM memories "
                "WHERE created_at < ?",
                (cutoff,),
            ).fetchall()

            for pair in pairs:
                sk, cat = pair["system_key"], pair["category"]
                # Count total entries for this pair
                total = conn.execute(
                    "SELECT COUNT(*) as c FROM memories WHERE system_key = ? AND category = ?",
                    (sk, cat),
                ).fetchone()["c"]

                if total <= min_per_category:
                    continue  # Keep minimum entries

                # Delete oldest entries beyond the minimum, older than cutoff
                deletable = total - min_per_category
                result = conn.execute(
                    "DELETE FROM memories WHERE id IN ("
                    "  SELECT id FROM memories "
                    "  WHERE system_key = ? AND category = ? AND created_at < ? "
                    "  ORDER BY created_at ASC LIMIT ?"
                    ")",
                    (sk, cat, cutoff, deletable),
                )
                deleted += result.rowcount

        if deleted:
            logger.info("Pruned %d old memories (retention=%d days)", deleted, retention_days)
    except Exception as e:
        logger.warning("Memory pruning failed: %s", e)

    return deleted
