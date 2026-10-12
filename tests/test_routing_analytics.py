"""
Codex audit F19: Routing Analytics shows real routing, in the shape the page reads.

Only the routing *test* endpoint recorded anything, the API returned
entries/total/agent_distribution while the page read decisions/agent_stats
and friends (so it showed zeros), and the time range was never sent.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def log(monkeypatch):
    from realize_core.agents import routing_log

    routing_log.DECISIONS.clear()
    yield routing_log
    routing_log.DECISIONS.clear()


@pytest.fixture
def engine(monkeypatch):
    import realize_core.base_handler as bh

    async def fake_standard(**kwargs):
        return "ok"

    async def no_skill(**kwargs):
        return False, None

    monkeypatch.setattr(bh, "standard_llm_handling", fake_standard)
    monkeypatch.setattr(bh, "check_and_execute_skill", no_skill)
    return bh


SYSTEM = {"agents": {"writer": "w.md", "analyst": "a.md"}, "agent_routing": {"analyst": ["analyze"]}}


@pytest.mark.asyncio
async def test_real_chat_routing_is_recorded_without_the_message(log, engine):
    await engine.process_message("acme", "u1", "please analyze the budget", system_config=SYSTEM)
    await engine.process_message("acme", "u1", "hello", system_config=SYSTEM, requested_agent="writer")
    await engine.process_message("acme", "u1", "hello there", system_config=SYSTEM)

    methods = [(d["selected_agent"], d["method"]) for d in log.DECISIONS]
    assert methods == [("analyst", "keyword"), ("writer", "requested"), ("orchestrator", "default")]
    assert all(d["message_preview"] == "" for d in log.DECISIONS)
    assert all(d["system_key"] == "acme" and d["timestamp"] for d in log.DECISIONS)


@pytest.mark.asyncio
async def test_paused_agent_is_recorded_as_a_fallback(log, engine, monkeypatch):
    from realize_core.scheduler import lifecycle

    monkeypatch.setattr(lifecycle, "is_paused", lambda agent, system: agent == "writer")
    monkeypatch.setattr(lifecycle, "mark_running", lambda *a, **k: None)
    monkeypatch.setattr(lifecycle, "mark_idle", lambda *a, **k: None, raising=False)

    await engine.process_message(
        "acme", "u1", "hi", system_config=SYSTEM, requested_agent="writer", features={"agent_lifecycle": True}
    )

    assert log.DECISIONS[-1]["selected_agent"] == "orchestrator"
    assert log.DECISIONS[-1]["method"] == "fallback"


def test_analytics_shape_and_time_filter(log):
    from realize_api.routes import routing

    log.record_decision("acme", "writer", "requested")
    log.record_decision("acme", "writer", "fallback")
    old = log.record_decision("acme", "analyst", "keyword")
    old["timestamp"] = (datetime.now(UTC) - timedelta(days=3)).isoformat()

    app = FastAPI()
    app.include_router(routing.router, prefix="/api")
    client = TestClient(app)

    body = client.get("/api/routing/analytics?hours=24").json()

    assert body["total_decisions"] == 2
    assert [d["selected_agent"] for d in body["decisions"]] == ["writer", "writer"]
    assert body["agent_stats"] == [{"agent_key": "writer", "total_calls": 2, "fallback_rate": 0.5}]
    assert body["method_counts"] == {"requested": 1, "fallback": 1}
    assert client.get("/api/routing/analytics").json()["total_decisions"] == 3
