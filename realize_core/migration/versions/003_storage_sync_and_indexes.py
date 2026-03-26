"""
Migration 003 — Storage sync log + performance indexes.

Ported from legacy ``realize_core/db/migrations.py`` (v2).

Adds:
- ``storage_sync_log`` table for tracking sync operations between storage providers
- Additional performance indexes on ``activity_events`` and ``approval_queue``
"""

import sqlite3

VERSION = 3
DESCRIPTION = "Storage sync log + performance indexes (ported from legacy v2)"


def up(conn: sqlite3.Connection) -> None:
    """Create storage sync log and add performance indexes."""
    conn.executescript("""
        -- Storage sync log (used by realize_core.storage.sync.SyncManager)
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

        -- Extra activity indexes for dashboard performance
        CREATE INDEX IF NOT EXISTS idx_activity_created_at
            ON activity_events(created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_activity_entity
            ON activity_events(entity_type, entity_id);

        -- Approval queue: index for expiry lookups
        CREATE INDEX IF NOT EXISTS idx_approval_expires
            ON approval_queue(expires_at)
            WHERE status = 'pending';
    """)


def down(conn: sqlite3.Connection) -> None:
    """Remove storage sync log and extra indexes."""
    conn.executescript("""
        DROP TABLE IF EXISTS storage_sync_log;
        DROP INDEX IF EXISTS idx_activity_created_at;
        DROP INDEX IF EXISTS idx_activity_entity;
        DROP INDEX IF EXISTS idx_approval_expires;
    """)
