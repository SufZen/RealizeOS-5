"""
Durable resume points for paused skills (Codex audit F10 / F17).

A skill pauses at a human step (waiting for an answer) or at a tool step the
governance gate held (waiting for an approval). Its resume point used to live
in a per-user dict: a second paused skill overwrote the first and a restart
lost both. Each resume point is now a row in ``skill_runs`` keyed by its own
id, linked to the approval item that resumes it, and claimed with one
DELETE so it can be resumed at most once.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS skill_runs (
    id             TEXT PRIMARY KEY,
    approval_id    TEXT,
    user_id        TEXT NOT NULL,
    system_key     TEXT NOT NULL,
    skill_name     TEXT NOT NULL,
    step_id        TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK(kind IN ('human', 'tool')),
    context_json   TEXT NOT NULL,
    remaining_json TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_runs_user ON skill_runs(user_id, system_key, kind, created_at);
CREATE INDEX IF NOT EXISTS idx_skill_runs_approval ON skill_runs(approval_id);
"""


def _conn() -> sqlite3.Connection:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    conn.executescript(DDL)
    return conn


def save(
    run_id: str,
    *,
    approval_id: str | None,
    user_id: str,
    system_key: str,
    skill_name: str,
    step_id: str,
    kind: str,
    context: dict[str, Any],
    remaining_steps: list,
) -> None:
    """Store a resume point."""
    conn = _conn()
    try:
        conn.execute(
            """INSERT INTO skill_runs
               (id, approval_id, user_id, system_key, skill_name, step_id, kind,
                context_json, remaining_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                approval_id,
                user_id,
                system_key,
                skill_name,
                step_id,
                kind,
                json.dumps(context, default=str),
                json.dumps(remaining_steps, default=str),
                datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    out["context"] = json.loads(out.pop("context_json"))
    out["remaining_steps"] = json.loads(out.pop("remaining_json"))
    return out


def find(
    *,
    run_id: str | None = None,
    approval_id: str | None = None,
    user_id: str | None = None,
    system_key: str | None = None,
    kind: str | None = None,
) -> dict[str, Any] | None:
    """The newest resume point matching every given filter, or None."""
    clauses, params = [], []
    for column, value in (
        ("id", run_id),
        ("approval_id", approval_id),
        ("user_id", user_id),
        ("system_key", system_key),
        ("kind", kind),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if not clauses:
        return None
    conn = _conn()
    try:
        row = conn.execute(
            f"SELECT * FROM skill_runs WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT 1", params
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def claim(run_id: str) -> dict[str, Any] | None:
    """Remove and return a resume point; None if it is gone (already resumed or stopped)."""
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM skill_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        cur = conn.execute("DELETE FROM skill_runs WHERE id = ?", (run_id,))
        conn.commit()
        if cur.rowcount != 1:
            return None  # someone else claimed it between the read and the delete
        return _row_to_dict(row)
    finally:
        conn.close()
