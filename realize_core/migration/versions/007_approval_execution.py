"""
Migration 007 — Approvals that execute (v5.7.0, STORY-16).

``approval_queue`` becomes the single approval store. A held tool action
is recorded with everything needed to run it once approved, and the
outcome is kept on the same row.

Adds columns to ``approval_queue``:
- ``action_name``   — registry action to execute (e.g. ``sheets_append``)
- ``params_json``   — full parameters (not the truncated display payload)
- ``requested_by``  — user the action was requested for
- ``session_ref``   — conversation to report back to (``<venture>|<user>``)
- ``updated_at``    — last change (also used by reports)
- ``executed_at``   — set when execution is claimed (exactly-once guard)
- ``result_json``   — tool output after execution
- ``error``         — error message if execution failed

Status values are unchanged (no table rebuild): execution state lives in
``executed_at`` / ``result_json`` / ``error``.
"""

import sqlite3

VERSION = 7
DESCRIPTION = "approval_queue execution columns (approvals that execute, v5.7.0)"

COLUMNS = {
    "action_name": "TEXT",
    "params_json": "TEXT",
    "requested_by": "TEXT",
    "session_ref": "TEXT",
    "updated_at": "TEXT",
    "executed_at": "TEXT",
    "result_json": "TEXT",
    "error": "TEXT",
}


def _existing_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(approval_queue)").fetchall()}


def up(conn: sqlite3.Connection) -> None:
    """Add the execution columns (idempotent: fresh schemas already have them)."""
    existing = _existing_columns(conn)
    for name, sql_type in COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE approval_queue ADD COLUMN {name} {sql_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_session ON approval_queue(session_ref, status)")


def down(conn: sqlite3.Connection) -> None:
    """Drop the execution columns (SQLite >= 3.35)."""
    conn.execute("DROP INDEX IF EXISTS idx_approval_session")
    existing = _existing_columns(conn)
    for name in COLUMNS:
        if name in existing:
            conn.execute(f"ALTER TABLE approval_queue DROP COLUMN {name}")
