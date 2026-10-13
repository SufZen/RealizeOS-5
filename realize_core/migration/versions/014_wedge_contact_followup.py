"""
Migration 014 — Wedge contact follow-up (audit N10).

Adds when a pilot user asked for a call and when, and by whom, the request
was handled, so call requests form an owner-visible contact queue
(``realize-os wedge contacts``). The wedge store adds the same columns on
first use; this migration records them in the schema history.
"""

import sqlite3

VERSION = 14
DESCRIPTION = "wedge_runs: call_requested_at, call_handled_at, call_handled_by (contact queue)"


def up(conn: sqlite3.Connection) -> None:
    """Add the follow-up columns (idempotent)."""
    from realize_core.wedge.store import ensure_schema

    ensure_schema(conn)


def down(conn: sqlite3.Connection) -> None:
    """Keep the columns: SQLite can't drop them on every supported version, and they're harmless."""
