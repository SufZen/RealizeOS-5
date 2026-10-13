"""Codex audit N03 — rule-card provenance survives the whole answer trail.

A pack rule card ([R1]…) carries its layer, pack, verification level and
dates from the resolver through the recorder, storage, REST, SSE, history
and the MCP trail summary, so the level can be shown on every answer
whatever the model wrote. KB sources ([S1]…) keep their plain shape, and
trails stored before provenance existed still load.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    """Isolated memory.db (conversations + chat_trail) with an empty cache."""
    from realize_core.memory.conversation import clear_all
    from realize_core.memory.store import init_db

    monkeypatch.setattr("realize_core.memory.store.DB_PATH", tmp_path / "memory.db")
    init_db()
    clear_all()
    yield tmp_path / "memory.db"
    clear_all()


@pytest.fixture
def client(memory_db):
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = {"acme": {"name": "Acme"}}
    app.state.config = {"features": {}}
    return TestClient(app)


def _write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _card(rid: str, statement: str, *, level: int, review_by: str | None) -> str:
    meta = {
        "id": rid,
        "statement": statement,
        "source": f"https://example.org/{rid}",
        "as_of": "2026-10-13",
        "verification": level,
        "applies_to": {"family": "money-event", "kinds": ["payment_claim"]},
    }
    if review_by:
        meta["review_by"] = review_by
    return "---\n" + yaml.safe_dump(meta, allow_unicode=True) + "---\nHow to use it.\n"


@pytest.fixture
def pack_sources(tmp_path) -> list[dict]:
    """Source records the real resolver emits for a Portugal market pack at level 1."""
    from realize_core.packs import PackResolver, build_pack_context, clear_cache

    root = tmp_path / "packs"
    pt = root / "market" / "pt"
    _write_yaml(
        pt / "pack.yaml",
        {"id": "pt", "kind": "market", "version": "0.1.0", "title": "Portugal", "verification": {"level": 1}},
    )
    (pt / "rules").mkdir(parents=True)
    (pt / "rules" / "revision.md").write_text(
        _card("pt.price-revision", "Public works contracts include price revision.", level=2, review_by="2099-04-13"),
        encoding="utf-8",
    )
    venture = tmp_path / "systems" / "acme"
    _write_yaml(venture / "packs.yaml", {"market": [{"id": "pt"}]})

    clear_cache()
    sources: list[dict] = []
    build_pack_context(PackResolver(venture, enabled=True, packs_root=root), "price revision", sources)
    clear_cache()
    return sources


KB_SOURCE = {"id": "S1", "title": "Budget", "path": "b.md"}


def _rule_event(pack_sources: list[dict]) -> dict:
    return {"type": "source", **pack_sources[0]}


def _scripted_process(events: list[dict], reply: str = "Price revision applies [R1]; budget 900k [S1]."):
    """A process_message stand-in that emits trail events and stores the reply."""

    async def fake_process_message(**kwargs):
        from realize_core.memory.conversation import add_message

        emit = kwargs["emit"]
        for e in events:
            await emit(e)
        add_message(kwargs["system_key"], kwargs["user_id"], "user", kwargs["message"])
        msg_id = add_message(kwargs["system_key"], kwargs["user_id"], "assistant", reply)
        await emit({"type": "message_saved", "message_id": msg_id})
        return reply

    return fake_process_message


def _sse_events(body: str) -> list[dict]:
    return [json.loads(line[len("data: ") :]) for line in body.splitlines() if line.startswith("data: ")]


EXPECTED_RULE = {
    "id": "R1",
    "title": "Public works contracts include price revision.",
    "path": "https://example.org/pt.price-revision",
    "layer": "market",
    "pack": "pt@0.1.0",
    # The card says 2; the pack is still a draft, so the lower level wins.
    "verification": 1,
    "as_of": "2026-10-13",
    "review_by": "2099-04-13",
}


# ---------------------------------------------------------------------------
# Resolver and recorder
# ---------------------------------------------------------------------------


def test_resolver_reports_provenance_and_dates(pack_sources):
    assert pack_sources == [EXPECTED_RULE]


@pytest.mark.asyncio
async def test_recorder_keeps_rule_provenance_and_plain_kb_sources(pack_sources):
    from realize_core.agents.trail import TrailRecorder

    forwarded: list[dict] = []
    rec = TrailRecorder(forward=forwarded.append)
    await rec({"type": "source", **KB_SOURCE})
    await rec(_rule_event(pack_sources))

    assert rec.sources == [KB_SOURCE, EXPECTED_RULE]
    assert rec.stored()["sources"] == [KB_SOURCE, EXPECTED_RULE]
    # Live listeners get the same shape.
    assert forwarded == [{"type": "source", **KB_SOURCE}, {"type": "source", **EXPECTED_RULE}]


@pytest.mark.asyncio
async def test_recorder_leaves_out_absent_provenance_and_clamps_levels():
    from realize_core.agents.trail import TrailRecorder

    rec = TrailRecorder()
    await rec({"type": "source", "id": "R1", "title": "firm rule", "path": "x", "layer": "firm", "pack": None})
    await rec({"type": "source", "id": "R2", "title": "t", "path": "p", "verification": "3", "review_by": None})
    await rec({"type": "source", "id": "R3", "title": "t", "path": "p", "verification": 9})
    await rec({"type": "source", "id": "R4", "title": "t", "path": "p", "verification": True})

    assert rec.sources[0] == {"id": "R1", "title": "firm rule", "path": "x", "layer": "firm"}
    assert rec.sources[1] == {"id": "R2", "title": "t", "path": "p", "verification": 3}
    assert rec.sources[2]["verification"] == 4
    assert "verification" not in rec.sources[3]


def test_mcp_summary_keeps_provenance(pack_sources):
    from realize_core.agents.trail import trail_summary

    summary = trail_summary({"sources": [KB_SOURCE, pack_sources[0]], "steps": []})
    assert summary["sources"] == [KB_SOURCE, EXPECTED_RULE]


# ---------------------------------------------------------------------------
# REST, SSE, history, MCP
# ---------------------------------------------------------------------------


def test_chat_response_and_history_carry_provenance(client, monkeypatch, pack_sources):
    import realize_core.base_handler as bh

    events = [{"type": "source", **KB_SOURCE}, _rule_event(pack_sources)]
    monkeypatch.setattr(bh, "process_message", _scripted_process(events))

    body = client.post("/api/chat", json={"message": "Price revision?", "system_key": "acme", "user_id": "u1"}).json()

    # KB sources stay id/title/path only; the rule card keeps its provenance.
    assert body["trail"]["sources"] == [KB_SOURCE, EXPECTED_RULE]

    history = client.get("/api/conversations/acme/u1").json()["messages"]
    restored = next(m for m in history if m.get("id") == body["message_id"])
    assert restored["trail"]["sources"] == [KB_SOURCE, EXPECTED_RULE]


def test_stream_events_and_final_carry_provenance(client, monkeypatch, pack_sources):
    import realize_core.base_handler as bh

    events = [{"type": "source", **KB_SOURCE}, _rule_event(pack_sources)]
    monkeypatch.setattr(bh, "process_message", _scripted_process(events))

    resp = client.post("/api/chat/stream", json={"message": "Price revision?", "system_key": "acme", "user_id": "u1"})

    streamed = _sse_events(resp.text)
    assert [e["type"] for e in streamed] == ["source", "source", "final"]
    assert streamed[0] == {"type": "source", **KB_SOURCE}
    assert streamed[1] == {"type": "source", **EXPECTED_RULE}
    assert streamed[-1]["trail"]["sources"] == [KB_SOURCE, EXPECTED_RULE]


@pytest.mark.asyncio
async def test_mcp_chat_summary_carries_provenance(memory_db, monkeypatch, pack_sources):
    import realize_core.base_handler as bh
    from realize_core.mcp_server.tools.chat_tools import realize_chat

    monkeypatch.setattr(bh, "process_message", _scripted_process([_rule_event(pack_sources)]))
    app_state = SimpleNamespace(systems={"acme": {"name": "Acme"}}, config={"features": {}}, kb_path=None)

    out = await realize_chat(
        {"message": "Price revision?", "system_key": "acme"}, app_state=app_state, user=SimpleNamespace(user_id="u1")
    )

    assert out["trail"]["sources"] == [EXPECTED_RULE]


def test_trail_stored_before_provenance_still_loads(client):
    """Rows written before N03 have id/title/path only; history returns them unchanged."""
    from realize_core.memory.conversation import add_message, save_trail

    msg_id = add_message("acme", "u1", "assistant", "Rule applies [R1]")
    legacy = {"sources": [{"id": "R1", "title": "rule", "path": "https://example.test"}], "steps": []}
    save_trail(msg_id, legacy)

    history = client.get("/api/conversations/acme/u1").json()["messages"]
    assert history[-1]["trail"] == legacy


def test_trail_model_accepts_legacy_and_rejects_off_ladder_levels():
    from pydantic import ValidationError
    from realize_api.routes.chat import Trail

    legacy = Trail(sources=[{"id": "R1", "title": "rule", "path": "p"}])
    assert legacy.model_dump()["sources"] == [{"id": "R1", "title": "rule", "path": "p"}]
    with pytest.raises(ValidationError):
        Trail(sources=[{"id": "R1", "title": "rule", "path": "p", "verification": 7}])
