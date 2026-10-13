"""
Migration 012 — Venture-scoped agent tokens (STORY-37).

``agent_tokens`` holds named, revocable tokens for outside agents (MCP and
REST). Each token is bound to a ``users.yaml`` user and names the ventures
the agent may see. Only a SHA-256 hash of the token is stored; the token
itself is shown once, at creation. The token store also creates the table on
first use; this migration records it in the schema history.
"""

import sqlite3

VERSION = 12
DESCRIPTION = "agent_tokens: venture-scoped tokens for outside agents (STORY-37)"


def up(conn: sqlite3.Connection) -> None:
    """Create agent_tokens (idempotent)."""
    from realize_core.security.agent_tokens import DDL

    conn.executescript(DDL)


def down(conn: sqlite3.Connection) -> None:
    """Drop agent_tokens (every agent token stops working)."""
    conn.executescript("""
        DROP INDEX IF EXISTS idx_agent_tokens_user;
        DROP TABLE IF EXISTS agent_tokens;
    """)
