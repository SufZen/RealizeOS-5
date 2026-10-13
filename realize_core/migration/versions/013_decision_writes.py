"""
Migration 013 — Durable decision-log writes (Codex audit N05).

``decision_writes`` holds one row per decided approval that belongs in the
decision log: the intent is stored before the decision file is written and
marked done after it. A write that failed (disk full, read-only mount, venture
folder missing) stays ``pending`` and is retried at startup, after the next
logged decision, and by ``realize-os decisions retry``. The decision log also
creates the table on first use; this migration records it in the schema history.
"""

import sqlite3

VERSION = 13
DESCRIPTION = "decision_writes: durable, retried decision-log writes (audit N05)"


def up(conn: sqlite3.Connection) -> None:
    """Create decision_writes (idempotent)."""
    from realize_core.governance.decision_log import DDL

    conn.executescript(DDL)


def down(conn: sqlite3.Connection) -> None:
    """Drop decision_writes (pending decision-log retries are forgotten)."""
    conn.executescript("""
        DROP INDEX IF EXISTS idx_decision_writes_status;
        DROP TABLE IF EXISTS decision_writes;
    """)
