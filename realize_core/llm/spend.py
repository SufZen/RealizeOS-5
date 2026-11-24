"""
Monthly LLM spend cap, shared by every process that uses the same data folder.

The hourly limit in ``router.py`` lives in process memory, so the API and each
bot keep their own window and none of them sees the others' spend. The monthly
cap is kept in SQLite instead (table ``llm_spend`` in ``memory.db``), so every
process that shares ``DATA_PATH`` checks one total.

``COST_LIMIT_PER_MONTH_USD`` turns it on; 0 (the default) leaves it off. The
month is the calendar month in UTC. Spend is counted from the moment the cap is
on: while it is off nothing is written.

The router records the cost of every call it routes (``_record_cost``), so
calls made directly to a provider outside the router are not counted.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

WARN_FRACTION = 0.8  # log a warning once a month when spend passes this share of the cap
_CACHE_SECONDS = 5.0  # how long a read of the month's total is reused within one process

_lock = threading.Lock()
_cache: tuple[float, float, float] | None = None  # (month_start, total, read_at)
_warned_month: float | None = None
_table_ready_for: str | None = None


def monthly_limit_usd() -> float:
    """The configured cap in USD; 0 or less means the cap is off."""
    from realize_core import config

    return float(getattr(config, "COST_LIMIT_PER_MONTH_USD", 0.0) or 0.0)


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
    global _cache
    if cost_usd <= 0 or monthly_limit_usd() <= 0:
        return
    from realize_core.memory.store import db_connection

    at = time.time() if now is None else now
    try:
        with db_connection() as conn:
            _ensure_table(conn)
            conn.execute("INSERT INTO llm_spend (created_at, cost_usd) VALUES (?, ?)", (at, cost_usd))
    except Exception as e:
        logger.error(f"Monthly spend not recorded (${cost_usd:.4f}): {e}")
        return
    with _lock:
        if _cache is not None and _cache[0] == month_start(at):
            _cache = (_cache[0], _cache[1] + cost_usd, _cache[2])


def month_spend(now: float | None = None) -> float:
    """Total recorded spend in USD for the current UTC month, across all processes."""
    global _cache
    at = time.time() if now is None else now
    start = month_start(at)
    with _lock:
        if _cache is not None and _cache[0] == start and at - _cache[2] < _CACHE_SECONDS:
            return _cache[1]
    from realize_core.memory.store import db_connection

    with db_connection() as conn:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_spend WHERE created_at >= ?", (start,)
        ).fetchone()
    total = float(row[0] or 0.0)
    with _lock:
        _cache = (start, total, at)
    return total


def check_monthly_limit(now: float | None = None) -> bool:
    """True while this month's spend is under the cap (or the cap is off).

    A database error is logged and the call is allowed: the cap must not take the
    whole system down when the spend table cannot be read.
    """
    global _warned_month
    limit = monthly_limit_usd()
    if limit <= 0:
        return True
    try:
        total = month_spend(now)
    except Exception as e:
        logger.error(f"Monthly spend could not be read; allowing the call: {e}")
        return True
    if total >= limit:
        logger.warning(f"Monthly cost limit reached: ${total:.4f} >= ${limit:.2f}/month")
        return False
    start = month_start(now)
    if total >= WARN_FRACTION * limit and _warned_month != start:
        _warned_month = start
        logger.warning(f"Monthly LLM spend at ${total:.2f} of ${limit:.2f} ({total / limit:.0%})")
    return True


def reset_cache() -> None:
    """Forget cached totals (tests, or after the data folder changes)."""
    global _cache, _warned_month, _table_ready_for
    with _lock:
        _cache = None
    _warned_month = None
    _table_ready_for = None
