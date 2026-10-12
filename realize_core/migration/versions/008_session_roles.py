"""
Migration 008 — Session roles for every RBAC role (v5.7.0, STORY-18).

``users.yaml`` now accepts ``operator`` and ``user`` (the RBAC built-ins), but
``user_sessions.role`` was limited to owner/admin/viewer by a CHECK constraint,
so signing in as an operator failed. SQLite can't alter a CHECK constraint, so
the table is rebuilt with the wider list; existing sessions are kept.
"""

import sqlite3

VERSION = 8
DESCRIPTION = "user_sessions.role accepts operator and user (v5.7.0)"

_ROLES_NEW = "'owner', 'admin', 'operator', 'user', 'viewer'"
_ROLES_OLD = "'owner', 'admin', 'viewer'"

_COLUMNS = (
    "session_id, csrf_token, user_id, role, created_at, expires_at, last_seen_at, ip_address, user_agent, remember_me"
)


def _rebuild(conn: sqlite3.Connection, roles: str) -> None:
    """Recreate user_sessions with ``roles`` allowed, keeping rows that fit."""
    exists = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'user_sessions'").fetchone()
    if not exists:
        return
    conn.executescript(f"""
        CREATE TABLE user_sessions_rebuild (
            session_id   TEXT PRIMARY KEY,
            csrf_token   TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            role         TEXT NOT NULL DEFAULT 'viewer'
                CHECK(role IN ({roles})),
            created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            expires_at   TEXT NOT NULL,
            last_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            ip_address   TEXT DEFAULT '',
            user_agent   TEXT DEFAULT '',
            remember_me  INTEGER NOT NULL DEFAULT 0 CHECK(remember_me IN (0, 1))
        );
        INSERT INTO user_sessions_rebuild ({_COLUMNS})
            SELECT {_COLUMNS} FROM user_sessions WHERE role IN ({roles});
        DROP TABLE user_sessions;
        ALTER TABLE user_sessions_rebuild RENAME TO user_sessions;
        CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id, expires_at);
        CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);
    """)


def up(conn: sqlite3.Connection) -> None:
    """Allow every RBAC role in user_sessions.role (idempotent)."""
    _rebuild(conn, _ROLES_NEW)


def down(conn: sqlite3.Connection) -> None:
    """Restore the owner/admin/viewer constraint; sessions of other roles are dropped."""
    _rebuild(conn, _ROLES_OLD)
