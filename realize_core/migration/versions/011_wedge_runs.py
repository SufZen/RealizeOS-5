"""
Migration 011 — Self-serve wedge runs (STORY-46).

Counts per tender-register run (market, verification level, items) for the
pilot funnel. No document text is stored. The wedge store also creates the
table on first use; this migration records it in the schema history.
"""

import sqlite3

VERSION = 11
DESCRIPTION = "wedge_runs: self-serve tender-register pilot funnel (STORY-46)"


def up(conn: sqlite3.Connection) -> None:
    """Create wedge_runs (idempotent)."""
    from realize_core.wedge.store import DDL

    conn.executescript(DDL)


def down(conn: sqlite3.Connection) -> None:
    """Drop wedge_runs (funnel history is lost)."""
    conn.executescript("DROP TABLE IF EXISTS wedge_runs;")
