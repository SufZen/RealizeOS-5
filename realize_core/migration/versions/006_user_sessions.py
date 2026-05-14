"""
Migration 006 — User sessions (cookie-based dashboard auth).

Introduced in v5.2.0 to replace the prefix-whitelist hack from the v5.1.1
hotfix with proper session-cookie authentication for the dashboard.

Adds:
- ``user_sessions`` — server-side session records keyed by an opaque 32-byte
  random ID stored in the ``realize_session`` HttpOnly cookie.

Sessions are intentionally server-side (not signed JWTs in the cookie) so that
logout / revoke is instant, sweeping expired rows is cheap, and a leaked cookie
can be revoked without rotating signing keys.
"""

import sqlite3

VERSION = 6
DESCRIPTION = "User sessions table for cookie-based dashboard auth (v5.2.0)"


def up(conn: sqlite3.Connection) -> None:
    """Create the user_sessions table and supporting indexes."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id   TEXT PRIMARY KEY,
            csrf_token   TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            role         TEXT NOT NULL DEFAULT 'viewer'
                CHECK(role IN ('owner', 'admin', 'viewer')),
            created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            expires_at   TEXT NOT NULL,
            last_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
            ip_address   TEXT DEFAULT '',
            user_agent   TEXT DEFAULT '',
            remember_me  INTEGER NOT NULL DEFAULT 0 CHECK(remember_me IN (0, 1))
        );

        CREATE INDEX IF NOT EXISTS idx_user_sessions_user
            ON user_sessions(user_id, expires_at);

        CREATE INDEX IF NOT EXISTS idx_user_sessions_expires
            ON user_sessions(expires_at);
    """)


def down(conn: sqlite3.Connection) -> None:
    """Drop the user_sessions table."""
    conn.executescript("""
        DROP INDEX IF EXISTS idx_user_sessions_expires;
        DROP INDEX IF EXISTS idx_user_sessions_user;
        DROP TABLE IF EXISTS user_sessions;
    """)
