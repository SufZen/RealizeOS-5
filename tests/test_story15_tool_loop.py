"""STORY-15 — the agent tool loop (brief item 1)."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest
from realize_core.llm.base_provider import LLMResponse
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def text(t: str):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_: str, name: str, **inp):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)


def message(*blocks, stop="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop, stop_details=None)


class ScriptedProvider:
    """Returns the scripted Claude messages in order; records every request."""

    name = "claude"

    def __init__(self, *messages):
        self._messages = list(messages)
        self.requests: list[dict[str, Any]] = []

    def is_available(self) -> bool:
        return True

    async def complete_with_tools(self, system_prompt, messages, tools, model=None, max_tokens=4096):
        self.requests.append({"system": system_prompt, "messages": copy.deepcopy(messages), "tools": tools})
        msg = self._messages.pop(0)
        if isinstance(msg, LLMResponse):
            return msg
        return LLMResponse(text="", provider="claude", cost_usd=0.001, raw=msg)


class SheetTool(BaseTool):
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    name = "sheets"
    description = "test sheets"
    category = ToolCategory.PRODUCTIVITY

    def get_schemas(self):
        obj = {"type": "object", "properties": {}}
        return [
            ToolSchema("sheets_read", "read", obj),
            ToolSchema("sheets_append", "append", obj, is_destructive=True),
            ToolSchema("sheets_broken", "fails", obj),
        ]

    def is_available(self):
        return True

    async def execute(self, action, params):
        self.calls.append((action, params))
        if action == "sheets_broken":
            return ToolResult.fail("Spreadsheet not found")
        return ToolResult.ok(output=f"{action} ok: {params}")


@pytest.fixture
def registry(monkeypatch):
    import realize_core.tools.tool_registry as tr

    monkeypatch.setattr(tr, "_registry", None)
    reg = tr.get_tool_registry()
    tool = SheetTool()
    reg.register(tool)
    return reg, tool


@pytest.fixture(autouse=True)
def no_limits(monkeypatch):
    from realize_core.llm import router

    monkeypatch.setattr(router, "_check_rate_limit", lambda: True)
    monkeypatch.setattr(router, "_check_cost_limit", lambda: True)


TOOLS = [
    {"name": name, "description": name, "input_schema": {"type": "object"}}
    for name in ("sheets_read", "sheets_append", "sheets_broken")
]
READ_ONLY_TOOLS = TOOLS[:1]


async def _run(provider, registry, tools=None, **kw):
    from realize_core.agents.tool_loop import run_tool_loop

    events: list[dict] = []
    result = await run_tool_loop(
        "You are the finance agent.",
        [{"role": "user", "content": "What is the budget?"}],
        TOOLS if tools is None else tools,
        registry=registry,
        provider=provider,
        emit=events.append,
        **kw,
    )
    return result, events


# ---------------------------------------------------------------------------
# Loop behaviour
# ---------------------------------------------------------------------------


class TestToolLoop:
    @pytest.mark.asyncio
    async def test_tool_call_then_answer(self, registry):
        reg, tool = registry
        provider = ScriptedProvider(
            message(text("Checking the sheet."), tool_use("t1", "sheets_read", range="A1:B9"), stop="tool_use"),
            message(text("The budget is ₪1.2M [S1].")),
        )

        result, events = await _run(provider, reg)

        assert result.text == "The budget is ₪1.2M [S1]."
        assert result.stop_reason == "end_turn"
        assert tool.calls == [("sheets_read", {"range": "A1:B9"})]
        # second request carries the assistant turn + the matching tool_result
        second = provider.requests[1]["messages"]
        assert second[-2]["role"] == "assistant"
        assert second[-1] == {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "sheets_read ok: {'range': 'A1:B9'}"}],
        }
        assert [e["type"] for e in events] == ["tool_call", "tool_result", "text"]

    @pytest.mark.asyncio
    async def test_parallel_calls_answered_in_one_message(self, registry):
        reg, tool = registry
        provider = ScriptedProvider(
            message(tool_use("a", "sheets_read", range="A"), tool_use("b", "sheets_read", range="B"), stop="tool_use"),
            message(text("done")),
        )

        await _run(provider, reg)

        results = provider.requests[1]["messages"][-1]["content"]
        assert [r["tool_use_id"] for r in results] == ["a", "b"]
        assert len(tool.calls) == 2

    @pytest.mark.asyncio
    async def test_failed_tool_reported_with_is_error(self, registry):
        reg, _ = registry
        provider = ScriptedProvider(
            message(tool_use("t1", "sheets_broken"), stop="tool_use"),
            message(text("I couldn't open the spreadsheet.")),
        )

        result, _ = await _run(provider, reg)

        block = provider.requests[1]["messages"][-1]["content"][0]
        assert block["is_error"] is True
        assert "Spreadsheet not found" in block["content"]
        assert result.tool_calls[0].success is False

    @pytest.mark.asyncio
    async def test_gate_holds_write_and_model_is_told(self, registry):
        from realize_core.governance.tool_gate import ToolGate

        reg, tool = registry
        reg.set_gate(ToolGate(config={}))  # default trust level 3 → unmapped write needs approval
        provider = ScriptedProvider(
            message(tool_use("w1", "sheets_append", values=[[1]]), stop="tool_use"),
            message(text("I've requested approval to add the row.")),
        )

        result, events = await _run(provider, reg)

        assert tool.calls == []  # never executed
        assert result.pending_approvals
        assert result.tool_calls[0].held
        block = provider.requests[1]["messages"][-1]["content"][0]
        assert "NOT performed" in block["content"]
        assert "is_error" not in block
        assert "approval_requested" in [e["type"] for e in events]

    @pytest.mark.asyncio
    async def test_iteration_cap_forces_final_answer(self, registry):
        reg, _ = registry
        loop_forever = [message(tool_use(f"t{i}", "sheets_read"), stop="tool_use") for i in range(3)]
        provider = ScriptedProvider(*loop_forever)

        result, _ = await _run(provider, reg, max_iterations=2)

        assert len(provider.requests) == 3
        assert "tool-use limit" in provider.requests[-1]["system"]
        assert result.stop_reason == "max_iterations"

    @pytest.mark.asyncio
    async def test_pause_turn_continues(self, registry):
        reg, _ = registry
        provider = ScriptedProvider(message(text("thinking..."), stop="pause_turn"), message(text("final")))

        result, _ = await _run(provider, reg)

        assert result.text == "final"
        assert provider.requests[1]["messages"][-1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_provider_error_stops_cleanly(self, registry):
        reg, _ = registry
        provider = ScriptedProvider(LLMResponse(text="AI service down", error="boom"))

        result, _ = await _run(provider, reg)

        assert result.stop_reason == "error"

    @pytest.mark.asyncio
    async def test_broken_listener_does_not_break_loop(self, registry):
        from realize_core.agents.tool_loop import run_tool_loop

        reg, _ = registry
        provider = ScriptedProvider(message(tool_use("t1", "sheets_read"), stop="tool_use"), message(text("ok")))

        def bad_listener(_event):
            raise RuntimeError("socket closed")

        result = await run_tool_loop(
            "s", [{"role": "user", "content": "q"}], TOOLS, registry=reg, provider=provider, emit=bad_listener
        )
        assert result.text == "ok"


# ---------------------------------------------------------------------------
# Chat + skills integration
# ---------------------------------------------------------------------------


class TestAgentToolSchemas:
    def test_without_gate_only_read_tools_offered(self, registry):
        from realize_core.base_handler import agent_tool_schemas

        reg, _ = registry
        names = {s["name"] for s in agent_tool_schemas("finance", None, {})}
        assert "sheets_read" in names
        assert "sheets_append" not in names

    def test_with_gate_writes_offered(self, registry):
        from realize_core.base_handler import agent_tool_schemas
        from realize_core.governance.tool_gate import ToolGate

        reg, _ = registry
        reg.set_gate(ToolGate(config={}))
        names = {s["name"] for s in agent_tool_schemas("finance", None, {})}
        assert {"sheets_read", "sheets_append"} <= names

    def test_persona_allowlist_narrows_tools(self, registry, tmp_path):
        from realize_core.base_handler import agent_tool_schemas

        agents = tmp_path / "systems" / "acme" / "A-agents"
        agents.mkdir(parents=True)
        (agents / "writer.persona.yaml").write_text("name: Writer\ntools_allowlist: [web]\n", encoding="utf-8")

        names = {s["name"] for s in agent_tool_schemas("writer", tmp_path, {"agents_dir": "systems/acme/A-agents"})}
        assert "sheets_read" not in names


@pytest.mark.asyncio
async def test_chat_uses_tool_loop_when_flag_on(registry, monkeypatch):
    import realize_core.agents.tool_loop as tl
    import realize_core.base_handler as bh

    reg, tool = registry
    provider = ScriptedProvider(message(tool_use("t1", "sheets_read"), stop="tool_use"), message(text("Budget: 1.2M")))
    monkeypatch.setattr(tl, "tool_capable_provider", lambda: provider)
    monkeypatch.setattr(tl, "_check_rate_limit", lambda: True, raising=False)
    monkeypatch.setattr(bh, "build_system_prompt", lambda **_: "prompt")
    monkeypatch.setattr(bh, "get_history", lambda *_: [])
    monkeypatch.setattr(bh, "add_message", lambda *_: None)
    events: list[dict] = []

    reply = await bh.standard_llm_handling(
        system_key="acme",
        agent_key="finance",
        user_id="u1",
        message="what is the budget?",
        system_config={},
        features={"agent_tools": True},
        emit=events.append,
    )

    assert reply == "Budget: 1.2M"
    assert tool.calls == [("sheets_read", {})]
    assert events[0]["type"] == "tool_call"


@pytest.mark.asyncio
async def test_chat_falls_back_to_router_without_flag(registry, monkeypatch):
    import realize_core.base_handler as bh

    async def fake_route(*_a, **_k):
        return "plain answer"

    monkeypatch.setattr(bh, "route_to_llm", fake_route)
    monkeypatch.setattr(bh, "build_system_prompt", lambda **_: "prompt")
    monkeypatch.setattr(bh, "get_history", lambda *_: [])
    monkeypatch.setattr(bh, "add_message", lambda *_: None)

    reply = await bh.standard_llm_handling(
        system_key="acme", agent_key="finance", user_id="u1", message="hi", system_config={}, features={}
    )
    assert reply == "plain answer"


class TestSkillToolStep:
    @pytest.mark.asyncio
    async def test_tool_step_goes_through_registry(self, registry):
        from realize_core.skills.executor import SkillContext, _execute_tool_step

        reg, tool = registry
        ctx = SkillContext(user_message="q", system_key="acme", user_id="u1")
        out = await _execute_tool_step({"action": "sheets_read", "params": {"range": "A1"}}, ctx)

        assert out == "sheets_read ok: {'range': 'A1'}"
        assert tool.calls == [("sheets_read", {"range": "A1"})]

    @pytest.mark.asyncio
    async def test_held_tool_step_reports_pending_approval(self, registry):
        from realize_core.governance.tool_gate import ToolGate
        from realize_core.skills.executor import SkillContext, _execute_tool_step

        reg, tool = registry
        reg.set_gate(ToolGate(config={}))
        ctx = SkillContext(user_message="q", system_key="acme", user_id="u1")
        out = await _execute_tool_step({"action": "sheets_append", "params": {}}, ctx)

        assert "waiting for operator approval" in out
        assert tool.calls == []

    @pytest.mark.asyncio
    async def test_unknown_tool(self, registry):
        from realize_core.skills.executor import SkillContext, _execute_tool_step

        ctx = SkillContext(user_message="q", system_key="acme", user_id="u1")
        assert "unknown tool" in await _execute_tool_step({"action": "nope"}, ctx)


@pytest.mark.asyncio
async def test_internal_runtime_streams_tool_events(monkeypatch):
    """Missions see the agent's tool calls as runtime events, in order."""
    import realize_core.base_handler as bh
    import realize_core.config as cfg
    from realize_core.runtimes.contract import Context, MissionStep
    from realize_core.runtimes.internal import InternalAdapter

    async def fake_process_message(**kwargs):
        emit = kwargs["emit"]
        emit({"type": "tool_call", "id": "t1", "name": "sheets_read", "input": {"range": "A1"}})
        emit({"type": "tool_result", "id": "t1", "name": "sheets_read", "success": True, "held": False, "output": "42"})
        emit({"type": "approval_requested", "id": "t2", "name": "sheets_append", "request_id": "req-9"})
        emit({"type": "text", "text": "done"})
        return "done"

    monkeypatch.setattr(bh, "process_message", fake_process_message)
    monkeypatch.setattr(cfg, "load_config", lambda *a, **k: {})
    monkeypatch.setattr(cfg, "build_systems_dict", lambda *a, **k: {})

    kinds = [
        e.kind
        async for e in InternalAdapter().invoke(
            MissionStep(step_id="s1", mission_id="m1", description="check budget"), Context(venture_id="acme")
        )
    ]

    assert kinds == ["progress", "tool_call", "tool_result", "approval_request", "text", "final"]


@pytest.mark.asyncio
async def test_tool_not_offered_is_never_executed(registry):
    """A model naming a tool it wasn't given (e.g. via prompt injection) is refused."""
    reg, tool = registry  # sheets_append exists in the registry, but isn't offered (no gate)
    provider = ScriptedProvider(
        message(tool_use("x1", "sheets_append", values=[["pwned"]]), stop="tool_use"),
        message(text("I can't do that.")),
    )

    result, events = await _run(provider, reg, tools=READ_ONLY_TOOLS)

    assert tool.calls == []
    block = provider.requests[1]["messages"][-1]["content"][0]
    assert block["is_error"] is True
    assert "not available" in block["content"]
    assert result.tool_calls[0].success is False
