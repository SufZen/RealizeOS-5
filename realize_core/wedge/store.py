"""Wedge run records for the funnel (STORY-46). Counts come from observed events only.

Only counts and the market are stored, never the tender text. Rows are kept for
30 days unless the user opts in to being contacted.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30
MAX_RUNS_PER_DAY = 10

DDL = """
CREATE TABLE IF NOT EXISTS wedge_runs (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    market         TEXT NOT NULL,
    verification   INTEGER NOT NULL,
    items          INTEGER NOT NULL,
    without_locator INTEGER NOT NULL,
    call_requested INTEGER NOT NULL DEFAULT 0,
    contact        TEXT,
    opt_in         INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wedge_runs_user ON wedge_runs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_wedge_runs_market ON wedge_runs(market, created_at);
"""


class WedgeLimitError(RuntimeError):
    """The user has reached the pilot's daily limit."""


def _conn() -> sqlite3.Connection:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    conn.executescript(DDL)
    return conn


def _now() -> datetime:
    return datetime.now(UTC)


def record_run(user_id: str, *, market: str, verification: int, items: int, without_locator: int) -> str:
    """Record one register run. Raises WedgeLimitError over the daily limit."""
    conn = _conn()
    try:
        since = (_now() - timedelta(days=1)).isoformat()
        used = conn.execute(
            "SELECT COUNT(*) FROM wedge_runs WHERE user_id = ? AND created_at > ?", (user_id, since)
        ).fetchone()[0]
        if used >= MAX_RUNS_PER_DAY:
            raise WedgeLimitError(f"The free pilot allows {MAX_RUNS_PER_DAY} registers a day")
        run_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO wedge_runs (id, user_id, market, verification, items, without_locator, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, user_id, market, verification, items, without_locator, _now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def request_call(run_id: str, user_id: str, contact: str, *, opt_in: bool = True) -> bool:
    """Mark that the user asked for a call after a run. Returns False for an unknown run."""
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE wedge_runs SET call_requested = 1, contact = ?, opt_in = ? WHERE id = ? AND user_id = ?",
            (contact[:200], 1 if opt_in else 0, run_id, user_id),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def funnel(days: int = 30) -> list[dict]:
    """Runs and call requests per market over the last ``days``."""
    conn = _conn()
    try:
        since = (_now() - timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT market, COUNT(*) AS runs, COUNT(DISTINCT user_id) AS users,
                      SUM(call_requested) AS calls, AVG(verification) AS avg_level
               FROM wedge_runs WHERE created_at > ? GROUP BY market ORDER BY runs DESC""",
            (since,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        users = r["users"] or 0
        calls = r["calls"] or 0
        out.append(
            {
                "market": r["market"],
                "runs": r["runs"],
                "users": users,
                "calls_requested": calls,
                "call_rate": round(calls / users, 3) if users else 0.0,
                "avg_verification": round(r["avg_level"] or 0, 2),
            }
        )
    return out


def purge_expired(days: int = RETENTION_DAYS) -> int:
    """Delete runs older than ``days`` unless the user opted in. Returns rows deleted."""
    conn = _conn()
    try:
        cutoff = (_now() - timedelta(days=days)).isoformat()
        cur = conn.execute("DELETE FROM wedge_runs WHERE created_at < ? AND opt_in = 0", (cutoff,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
