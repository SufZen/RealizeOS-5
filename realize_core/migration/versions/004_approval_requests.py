"""
Migration 004 — Approval requests table.

Ported from legacy ``realize_core/db/migrations.py`` (v3).

Adds:
- ``approval_requests`` table for operator approval workflow
"""

import sqlite3

VERSION = 4
DESCRIPTION = "Approval requests table (ported from legacy v3)"


def up(conn: sqlite3.Connection) -> None:
    """Create approval_requests table."""
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


def down(conn: sqlite3.Connection) -> None:
    """Drop approval_requests table."""
    conn.executescript("""
        DROP TABLE IF EXISTS approval_requests;
    """)
