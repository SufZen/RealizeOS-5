"""
Migration 009 — OAuth 2.1 store for the MCP server (issue #21, STORY-37).

Claude.ai custom connectors can't send a static bearer header; they sign in
with OAuth (dynamic client registration + PKCE). These tables back the
authorization server in ``realize_core/mcp_server/oauth.py``:

- ``mcp_oauth_clients``  — dynamically registered clients (JSON metadata).
- ``mcp_oauth_requests`` — authorize requests waiting for the user to sign in.
- ``mcp_oauth_codes``    — single-use authorization codes, bound to a user.
- ``mcp_oauth_tokens``   — access and refresh tokens, bound to a user.

Codes and tokens are stored as SHA-256 hashes, never in plain text.
"""

import sqlite3

VERSION = 9
DESCRIPTION = "OAuth 2.1 clients, codes and tokens for MCP connectors (v5.14.0)"


def up(conn: sqlite3.Connection) -> None:
    """Create the MCP OAuth tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mcp_oauth_clients (
            client_id    TEXT PRIMARY KEY,
            client_info  TEXT NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
        );

        CREATE TABLE IF NOT EXISTS mcp_oauth_requests (
            request_id   TEXT PRIMARY KEY,
            client_id    TEXT NOT NULL,
            params       TEXT NOT NULL,
            expires_at   REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mcp_oauth_codes (
            code_hash    TEXT PRIMARY KEY,
            client_id    TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            data         TEXT NOT NULL,
            expires_at   REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mcp_oauth_tokens (
            token_hash   TEXT PRIMARY KEY,
            kind         TEXT NOT NULL CHECK(kind IN ('access', 'refresh')),
            grant_id     TEXT NOT NULL,
            client_id    TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            scopes       TEXT NOT NULL DEFAULT '',
            resource     TEXT,
            expires_at   INTEGER NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
        );

        CREATE INDEX IF NOT EXISTS idx_mcp_oauth_tokens_grant
            ON mcp_oauth_tokens(grant_id);

        CREATE INDEX IF NOT EXISTS idx_mcp_oauth_tokens_user
            ON mcp_oauth_tokens(user_id);
    """)


def down(conn: sqlite3.Connection) -> None:
    """Drop the MCP OAuth tables."""
    conn.executescript("""
        DROP INDEX IF EXISTS idx_mcp_oauth_tokens_user;
        DROP INDEX IF EXISTS idx_mcp_oauth_tokens_grant;
        DROP TABLE IF EXISTS mcp_oauth_tokens;
        DROP TABLE IF EXISTS mcp_oauth_codes;
        DROP TABLE IF EXISTS mcp_oauth_requests;
        DROP TABLE IF EXISTS mcp_oauth_clients;
    """)
