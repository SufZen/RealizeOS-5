"""
Migration 001 — Baseline schema.

Creates the foundational operational tables that already exist in
``realize_core/db/schema.py``.  This migration captures the baseline
so the migration engine can manage all future schema changes.

Tables created:
- ``activity_events``  — chronological log of all agent actions
- ``agent_states``     — current status of each agent
- ``approval_queue``   — pending human approval requests
- ``schema_version``   — legacy version tracking (from original schema.py)
"""
import sqlite3

VERSION = 1
DESCRIPTION = "Baseline schema — activity_events, agent_states, approval_queue"


def up(conn: sqlite3.Connection) -> None:
    """Create the baseline operational tables."""
    conn.executescript("""
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


        -- Legacy schema version tracking (kept for backward compatibility)
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
        );

        INSERT OR IGNORE INTO schema_version(version) VALUES (1);
    """)


def down(conn: sqlite3.Connection) -> None:
    """Drop all baseline tables (destructive — use only in dev/test)."""
    conn.executescript("""
        DROP TABLE IF EXISTS activity_events;
        DROP TABLE IF EXISTS agent_states;
        DROP TABLE IF EXISTS approval_queue;
        DROP TABLE IF EXISTS schema_version;
    """)
