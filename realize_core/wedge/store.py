"""Wedge run records for the funnel (STORY-46). Counts come from observed events only.

Only counts and the market are stored, never the tender text. Rows are kept for
30 days unless the user opts in to being contacted.

A call request lands in the owner's contact queue (:func:`contacts`), stays
there until someone marks it handled (:func:`mark_contacted`), and is counted
once per person in the funnel: :func:`funnel` reports converted *users*, not
requests, so one person asking twice can't inflate the pass signal (audit N09).
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
    created_at     TEXT NOT NULL,
    call_requested_at TEXT,
    call_handled_at   TEXT,
    call_handled_by   TEXT
);
CREATE INDEX IF NOT EXISTS idx_wedge_runs_user ON wedge_runs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_wedge_runs_market ON wedge_runs(market, created_at);
"""


#: Follow-up columns added after the first release of the table (migration 014).
FOLLOW_UP_COLUMNS = {"call_requested_at": "TEXT", "call_handled_at": "TEXT", "call_handled_by": "TEXT"}
#: The pilot's pass signal (docs/self-serve-wedge.md).
PASS_RATE = 0.30
HOME_MARKET = "il"


class WedgeLimitError(RuntimeError):
    """The user has reached the pilot's daily limit."""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create ``wedge_runs`` and add any follow-up columns an older table lacks."""
    conn.executescript(DDL)
    have = {row[1] for row in conn.execute("PRAGMA table_info(wedge_runs)")}
    for name, kind in FOLLOW_UP_COLUMNS.items():
        if name not in have:
            conn.execute(f"ALTER TABLE wedge_runs ADD COLUMN {name} {kind}")
    conn.commit()


def _conn() -> sqlite3.Connection:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    ensure_schema(conn)
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
    """Put the user in the contact queue after a run. Returns False for an unknown run.

    Asking again (after the same or another run) updates the contact and puts
    the person back in the queue if they had been handled; it never counts twice.
    """
    conn = _conn()
    try:
        cur = conn.execute(
            """UPDATE wedge_runs
               SET call_requested = 1, contact = ?, opt_in = ?,
                   call_requested_at = ?, call_handled_at = NULL, call_handled_by = NULL
               WHERE id = ? AND user_id = ?""",
            (contact[:200], 1 if opt_in else 0, _now().isoformat(), run_id, user_id),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def contacts(*, include_handled: bool = False) -> list[dict]:
    """The owner's contact queue: one row per person who asked for a call.

    Each row has the person's latest contact, the markets they ran, how many
    of their runs asked for a call, when they first and last asked, and when
    they were handled (None while waiting). Oldest waiting request first.
    """
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT user_id,
                      GROUP_CONCAT(DISTINCT market) AS markets,
                      COUNT(*) AS requests,
                      MIN(COALESCE(call_requested_at, created_at)) AS first_requested_at,
                      MAX(COALESCE(call_requested_at, created_at)) AS last_requested_at,
                      MAX(CASE WHEN call_handled_at IS NULL THEN 1 ELSE 0 END) AS waiting,
                      MAX(call_handled_at) AS handled_at
               FROM wedge_runs WHERE call_requested = 1
               GROUP BY user_id ORDER BY waiting DESC, first_requested_at"""
        ).fetchall()
        out = []
        for r in rows:
            if r["waiting"] == 0 and not include_handled:
                continue
            latest = conn.execute(
                """SELECT contact, call_handled_by FROM wedge_runs
                   WHERE user_id = ? AND call_requested = 1
                   ORDER BY COALESCE(call_requested_at, created_at) DESC LIMIT 1""",
                (r["user_id"],),
            ).fetchone()
            out.append(
                {
                    "user_id": r["user_id"],
                    "contact": latest["contact"] if latest else None,
                    "markets": sorted((r["markets"] or "").split(",")) if r["markets"] else [],
                    "requests": r["requests"],
                    "first_requested_at": r["first_requested_at"],
                    "last_requested_at": r["last_requested_at"],
                    "handled_at": None if r["waiting"] else r["handled_at"],
                    "handled_by": None if r["waiting"] else (latest["call_handled_by"] if latest else None),
                }
            )
        return out
    finally:
        conn.close()


def mark_contacted(user_id: str, handled_by: str) -> int:
    """Take a person out of the contact queue. Returns how many of their requests were open."""
    conn = _conn()
    try:
        cur = conn.execute(
            """UPDATE wedge_runs SET call_handled_at = ?, call_handled_by = ?
               WHERE user_id = ? AND call_requested = 1 AND call_handled_at IS NULL""",
            (_now().isoformat(), handled_by[:200], user_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def funnel(days: int = 30) -> list[dict]:
    """Runs, users and conversions per market over the last ``days``.

    ``converted_users`` counts people who asked for a call (each once);
    ``call_rate`` is ``converted_users / users``. ``calls_requested`` is the
    number of runs that asked, a volume figure only.
    """
    conn = _conn()
    try:
        since = (_now() - timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT market, COUNT(*) AS runs, COUNT(DISTINCT user_id) AS users,
                      SUM(call_requested) AS calls,
                      COUNT(DISTINCT CASE WHEN call_requested = 1 THEN user_id END) AS converted,
                      AVG(verification) AS avg_level
               FROM wedge_runs WHERE created_at > ? GROUP BY market ORDER BY runs DESC""",
            (since,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        users = r["users"] or 0
        converted = r["converted"] or 0
        out.append(
            {
                "market": r["market"],
                "runs": r["runs"],
                "users": users,
                "converted_users": converted,
                "calls_requested": r["calls"] or 0,
                "call_rate": round(converted / users, 3) if users else 0.0,
                "avg_verification": round(r["avg_level"] or 0, 2),
            }
        )
    return out


def funnel_summary(days: int = 30) -> dict:
    """The pilot's pass check over the last ``days``, counting each person once across markets.

    Passes when at least :data:`PASS_RATE` of users asked for a call and at
    least one of those ran a market other than :data:`HOME_MARKET`.
    """
    conn = _conn()
    try:
        since = (_now() - timedelta(days=days)).isoformat()
        row = conn.execute(
            """SELECT COUNT(DISTINCT user_id) AS users,
                      COUNT(DISTINCT CASE WHEN call_requested = 1 THEN user_id END) AS converted,
                      COUNT(DISTINCT CASE WHEN call_requested = 1 AND market != ? THEN user_id END) AS abroad
               FROM wedge_runs WHERE created_at > ?""",
            (HOME_MARKET, since),
        ).fetchone()
    finally:
        conn.close()
    users, converted, abroad = row["users"] or 0, row["converted"] or 0, row["abroad"] or 0
    rate = round(converted / users, 3) if users else 0.0
    return {
        "days": days,
        "users": users,
        "converted_users": converted,
        "call_rate": rate,
        "converted_outside_home": abroad,
        "passed": users > 0 and rate >= PASS_RATE and abroad >= 1,
    }


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
