"""Cross-provider parity: every feature works on every LLM provider, none is required.

Each test runs once per wire shape (``fake_llm``: anthropic, openai, gemini,
ollama). Only that shape's REAL provider adapter is registered, and only its
transport is mocked (the anthropic client, or ``litellm.acompletion`` plus
Ollama's ``/api/tags`` and ``/api/show``), so request building, response
parsing, routing and fallback all run for real. See ``tests/fakes/llm.py``.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import litellm  # noqa: F401  (loads .env before the fixtures set or clear keys)
import pytest
import yaml
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

from tests.fakes.llm import empty, install_fake_llm, refusal, text, tool

ROOT = Path(__file__).resolve().parents[1]
DEMO_PROJECT = ROOT / "templates" / "demos" / "tower-b-he" / "B-brain" / "project"
PAYMENT_YAML = ROOT / "packs" / "profession" / "developer" / "R-routines" / "skills" / "payment-milestone-check.yaml"
VENTURE = "tower-b"
BUDGET_QUESTION = "כמה נשאר לנו נטו בתקציב?"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


class SheetTool(BaseTool):
    """sheets_read answers with the schedule; sheets_append records rows (a gated write)."""

    name = "fake_sheets"
    description = "test sheets"
    category = ToolCategory.PRODUCTIVITY

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def get_schemas(self):
        obj = {"type": "object", "properties": {"range": {"type": "string"}}}
        rows = {
            "type": "object",
            "properties": {
                "spreadsheet_id": {"type": "string"},
                "range": {"type": "string"},
                "values": {"type": "array", "items": {"type": "array", "items": {}}},
            },
        }
        return [
            ToolSchema("sheets_read", "read a range", obj),
            ToolSchema("sheets_append", "append rows", rows, is_destructive=True),
        ]

    def is_available(self):
        return True

    async def execute(self, action, params):
        self.calls.append((action, params))
        if action == "sheets_read":
            return ToolResult.ok(output="Milestone 4 | Frame works | 30% | 360000\nContractor | Demo Builders Ltd")
        return ToolResult.ok(output="appended 1 row")


@pytest.fixture
def sheets(monkeypatch):
    """A fresh tool registry with the sheets tool behind the default approval gate."""
    import realize_core.tools.tool_registry as tr
    from realize_core.governance.tool_gate import ToolGate

    monkeypatch.setattr(tr, "_registry", None)
    registry = tr.get_tool_registry()
    sheet = SheetTool()
    registry.register(sheet)
    registry.set_gate(ToolGate(config={}))  # unmapped writes wait for a person
    return sheet


@pytest.fixture
def quiet_chat(monkeypatch):
    """standard_llm_handling with a fixed prompt and no conversation store."""
    import realize_core.base_handler as bh

    monkeypatch.setattr(bh, "build_system_prompt", lambda **_: "You are the finance agent.")
    monkeypatch.setattr(bh, "get_history", lambda *_: [])
    monkeypatch.setattr(bh, "add_message", lambda *_a, **_k: None)


async def _chat(message="What is the budget?", features=None, **kwargs) -> tuple[str, list[dict]]:
    from realize_core.base_handler import standard_llm_handling

    events: list[dict] = []
    reply = await standard_llm_handling(
        system_key=VENTURE,
        agent_key="finance",
        user_id="dana",
        message=message,
        system_config=kwargs.pop("system_config", {}),
        features=features or {},
        emit=events.append,
        **kwargs,
    )
    return reply, events


# ---------------------------------------------------------------------------
# Plain chat
# ---------------------------------------------------------------------------


async def test_plain_chat(fake_llm, quiet_chat):
    fake_llm.script(text("The budget is 1.2M."))

    reply, events = await _chat()

    assert reply == "The budget is 1.2M."
    assert len(fake_llm.requests) == 1
    assert fake_llm.system_prompt() == "You are the finance agent."
    assert fake_llm.user_text() == "What is the budget?"
    assert not [e for e in events if e["type"] == "notice"]


@pytest.mark.parametrize("blocked", [refusal, empty], ids=["safety", "empty"])
async def test_blocked_answer_is_never_reported_as_success(fake_llm, quiet_chat, blocked):
    """A safety block is final (a refusal message); an empty answer falls back, then reports failure."""
    from realize_core.llm.base_provider import REFUSAL_TEXT
    from realize_core.llm.router import ALL_FAILED_TEXT

    fake_llm.script(blocked())

    reply, _ = await _chat()

    assert reply == (REFUSAL_TEXT if blocked is refusal else ALL_FAILED_TEXT)


@pytest.mark.parametrize("shape", ["gemini", "ollama"])
async def test_empty_answer_falls_back_to_the_next_provider(monkeypatch, quiet_chat, shape):
    """Gemini/Ollama return nothing; the next provider in the chain answers."""
    from realize_core.llm import registry as registry_mod
    from realize_core.llm.base_provider import BaseLLMProvider, LLMResponse

    class Backup(BaseLLMProvider):
        name = "backup"

        async def complete(self, system_prompt, messages, model=None, **_):
            return LLMResponse(text="Backup answer.", provider="backup")

        def list_models(self):
            return []

    fake = install_fake_llm(monkeypatch, shape).script(empty())
    registry = registry_mod.get_registry()
    registry.register(Backup())
    registry.set_fallback_chain([fake.name, "backup"])

    reply, _ = await _chat()

    assert reply == "Backup answer."
    assert len(fake.requests) == 1


# ---------------------------------------------------------------------------
# Tool loop and its trail
# ---------------------------------------------------------------------------


async def test_tool_loop_with_trail(fake_llm, quiet_chat, sheets):
    fake_llm.script(tool("sheets_read", {"range": "Milestones"}, "Checking."), text("Milestone 4 is 360,000."))

    reply, events = await _chat(features={"agent_tools": True})

    assert reply == "Milestone 4 is 360,000."
    assert sheets.calls == [("sheets_read", {"range": "Milestones"})]
    kinds = [e["type"] for e in events]
    assert kinds == ["tool_call", "tool_result", "text"]
    assert events[1]["success"] is True
    assert events[1]["output"].startswith("Milestone 4")
    # The tool result went back to the model in its own wire shape.
    assert "Milestone 4 | Frame works" in json.dumps(fake_llm.requests[1]["messages"], ensure_ascii=False)


async def test_ollama_model_without_tools_says_so(monkeypatch, quiet_chat, sheets):
    """No silent fallback: an explicit notice, and the answer is told it read no live data."""
    from realize_core.base_handler import NO_LIVE_DATA_NOTE

    fake = install_fake_llm(monkeypatch, "ollama", ollama_tools=False)
    fake.script(text("I can't see the sheet right now."))

    reply, events = await _chat(features={"agent_tools": True})

    assert reply == "I can't see the sheet right now."
    assert sheets.calls == []
    assert [e["code"] for e in events if e["type"] == "notice"] == ["tools_unavailable"]
    assert not [e for e in events if e["type"] in ("tool_call", "tool_result")]
    assert len(fake.requests) == 1
    assert "tools" not in fake.requests[0]
    assert fake.system_prompt().endswith(NO_LIVE_DATA_NOTE)


# ---------------------------------------------------------------------------
# Approvals (STORY-16): a gated write pauses, then runs once after approval
# ---------------------------------------------------------------------------


async def test_gated_write_waits_for_approval_then_runs_once(fake_llm, quiet_chat, sheets, monkeypatch, tmp_path):
    import realize_core.memory.conversation as conv
    from realize_core import config
    from realize_core.governance.gates import decide_approval

    monkeypatch.setattr(conv, "add_message", lambda *a, **k: None)
    monkeypatch.setattr(config, "KB_PATH", tmp_path)  # the decision log stays in the temp folder
    row = {"range": "Payments", "values": [["2026-10-14", "Demo Builders Ltd", 360000]]}
    fake_llm.script(tool("sheets_append", row), text("The payment row waits for your approval."))

    reply, events = await _chat(features={"agent_tools": True})

    assert reply == "The payment row waits for your approval."
    assert sheets.calls == []
    requested = [e for e in events if e["type"] == "approval_requested"]
    assert len(requested) == 1
    assert "NOT performed" in json.dumps(fake_llm.requests[1]["messages"])

    out = await decide_approval(requested[0]["request_id"], approve=True)

    assert out["execution"]["executed"] is True
    assert out["execution"]["success"] is True
    assert sheets.calls == [("sheets_append", row)]
    await decide_approval(requested[0]["request_id"], approve=True)  # already decided: nothing runs
    assert len(sheets.calls) == 1


# ---------------------------------------------------------------------------
# Skill JSON step (the webinar payment row)
# ---------------------------------------------------------------------------

TODAY = date.today().isoformat()
TEMPLATE_ROW = json.dumps([[TODAY, "contractor", "milestone", 0, 0, "verdict", "missing evidence"]])
REAL_ROW = [[TODAY, "Demo Builders Ltd", "Milestone 4", 360000, 342000, "PARTIAL", "supervisor sign-off"]]
CHECK = "Verdict: PARTIAL\nMilestone 4 — Frame works, 30%\nContractor: Demo Builders Ltd"


def _payment_skill() -> dict:
    skill = yaml.safe_load(PAYMENT_YAML.read_text(encoding="utf-8"))
    skill["variables"] = {**skill["variables"], "milestones_sheet_id": "m1", "payments_sheet_id": "p1"}
    return {**skill, "_version": 2}


async def _run_payment_skill():
    from realize_core.skills.executor import _execute_v2_steps

    return await _execute_v2_steps(
        _payment_skill(), "Demo Builders asks 360000 for milestone 4", "acme", "u1", None, {}, {}, "api"
    )


@pytest.fixture
def plain_prompt(monkeypatch):
    monkeypatch.setattr("realize_core.prompt.builder.build_system_prompt", lambda **_: "system")


@pytest.fixture
def skill_runtime(monkeypatch, tmp_path):
    """What an approval needs to resume a paused skill (STORY-16 pattern), kept in temp folders."""
    import realize_core.memory.conversation as conv
    from realize_core import config, engine

    monkeypatch.setattr(conv, "add_message", lambda *a, **k: None)
    monkeypatch.setattr(config, "KB_PATH", tmp_path)
    monkeypatch.setattr(
        engine,
        "load_runtime",
        lambda: {"kb_path": None, "systems": {"acme": {}}, "shared_config": {}, "features": {}, "config": {}},
    )


def _pending_approval() -> str:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        return conn.execute("SELECT id FROM approval_queue WHERE status = 'pending'").fetchone()[0]
    finally:
        conn.close()


async def test_skill_json_step_writes_real_values_after_approval(fake_llm, sheets, plain_prompt, skill_runtime):
    """The template row is rejected and retried; after approval the sheet gets the real values."""
    from realize_core.governance.gates import decide_approval

    fake_llm.script(text(CHECK), text(TEMPLATE_ROW), text(json.dumps(REAL_ROW)), text("Short report"))

    out = await _run_payment_skill()

    assert "waiting for operator approval" in out
    assert [a for a, _ in sheets.calls] == ["sheets_read"]  # the row is held, not written
    assert "rejected" in fake_llm.user_text(2)

    result = await decide_approval(_pending_approval(), approve=True)

    appended = [p for action, p in sheets.calls if action == "sheets_append"]
    assert [p["values"] for p in appended] == [REAL_ROW]
    assert result["skill_output"] == "Short report"
    assert not fake_llm.unused


async def test_skill_placeholder_echo_twice_fails_before_the_sheet(fake_llm, sheets, plain_prompt):
    fake_llm.script(text(CHECK), text(TEMPLATE_ROW), text(TEMPLATE_ROW))

    out = await _run_payment_skill()

    assert "stopped at step 'payment_row'" in out
    assert [a for a, _ in sheets.calls] == ["sheets_read"]


# ---------------------------------------------------------------------------
# KB (Hebrew) and memory search: provider-independent, run under each provider
# ---------------------------------------------------------------------------


@pytest.fixture
def hebrew_kb(tmp_path, monkeypatch):
    """The Hebrew demo project indexed into a temp KB; the prompt builder searches it."""
    from functools import partial

    from realize_core.kb import indexer

    project = tmp_path / "systems" / VENTURE / "B-brain" / "project"
    project.mkdir(parents=True)
    for md in DEMO_PROJECT.glob("*.md"):
        shutil.copy(md, project / md.name)
    db_path = tmp_path / "kb_index.db"
    monkeypatch.setattr(indexer, "_get_embedder", lambda: None)
    indexer.index_kb_files(str(tmp_path), db_path=db_path, force=True)
    monkeypatch.setattr(indexer, "semantic_search", partial(indexer.semantic_search, db_path=db_path))
    return tmp_path


async def test_hebrew_kb_question_is_answered_with_sources(fake_llm, hebrew_kb, monkeypatch):
    import realize_core.base_handler as bh

    monkeypatch.setattr(bh, "get_history", lambda *_: [])
    monkeypatch.setattr(bh, "add_message", lambda *_a, **_k: None)
    fake_llm.script(text("נשארו 1,240,000 ₪ נטו [S1]"))

    reply, events = await _chat(
        BUDGET_QUESTION,
        features={"cite_sources": True},
        kb_path=hebrew_kb,
        system_config={"name": "Tower B"},
    )

    assert reply.endswith("[S1]")
    sources = [e for e in events if e["type"] == "source"]
    assert sources
    assert sources[0]["id"] == "S1"
    assert any(Path(s["path"]).name == "budget.md" for s in sources)
    assert "[S1]" in fake_llm.system_prompt()


async def test_hebrew_memory_search(fake_llm, tmp_path, monkeypatch):
    from realize_core.memory import store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "memory.db")
    store.init_db()
    store.store_memory(VENTURE, "decision", "התקציב אושר: נשארו 1.2 מיליון נטו")
    store.store_memory("other", "decision", "תקציב של מיזם אחר")

    results = store.search_memories("כמה נשאר בתקציב", system_key=VENTURE)

    assert [r["content"] for r in results] == ["התקציב אושר: נשארו 1.2 מיליון נטו"]
    assert fake_llm.requests == []  # search never needs a model


# ---------------------------------------------------------------------------
# Vision, evolution intent, review
# ---------------------------------------------------------------------------

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082"
)


async def test_vision_analyze_image(fake_llm):
    from realize_core.media import analyze_image

    fake_llm.script(text("A site photo of the frame works."))

    result = await analyze_image(PNG, "image/png", prompt="What does this show?")

    assert result.success, result.error
    assert result.output == "A site photo of the frame works."
    assert result.metadata["provider"] == fake_llm.name
    assert fake_llm.has_image()


async def test_evolution_intent(fake_llm):
    from realize_core.evolution.handler import analyze_evolution_intent

    fake_llm.script(text(json.dumps({"action": "create_file", "system_key": "acme", "title": "SOP", "content": "x"})))

    result = await analyze_evolution_intent("save this as an SOP", "acme")

    assert result is not None
    assert result["action"] == "create_file"


async def test_review_handler(fake_llm, monkeypatch):
    import realize_core.base_handler as bh

    monkeypatch.setattr(bh, "get_session", lambda *_: None)
    monkeypatch.setattr(bh, "get_history", lambda *_: [{"role": "assistant", "content": "a draft"}])
    monkeypatch.setattr(bh, "build_system_prompt", lambda **_: "reviewer prompt")
    fake_llm.script(text("Verdict: APPROVED"))

    result = await bh.handle_review(VENTURE, "dana")

    assert result == "Verdict: APPROVED"
    assert "a draft" in fake_llm.user_text()


# ---------------------------------------------------------------------------
# MCP realize_chat
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    from realize_core.memory.conversation import clear_all
    from realize_core.memory.store import init_db

    monkeypatch.setattr("realize_core.memory.store.DB_PATH", tmp_path / "memory.db")
    init_db()
    clear_all()
    yield
    clear_all()


async def test_mcp_realize_chat(fake_llm, memory_db, kb_root, system_config, shared_config):
    from realize_api.dependencies import CurrentUser
    from realize_core.mcp_server.tools.chat_tools import realize_chat

    fake_llm.script(text("Hello from the team."))
    state = SimpleNamespace(
        systems={"test": system_config}, kb_path=kb_root, shared_config=shared_config, config={"features": {}}
    )

    out = await realize_chat(
        {"message": "Say hello to the team", "system_key": "test"},
        state,
        CurrentUser(user_id="owner@acme.io", role="owner", scopes=[]),
    )

    assert out["response"] == "Hello from the team."
    assert out["system_key"] == "test"
    assert out["message_id"] is not None
    assert len(fake_llm.requests) == 1
