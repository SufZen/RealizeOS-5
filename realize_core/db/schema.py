"""
SQLite schema for RealizeOS operational data.

Tables:
- activity_events: chronological log of all agent actions
- agent_states: current status of each agent (idle/running/paused/error)
- approval_queue: pending human approval requests
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH: Path | None = None
_SCHEMA_VERSION = 1


def get_db_path(base_path: Path = None) -> Path:
    """Get the database file path. Defaults to <cwd>/realize_data.db."""
    global _DB_PATH
    if _DB_PATH is not None:
        return _DB_PATH
    if base_path:
        _DB_PATH = base_path / "realize_data.db"
    else:
        _DB_PATH = Path("realize_data.db")
    return _DB_PATH


def set_db_path(path=None):
    """Override the database path (useful for testing). Pass None to reset."""
    global _DB_PATH
    _DB_PATH = Path(path) if path is not None else None


def get_connection(db_path: Path = None, retries: int = 3) -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled.

    Retries on SQLITE_BUSY with exponential backoff.
    """
    import time

    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    delays = [0.1, 0.5, 1.0]
    for attempt in range(retries):
        try:
            conn = sqlite3.connect(str(path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                if attempt < retries - 1:
                    delay = delays[min(attempt, len(delays) - 1)]
                    logger.warning(f"Database busy, retrying in {delay}s (attempt {attempt + 1}/{retries})")
                    time.sleep(delay)
                else:
                    raise
            else:
                raise
    # Unreachable, but satisfies type checker
    raise sqlite3.OperationalError("Database connection failed after retries")


def init_schema(db_path: Path = None):
    """
    Create all operational tables if they don't exist.
    Safe to call multiple times (uses IF NOT EXISTS).
    """
    conn = get_connection(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        logger.info("Database schema initialized")
    finally:
        conn.close()


_SCHEMA_SQL = """
-- Activity Events: chronological log of all agent actions
CREATE TABLE IF NOT EXISTS activity_events (
    id TEXT PRIMARY KEY,
    venture_key TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK(actor_type IN ('agent', 'system', 'user')),
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_activity_venture_time
    ON activity_events(venture_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activity_actor_time
    ON activity_events(venture_key, actor_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activity_action
    ON activity_events(action, created_at DESC);


-- Agent States: current status of each agent
CREATE TABLE IF NOT EXISTS agent_states (
    agent_key TEXT NOT NULL,
    venture_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle'
        CHECK(status IN ('idle', 'running', 'paused', 'error')),
    last_run_at TEXT,
    last_error TEXT,
    schedule_cron TEXT,
    schedule_interval_sec INTEGER,
    next_run_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    PRIMARY KEY (agent_key, venture_key)
);

CREATE INDEX IF NOT EXISTS idx_agent_states_venture_status
    ON agent_states(venture_key, status);


-- Approval Queue: pending human approval requests
CREATE TABLE IF NOT EXISTS approval_queue (
    id TEXT PRIMARY KEY,
    venture_key TEXT NOT NULL,
    agent_key TEXT NOT NULL,
    action_type TEXT NOT NULL,
    payload TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'approved', 'rejected', 'expired')),
    decision_note TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    decided_at TEXT,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_approval_venture_status
    ON approval_queue(venture_key, status);

CREATE INDEX IF NOT EXISTS idx_approval_status
    ON approval_queue(status, created_at DESC);


-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
);

INSERT OR IGNORE INTO schema_version(version) VALUES (1);
"""
