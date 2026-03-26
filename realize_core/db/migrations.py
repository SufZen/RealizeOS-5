"""
Migration compatibility shim for RealizeOS.

.. deprecated:: V5
    This module is a backward-compatible shim.  All migration logic has
    been moved to ``realize_core.migration.engine.MigrationEngine`` and
    individual version modules under ``realize_core/migration/versions/``.

    New code should use::

        from realize_core.migration.engine import MigrationEngine
        engine = MigrationEngine()
        engine.migrate_up()

    This shim is kept so that ``realize_api.main`` and existing test
    imports continue to work without changes.
"""

import logging
import sqlite3
import warnings
from pathlib import Path
from typing import Callable, Optional

from realize_core.db.schema import get_connection, init_schema

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Legacy MIGRATIONS dict — kept for backward compatibility with tests
# that inspect ``MIGRATIONS`` directly (test_messaging, test_hardening_phase2,
# test_approval_tool, test_launch_checklist).
# ---------------------------------------------------------------------------

MIGRATIONS: dict[int, Callable] = {}


def _migration_v2(conn):
    """Storage sync log + performance indexes (legacy — now in versions/003)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS storage_sync_log (
            id TEXT PRIMARY KEY,
            sync_type TEXT NOT NULL,
            source_backend TEXT NOT NULL,
            target_backend TEXT NOT NULL,
            file_key TEXT NOT NULL,
            file_size_bytes INTEGER,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped')),
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            completed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_sync_log_status
            ON storage_sync_log(status, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_sync_log_file_key
            ON storage_sync_log(file_key);

        CREATE INDEX IF NOT EXISTS idx_activity_created_at
            ON activity_events(created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_activity_entity
            ON activity_events(entity_type, entity_id);

        CREATE INDEX IF NOT EXISTS idx_approval_expires
            ON approval_queue(expires_at)
            WHERE status = 'pending';
    """)


MIGRATIONS[2] = _migration_v2


def _migration_v3(conn):
    """Approval requests table (legacy — now in versions/004)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS approval_requests (
            id TEXT PRIMARY KEY,
            action TEXT NOT NULL CHECK(action IN ('request_decision', 'request_credential', 'request_input')),
            description TEXT NOT NULL,
            agent_key TEXT NOT NULL,
            system_key TEXT NOT NULL,
            session_id TEXT DEFAULT '',
            options TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled')),
            response TEXT,
            responded_by TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            expires_at TEXT NOT NULL,
            responded_at TEXT,
            metadata TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_approval_status
            ON approval_requests(status, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_approval_system
            ON approval_requests(system_key, status);

        CREATE INDEX IF NOT EXISTS idx_approval_agent
            ON approval_requests(agent_key, status);
    """)


MIGRATIONS[3] = _migration_v3


def _migration_v4(conn):
    """Messaging tables (legacy — now in versions/005)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_messages (
            id TEXT PRIMARY KEY,
            sender TEXT NOT NULL,
            target TEXT NOT NULL,
            target_type TEXT NOT NULL CHECK(target_type IN ('agent', 'human', 'channel')),
            target_id TEXT NOT NULL,
            content TEXT NOT NULL,
            system_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'sent'
                CHECK(status IN ('sent', 'delivered', 'read', 'queued', 'failed')),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            delivered_at TEXT,
            read_at TEXT,
            metadata TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_messages_target
            ON agent_messages(target_type, target_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_messages_sender
            ON agent_messages(sender, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_messages_status
            ON agent_messages(status);

        CREATE TABLE IF NOT EXISTS message_channels (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            system_key TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            UNIQUE(name, system_key)
        );

        CREATE TABLE IF NOT EXISTS message_channel_subscribers (
            channel_id TEXT NOT NULL,
            agent_key TEXT NOT NULL,
            subscribed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            PRIMARY KEY (channel_id, agent_key),
            FOREIGN KEY (channel_id) REFERENCES message_channels(id)
        );

        CREATE TABLE IF NOT EXISTS message_queues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT NOT NULL,
            agent_key TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            FOREIGN KEY (message_id) REFERENCES agent_messages(id)
        );

        CREATE INDEX IF NOT EXISTS idx_queue_agent
            ON message_queues(agent_key, created_at);
    """)


MIGRATIONS[4] = _migration_v4


# ---------------------------------------------------------------------------
# Public API — backward compatible
# ---------------------------------------------------------------------------


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version from the database."""
    try:
        row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        return row["v"] if row and row["v"] else 0
    except sqlite3.OperationalError:
        return 0


def run_migrations(db_path: Optional[Path] = None):
    """
    Run all pending migrations.

    .. deprecated:: V5
        Prefer ``MigrationEngine().migrate_up()`` for new code.

    Kept for backward compatibility with ``realize_api.main`` and tests.

    1. Ensures base schema exists (version 1)
    2. Checks current version
    3. Applies any migrations with version > current
    """
    init_schema(db_path)
    conn = get_connection(db_path)

    try:
        current = get_current_version(conn)
        pending = {v: fn for v, fn in MIGRATIONS.items() if v > current}

        if not pending:
            logger.debug(f"Database at version {current}, no migrations needed")
            return

        for version in sorted(pending.keys()):
            logger.info(f"Running migration v{version}...")
            try:
                pending[version](conn)
                conn.execute(
                    "INSERT INTO schema_version(version) VALUES (?)",
                    (version,),
                )
                conn.commit()
                logger.info(f"Migration v{version} complete")
            except Exception as e:
                conn.rollback()
                logger.error(f"Migration v{version} failed: {e}")
                raise
    finally:
        conn.close()
