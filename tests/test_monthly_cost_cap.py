"""Monthly LLM spend cap (COST_LIMIT_PER_MONTH_USD), shared through SQLite."""

from datetime import UTC, datetime

import pytest
from realize_core.llm import router, spend
from realize_core.llm.base_provider import BaseLLMProvider, LLMResponse


@pytest.fixture
def cap(monkeypatch, tmp_path):
    """A fresh memory.db, an empty hourly window and a $20 monthly cap."""
    monkeypatch.setattr("realize_core.memory.store.DB_PATH", tmp_path / "memory.db")
    monkeypatch.setenv("COST_LIMIT_PER_MONTH_USD", "20")
    monkeypatch.setattr("realize_core.config.COST_LIMIT_PER_HOUR_USD", 1000.0)
    router._cost_window.clear()
    spend.reset_cache()
    yield
    router._cost_window.clear()
    spend.reset_cache()


def _ts(year, month, day, hour=12):
    return datetime(year, month, day, hour, tzinfo=UTC).timestamp()


class _Provider(BaseLLMProvider):
    def __init__(self, name, billable, cost=0.0, error=None):
        self._name, self.billable, self.cost, self.calls, self.error = name, billable, cost, 0, error

    @property
    def name(self):
        return self._name

    async def complete(self, system_prompt, messages, model=None, **kw):
        self.calls += 1
        return LLMResponse(text=self._name, model="m", provider=self._name, cost_usd=self.cost, error=self.error)

    def list_models(self):
        return []


def _registry(monkeypatch, *providers):
    from realize_core.llm.registry import ProviderRegistry

    registry = ProviderRegistry()
    for p in providers:
        registry.register(p)
    registry.set_fallback_chain([p.name for p in providers])
    for tier in ("FAST", "STANDARD", "DEEP"):
        monkeypatch.delenv(f"LLM_MODEL_{tier}", raising=False)
    monkeypatch.setenv("LLM_PRIMARY", providers[0].name)
    monkeypatch.setattr("realize_core.llm.registry.get_registry", lambda: registry)
    monkeypatch.setattr(router, "_check_rate_limit", lambda: True)


# --- the ledger ------------------------------------------------------------------


def test_off_by_default_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr("realize_core.memory.store.DB_PATH", tmp_path / "memory.db")
    monkeypatch.delenv("COST_LIMIT_PER_MONTH_USD", raising=False)
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
    """Another process writes to the same memory.db; the next check sees it."""
    from realize_core.memory.store import db_connection

    now = _ts(2026, 11, 24)
    assert spend.check_monthly_limit(now) is True  # creates the table, as any process would
    with db_connection() as conn:
        conn.execute("INSERT INTO llm_spend (created_at, cost_usd) VALUES (?, ?)", (now, 21.0))
    assert spend.check_monthly_limit(now) is False


def test_unreadable_ledger_blocks_paid_calls(cap, monkeypatch):
    def broken(now=None):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(spend, "month_spend", broken)
    assert spend.check_monthly_limit() is False


@pytest.mark.parametrize("value", ["nan", "-5", "twenty", "inf"])
def test_invalid_setting_blocks_instead_of_lifting_the_cap(cap, monkeypatch, value):
    monkeypatch.setenv("COST_LIMIT_PER_MONTH_USD", value)
    assert spend.check_monthly_limit() is False


def test_setting_is_read_live(cap, monkeypatch):
    spend.record_spend(30.0)
    assert spend.check_monthly_limit() is False
    monkeypatch.setenv("COST_LIMIT_PER_MONTH_USD", "50")
    assert spend.check_monthly_limit() is True


# --- routing -----------------------------------------------------------------------


def test_router_records_spend(cap):
    router._record_cost(0.25)
    assert spend.month_spend() == pytest.approx(0.25)


async def test_cap_stops_paid_provider_but_not_the_free_one(cap, monkeypatch):
    free = _Provider("chatgpt_plan", billable=False)
    paid = _Provider("gemini", billable=True, cost=0.01)
    _registry(monkeypatch, free, paid)
    spend.record_spend(20.0)

    response = await router.route_completion("s", [{"role": "user", "content": "q"}], tier="standard")
    assert response.text == "chatgpt_plan"
    assert free.calls == 1


async def test_capped_fallback_is_skipped_with_a_cost_message(cap, monkeypatch):
    paid = _Provider("gemini", billable=True, cost=0.01)
    _registry(monkeypatch, paid)
    spend.record_spend(20.0)

    response = await router.route_completion("s", [{"role": "user", "content": "q"}], tier="standard")
    assert response.ok is False
    assert response.error == "cost_limited"
    assert paid.calls == 0


async def test_under_the_cap_paid_calls_go_through_and_are_counted(cap, monkeypatch):
    paid = _Provider("gemini", billable=True, cost=0.5)
    _registry(monkeypatch, paid)
    response = await router.route_completion("s", [{"role": "user", "content": "q"}], tier="standard")
    assert response.ok
    assert spend.month_spend() == pytest.approx(0.5)


def test_hourly_limit_is_unchanged(cap, monkeypatch):
    monkeypatch.setattr("realize_core.config.COST_LIMIT_PER_HOUR_USD", 1.0)
    router._record_cost(1.0)
    assert router._check_cost_limit() is False


def test_empty_setting_means_off(cap, monkeypatch):
    monkeypatch.setenv("COST_LIMIT_PER_MONTH_USD", "")
    spend.record_spend(100.0)
    assert spend.check_monthly_limit() is True


async def test_a_billed_failure_is_still_counted(cap, monkeypatch):
    broken = _Provider("claude", billable=True, cost=0.3, error="empty response")
    ok = _Provider("gemini", billable=True, cost=0.1)
    _registry(monkeypatch, broken, ok)
    response = await router.route_completion("s", [{"role": "user", "content": "q"}], tier="standard")
    assert response.text == "gemini"
    assert spend.month_spend() == pytest.approx(0.4)


async def test_capped_providers_do_not_use_up_retries(cap, monkeypatch):
    paid = [_Provider(n, billable=True, cost=0.01) for n in ("claude", "gemini", "openai", "litellm")]
    local = _Provider("ollama", billable=False)
    _registry(monkeypatch, *paid, local)
    spend.record_spend(20.0)
    response = await router.route_completion("s", [{"role": "user", "content": "q"}], tier="standard")
    assert response.text == "ollama"
    assert all(p.calls == 0 for p in paid)
