"""
Migration 007 — Approvals that execute (v5.7.0, STORY-16).

``approval_queue`` becomes the single approval store. A held tool action
is recorded with everything needed to run it once approved, and the
outcome is kept on the same row.

Adds columns to ``approval_queue``:
- ``action_name``      — registry action to execute (e.g. ``sheets_append``)
- ``params_json``      — full parameters (not the truncated display payload)
- ``requested_by``     — user the action was requested for
- ``session_ref``      — conversation to report back to (``<venture>|<user>``)
- ``updated_at``       — last change (also used by reports)
- ``executed_at``      — when execution was claimed (one dispatch per approval)
- ``result_json``      — tool output after execution
- ``error``            — error message if execution failed
- ``decided_by``       — who approved or rejected (or answered a skill question)
- ``decision_channel`` — where the decision came from (dashboard, api, mcp, chat)
- ``execution_status`` — ``claimed`` → ``succeeded`` / ``failed``; a row left at
  ``claimed`` has an unknown outcome and needs a person to check

Adds the status ``answered``: a skill's question (``skill_input``) was answered.
That is input, not an approval. SQLite can't change a CHECK constraint, so the
table is rebuilt when the old constraint is present.
"""

import sqlite3

VERSION = 7
DESCRIPTION = "approval_queue execution + decision columns, 'answered' status (v5.7.0)"

COLUMNS = {
    "action_name": "TEXT",
    "params_json": "TEXT",
    "requested_by": "TEXT",
    "session_ref": "TEXT",
    "updated_at": "TEXT",
    "executed_at": "TEXT",
    "result_json": "TEXT",
    "error": "TEXT",
    "decided_by": "TEXT",
    "decision_channel": "TEXT",
    "execution_status": "TEXT",
}

_BASE_COLUMNS = """
    id TEXT PRIMARY KEY,
    venture_key TEXT NOT NULL,
    agent_key TEXT NOT NULL,
    action_type TEXT NOT NULL,
    payload TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ({statuses})),
    decision_note TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    decided_at TEXT,
    expires_at TEXT"""

STATUSES_NEW = "'pending', 'approved', 'rejected', 'expired', 'answered'"
STATUSES_OLD = "'pending', 'approved', 'rejected', 'expired'"

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_approval_venture_status ON approval_queue(venture_key, status)",
    "CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_queue(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_approval_expires ON approval_queue(expires_at)",
)


def _existing_columns(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA table_info(approval_queue)").fetchall()]


def _table_sql(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'approval_queue'").fetchone()
    return row[0] if row else ""


def _rebuild(conn: sqlite3.Connection, statuses: str, extra: dict[str, str], status_map: str = "status") -> None:
    """Recreate approval_queue with ``statuses`` allowed and ``extra`` columns, keeping rows."""
    keep = [
        c
        for c in _existing_columns(conn)
        if c
        in {
            *extra,
            "id",
            "venture_key",
            "agent_key",
            "action_type",
            "payload",
            "status",
            "decision_note",
            "created_at",
            "decided_at",
            "expires_at",
        }
    ]
    extra_sql = "".join(f",\n    {name} {sql_type}" for name, sql_type in extra.items())
    conn.execute(f"CREATE TABLE approval_queue_rebuild ({_BASE_COLUMNS.format(statuses=statuses)}{extra_sql}\n)")
    select = ", ".join(status_map if c == "status" else c for c in keep)
    conn.execute(f"INSERT INTO approval_queue_rebuild ({', '.join(keep)}) SELECT {select} FROM approval_queue")
    conn.execute("DROP TABLE approval_queue")
    conn.execute("ALTER TABLE approval_queue_rebuild RENAME TO approval_queue")
    for statement in _INDEXES:
        conn.execute(statement)


def up(conn: sqlite3.Connection) -> None:
    """Add the execution/decision columns and the 'answered' status (idempotent)."""
    if not _table_sql(conn):
        return
    if "'answered'" not in _table_sql(conn):
        _rebuild(conn, STATUSES_NEW, COLUMNS)
    existing = set(_existing_columns(conn))
    for name, sql_type in COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE approval_queue ADD COLUMN {name} {sql_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_session ON approval_queue(session_ref, status)")


def down(conn: sqlite3.Connection) -> None:
    """Restore the pre-007 table: no execution columns; 'answered' rows become 'approved'."""
    if not _table_sql(conn):
        return
    conn.execute("DROP INDEX IF EXISTS idx_approval_session")
    _rebuild(
        conn,
        STATUSES_OLD,
        {},
        status_map="CASE WHEN status = 'answered' THEN 'approved' ELSE status END",
    )
