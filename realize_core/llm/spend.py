"""
Monthly LLM spend cap, shared by every process that uses the same data folder.

The hourly limit in ``router.py`` lives in process memory, so the API and each
bot keep their own window and none of them sees the others' spend. The monthly
cap is kept in SQLite instead (table ``llm_spend`` in ``memory.db``), so every
process that shares ``DATA_PATH`` checks one total.

``COST_LIMIT_PER_MONTH_USD`` turns it on; 0 (the default) leaves it off. It is
read from the environment on every check, so a value saved in Settings applies
to the API at once; other processes (bots) pick it up when they restart. The
month is the calendar month in UTC. Spend is counted from the moment the cap is
on: while it is off nothing is written.

What it guards: the router checks it before each attempt on a billable
provider (``BaseLLMProvider.billable``), so reaching the cap stops paid calls
while zero-cost providers (a ChatGPT plan, a local Ollama) keep answering.

It is a soft cap: the check and the record are separate steps, so every call
already admitted when the total crosses the cap still finishes and is charged
(the overshoot is bounded by the calls in flight, not by a fixed amount). If the
spend table cannot be read, paid calls are refused; if one write fails, that
charge is logged as an error and missing from the total.
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

WARN_FRACTION = 0.8  # log a warning once a month when spend passes this share of the cap

_warned_month: float | None = None
_table_ready_for: str | None = None


def monthly_limit_usd() -> float:
    """The configured cap in USD; 0 means the cap is off, -1 means the value is invalid.

    Read live from the environment; unset or empty means off. A value that is
    not a finite non-negative number is logged and returned as -1, which blocks
    paid calls: a typo must never mean "no cap".
    """
    raw = (os.getenv("COST_LIMIT_PER_MONTH_USD") or "").strip()
    if not raw:
        return 0.0  # unset or cleared in Setup: off
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value < 0:
        logger.error(f"COST_LIMIT_PER_MONTH_USD={raw!r} is not a valid amount; paid LLM calls are blocked")
        return -1.0
    return value


def month_start(now: float | None = None) -> float:
    """Epoch seconds of 00:00 UTC on the first day of the month that contains ``now``."""
    moment = datetime.fromtimestamp(time.time() if now is None else now, tz=UTC)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()


def _ensure_table(conn) -> None:
    global _table_ready_for
    from realize_core.memory.store import _resolve_db_path

    db = str(_resolve_db_path())
    if _table_ready_for == db:
        return
    conn.execute(
        "CREATE TABLE IF NOT EXISTS llm_spend ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, cost_usd REAL NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_spend_created_at ON llm_spend(created_at)")
    _table_ready_for = db


def record_spend(cost_usd: float, now: float | None = None) -> None:
    """Add one call's cost to this month's total. Does nothing while the cap is off."""
    if cost_usd <= 0 or monthly_limit_usd() == 0:
        return
    from realize_core.memory.store import db_connection

    at = time.time() if now is None else now
    try:
        with db_connection() as conn:
            _ensure_table(conn)
            conn.execute("INSERT INTO llm_spend (created_at, cost_usd) VALUES (?, ?)", (at, cost_usd))
    except Exception as e:
        logger.error(f"Monthly spend not recorded (${cost_usd:.4f}): {e}")


def month_spend(now: float | None = None) -> float:
    """Total recorded spend in USD for the current UTC month, across all processes."""
    from realize_core.memory.store import db_connection

    start = month_start(now)
    with db_connection() as conn:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_spend WHERE created_at >= ?", (start,)
        ).fetchone()
    return float(row[0] or 0.0)


def check_monthly_limit(now: float | None = None) -> bool:
    """True while this month's spend is under the cap (or the cap is off).

    Call it only before a billable call. When the spend table cannot be read the
    answer is False: the cap must not silently stop guarding.
    """
    global _warned_month
    limit = monthly_limit_usd()
    if limit == 0:
        return True
    if limit < 0:
        return False
    try:
        total = month_spend(now)
    except Exception as e:
        logger.error(f"Monthly spend could not be read; refusing the paid call: {e}")
        return False
    if total >= limit:
        logger.warning(f"Monthly cost limit reached: ${total:.4f} >= ${limit:.2f}/month")
        return False
    start = month_start(now)
    if total >= WARN_FRACTION * limit and _warned_month != start:
        _warned_month = start
        logger.warning(f"Monthly LLM spend at ${total:.2f} of ${limit:.2f} ({total / limit:.0%})")
    return True


def reset_cache() -> None:
    """Forget per-process state (tests, or after the data folder changes)."""
    global _warned_month, _table_ready_for
    _warned_month = None
    _table_ready_for = None
