"""Self-serve wedge pilot (STORY-46)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from realize_core.wedge import (
    check_register,
    funnel,
    get_method,
    purge_expired,
    record_run,
    render_register,
    request_call,
)
from realize_core.wedge import store as wedge_store

ITEMS = [
    {
        "statement": "Bank guarantee of 5% of the bid",
        "mandatory": True,
        "category": "financial",
        "sources": [{"source": "tender.pdf", "locator": "p.4"}],
    },
    {
        "statement": "Site visit certificate",
        "mandatory": False,
        "category": "administrative",
        "sources": [{"source": "tender.pdf"}],
    },
    {"statement": "Bank guarantee of 5% of the bid", "mandatory": True, "category": "financial"},
    {"statement": "", "mandatory": True},
    {"statement": "Programme of works", "category": "planning"},
]


@pytest.fixture
def db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


def test_method_without_market_pack_is_level_zero():
    method = get_method("xx")
    assert method["market"]["verification"] == 0
    assert "unverified" in method["market"]["notice"]
    assert method["steps"]
    assert method["register_format"]["max_items"] == 300


def test_method_with_portugal_pack_carries_terms_rules_and_level():
    market = get_method("pt")["market"]
    assert market["verification"] == 1
    assert any(t["term"] == "auto de medição" for t in market["terms"])
    assert all(r["source"].startswith("https://") for r in market["rules"])


def test_check_register_cleans_and_flags():
    checked = check_register(ITEMS)
    assert checked["counts"] == {"items": 3, "mandatory": 2, "without_locator": 2}
    text = " ".join(checked["warnings"])
    assert "duplicate" in text
    assert "no statement" in text
    assert "'planning' is not one of" in text
    assert "mandatory not stated" in text


@pytest.mark.parametrize("bad", [[], [{"statement": ""}], [{"statement": f"x{i}"} for i in range(301)]])
def test_check_register_rejects_unusable_input(bad):
    with pytest.raises(ValueError):
        check_register(bad)


def test_render_shows_level_and_languages():
    checked = check_register(ITEMS)
    en = render_register(checked, market="pt", language="en", title="Tower B")
    assert en.startswith("# Tender requirements register — Tower B")
    assert "verification 1" in en
    assert "tender.pdf p.4" in en
    assert render_register(checked, market=None, language="he").startswith("# מרשם דרישות המכרז")
    assert "unverified" in render_register(checked, market=None, language="pt")


def test_runs_limits_funnel_and_purge(db, monkeypatch):
    first = record_run("u1", market="pt", verification=1, items=10, without_locator=2)
    record_run("u2", market="pt", verification=1, items=5, without_locator=0)
    record_run("u3", market="any", verification=0, items=3, without_locator=3)
    assert request_call(first, "u1", "a@example.com") is True
    assert request_call(first, "someone-else", "x") is False
    stats = {row["market"]: row for row in funnel()}
    assert stats["pt"]["runs"] == 2
    assert stats["pt"]["calls_requested"] == 1
    assert stats["pt"]["call_rate"] == 0.5
    assert stats["any"]["avg_verification"] == 0

    monkeypatch.setattr(wedge_store, "MAX_RUNS_PER_DAY", 1)
    with pytest.raises(wedge_store.WedgeLimitError):
        record_run("u2", market="pt", verification=1, items=1, without_locator=0)

    later = datetime.now(UTC) + timedelta(days=31)
    monkeypatch.setattr(wedge_store, "_now", lambda: later)
    assert purge_expired() == 2  # the opted-in run stays
    assert [r["market"] for r in funnel(days=60)] == ["pt"]


def _state(on: bool):
    return SimpleNamespace(
        config={
            "features": {"wedge": on},
            "wedge": {
                "booking_url": "https://example.com/book",
                "partners": {"pt": {"name": "Partner PT", "url": "https://p.example"}},
            },
        }
    )


def test_tools_are_off_by_default(db):
    from realize_core.mcp_server.tools import wedge_tools

    out = asyncio.run(wedge_tools.tender_register_method({}, _state(False), None))
    assert out["code"] == "MCP_TOOL_DISABLED"


def test_submit_and_call_through_mcp(db):
    from realize_core.mcp_server.tools import wedge_tools

    user = SimpleNamespace(user_id="guest-1")
    state = _state(True)
    out = asyncio.run(
        wedge_tools.tender_register_submit({"items": ITEMS, "market": "pt", "language": "pt"}, state, user)
    )
    assert out["verification"] == 1
    assert out["document"].startswith("# Registo de requisitos do concurso")
    assert out["local_partner"]["name"] == "Partner PT"
    assert out["booking_url"] == "https://example.com/book"
    call = asyncio.run(wedge_tools.request_audit_call({"run_id": out["run_id"], "contact": "+351 900"}, state, user))
    assert call["status"] == "requested"
    bad = asyncio.run(wedge_tools.tender_register_submit({"items": []}, state, user))
    assert bad["code"] == "MCP_VALIDATION"


def test_wedge_tools_registered_and_allowed_for_scoped_callers():
    from realize_core.config import get_features
    from realize_core.mcp_server import registry, venture_guard

    assert get_features({})["wedge"] is False
    registry.reset_for_tests()
    reg = registry.get_registry()
    for name in ("tender_register_method", "tender_register_submit", "request_audit_call"):
        assert reg.get(name).family == "chat"
        assert name in venture_guard.ALWAYS_ALLOWED
        assert venture_guard.TOOL_PERMISSIONS[name] == "system:read"
