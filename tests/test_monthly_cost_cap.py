"""Monthly LLM spend cap (COST_LIMIT_PER_MONTH_USD), shared through SQLite."""

from datetime import UTC, datetime

import pytest
from realize_core.llm import router, spend


@pytest.fixture
def cap(monkeypatch, tmp_path):
    """A fresh memory.db, an empty hourly window and a $20 monthly cap."""
    monkeypatch.setattr("realize_core.memory.store.DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr("realize_core.config.COST_LIMIT_PER_MONTH_USD", 20.0)
    monkeypatch.setattr("realize_core.config.COST_LIMIT_PER_HOUR_USD", 1000.0)
    monkeypatch.setattr(spend, "_CACHE_SECONDS", 0.0)
    router._cost_window.clear()
    spend.reset_cache()
    yield
    router._cost_window.clear()
    spend.reset_cache()


def _ts(year, month, day, hour=12):
    return datetime(year, month, day, hour, tzinfo=UTC).timestamp()


def test_off_by_default_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr("realize_core.memory.store.DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr("realize_core.config.COST_LIMIT_PER_MONTH_USD", 0.0)
    spend.reset_cache()
    spend.record_spend(50.0)
    assert spend.check_monthly_limit() is True
    assert not (tmp_path / "memory.db").exists()


def test_blocks_once_the_month_reaches_the_cap(cap):
    now = _ts(2026, 11, 24)
    spend.record_spend(12.0, now=now)
    assert spend.check_monthly_limit(now) is True
    spend.record_spend(8.0, now=now)
    assert spend.month_spend(now) == pytest.approx(20.0)
    assert spend.check_monthly_limit(now) is False


def test_new_month_starts_from_zero(cap):
    spend.record_spend(25.0, now=_ts(2026, 11, 30, 23))
    assert spend.check_monthly_limit(_ts(2026, 11, 30, 23)) is False
    assert spend.check_monthly_limit(_ts(2026, 12, 1, 0)) is True
    assert spend.month_spend(_ts(2026, 12, 1, 0)) == 0.0


def test_month_start_is_utc_first_day():
    assert spend.month_start(_ts(2026, 11, 24, 15)) == _ts(2026, 11, 1, 0)


def test_total_is_shared_through_the_database(cap):
    """Another process writes to the same memory.db; this process sees it."""
    from realize_core.memory.store import db_connection

    now = _ts(2026, 11, 24)
    spend.month_spend(now)  # creates the table, as any process would
    with db_connection() as conn:
        conn.execute("INSERT INTO llm_spend (created_at, cost_usd) VALUES (?, ?)", (now, 21.0))
    assert spend.check_monthly_limit(now) is False


def test_router_records_and_enforces(cap):
    router._record_cost(19.5)
    assert router._check_cost_limit() is True
    router._record_cost(0.6)
    assert router._check_cost_limit() is False


def test_hourly_limit_still_applies_first(cap, monkeypatch):
    monkeypatch.setattr("realize_core.config.COST_LIMIT_PER_HOUR_USD", 1.0)
    router._record_cost(1.0)
    assert router._check_cost_limit() is False
    assert spend.month_spend() == pytest.approx(1.0)


def test_unreadable_database_allows_the_call(cap, monkeypatch):
    def broken():
        raise RuntimeError("disk gone")

    monkeypatch.setattr(spend, "month_spend", lambda now=None: broken())
    assert spend.check_monthly_limit() is True


async def test_route_returns_cost_limited_when_capped(cap, monkeypatch):
    monkeypatch.setattr(router, "_check_rate_limit", lambda: True)
    router._record_cost(20.0)
    response = await router.route_completion(system_prompt="s", messages=[{"role": "user", "content": "hi"}])
    assert response.ok is False
    assert response.error == "cost_limited"
