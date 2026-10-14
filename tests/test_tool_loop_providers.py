"""The agent tool loop runs the same way on every tool-capable provider.

One scenario (tool call -> result -> final answer, plus an approval-gated
write) is run against real provider adapters whose transport is mocked:
Claude (anthropic client) and LiteLLM / OpenAI / Gemini (``litellm.acompletion``).
The trail and the answer must be identical; only the wire shapes differ.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import litellm  # imported up front: it loads .env, which would re-set keys the fixtures delete
import pytest
from anthropic.types import Message
from realize_core.llm.litellm_provider import LiteLLMProvider
from realize_core.llm.providers.claude_provider import ClaudeProvider
from realize_core.llm.providers.gemini_provider import GeminiProvider
from realize_core.llm.providers.openai_provider import OpenAIProvider
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

TOOLS = [
    {
        "name": name,
        "description": name,
        "input_schema": {"type": "object", "properties": {"range": {"type": "string"}}},
    }
    for name in ("sheets_read", "sheets_append")
]
QUESTION = [{"role": "user", "content": "What is the budget?"}]


class SheetTool(BaseTool):
    name = "sheets"
    description = "test sheets"
    category = ToolCategory.PRODUCTIVITY

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def get_schemas(self):
        obj = {"type": "object", "properties": {}}
        return [ToolSchema("sheets_read", "read", obj), ToolSchema("sheets_append", "append", obj, is_destructive=True)]

    def is_available(self):
        return True

    async def execute(self, action, params):
        self.calls.append((action, params))
        return ToolResult.ok(output=f"{action} ok")


@pytest.fixture
def registry(monkeypatch):
    import realize_core.tools.tool_registry as tr
    from realize_core.governance.tool_gate import ToolGate

    monkeypatch.setattr(tr, "_registry", None)
    reg = tr.get_tool_registry()
    tool = SheetTool()
    reg.register(tool)
    reg.set_gate(ToolGate(config={}))  # default trust level: unmapped writes need approval
    return reg, tool


@pytest.fixture(autouse=True)
def no_limits(monkeypatch):
    from realize_core.llm import router

    monkeypatch.setattr(router, "_check_rate_limit", lambda: True)
    monkeypatch.setattr(router, "_check_cost_limit", lambda: True)


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    for var in ("LITELLM_MODEL", "LITELLM_API_BASE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-test")


# ---------------------------------------------------------------------------
# Mocked transports. A "turn" is (text, tool_call or None).
# ---------------------------------------------------------------------------


def _claude_message(text: str, call: tuple[str, str, dict] | None) -> Message:
    content: list[dict] = [{"type": "text", "text": text}] if text else []
    if call:
        content.append({"type": "tool_use", "id": call[0], "name": call[1], "input": call[2]})
    return Message.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": content,
            "stop_reason": "tool_use" if call else "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 5, "output_tokens": 5},
        }
    )


def _litellm_response(text: str, call: tuple[str, str, dict] | None):
    tool_calls = None
    if call:
        fn = SimpleNamespace(name=call[1], arguments=json.dumps(call[2]))
        tool_calls = [SimpleNamespace(id=call[0], type="function", function=fn)]
    message = SimpleNamespace(content=text or None, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls" if call else "stop")],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5),
    )


class Transport:
    """Records every request (deep-copied) and replies with scripted turns."""

    def __init__(self, build, turns):
        self._build = build
        self._turns = list(turns)
        self.requests: list[dict] = []

    def __call__(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        return self._build(*self._turns.pop(0))


def _run_claude(turns):
    transport = Transport(_claude_message, turns)
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=transport)
    return ClaudeProvider(), transport, patch("realize_core.llm.claude_client._get_client", return_value=client)


def _run_litellm(factory):
    def setup(turns):
        transport = Transport(_litellm_response, turns)
        ctx = patch.object(litellm, "acompletion", AsyncMock(side_effect=transport))
        return factory(), transport, ctx

    return setup


PROVIDERS = {
    "claude": _run_claude,
    "litellm": _run_litellm(LiteLLMProvider),
    "openai": _run_litellm(OpenAIProvider),
    "gemini": _run_litellm(GeminiProvider),
}


async def _scenario(name, turns, registry):
    from realize_core.agents.tool_loop import run_tool_loop

    provider, transport, transport_patch = PROVIDERS[name](turns)
    events: list[dict] = []
    with transport_patch, patch.object(litellm, "completion_cost", return_value=0.0):
        result = await run_tool_loop(
            "You are the finance agent.", QUESTION, TOOLS, registry=registry, provider=provider, emit=events.append
        )
    for event in events:
        event.pop("duration_ms", None)
    return result, events, transport.requests


READ_TURNS = [("Checking.", ("call_1", "sheets_read", {"range": "A1"})), ("The budget is 1.2M.", None)]
WRITE_TURNS = [("", ("call_9", "sheets_append", {"range": "B2"})), ("I asked for approval.", None)]


class TestSameTrailOnEveryProvider:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", list(PROVIDERS))
    async def test_read_tool_then_answer(self, name, registry):
        reg, tool = registry
        result, events, requests = await _scenario(name, READ_TURNS, reg)

        assert result.text == "The budget is 1.2M."
        assert tool.calls == [("sheets_read", {"range": "A1"})]
        assert events == [
            {"type": "tool_call", "id": "call_1", "name": "sheets_read", "input": {"range": "A1"}},
            {
                "type": "tool_result",
                "id": "call_1",
                "name": "sheets_read",
                "success": True,
                "held": False,
                "output": "sheets_read ok",
                "error": None,
            },
            {"type": "text", "text": "The budget is 1.2M."},
        ]
        assert len(requests) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", list(PROVIDERS))
    async def test_gated_write_is_held(self, name, registry):
        reg, tool = registry
        result, events, requests = await _scenario(name, WRITE_TURNS, reg)

        assert tool.calls == []
        assert result.text == "I asked for approval."
        assert result.pending_approvals
        kinds = [e["type"] for e in events]
        assert kinds == ["tool_call", "approval_requested", "tool_result", "text"]
        assert events[2]["held"] is True
        second = json.dumps(requests[1]["messages"])
        assert "NOT performed" in second


class TestProviderNativeWireShapes:
    @pytest.mark.asyncio
    async def test_claude_gets_claude_tools_and_tool_result_blocks(self, registry):
        reg, _ = registry
        _, _, requests = await _scenario("claude", READ_TURNS, reg)

        assert requests[0]["tools"][0]["input_schema"]  # Claude tool format
        assistant, results = requests[1]["messages"][-2:]
        assert assistant["role"] == "assistant"
        assert {"type": "tool_use", "id": "call_1", "name": "sheets_read", "input": {"range": "A1"}} in assistant[
            "content"
        ]
        assert results == {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "sheets_read ok"}],
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", ["litellm", "openai", "gemini"])
    async def test_litellm_providers_get_openai_tools_and_tool_messages(self, name, registry):
        reg, _ = registry
        _, _, requests = await _scenario(name, READ_TURNS, reg)

        assert requests[0]["tools"][0]["type"] == "function"
        assert requests[0]["tools"][0]["function"]["name"] == "sheets_read"
        assistant, result = requests[1]["messages"][-2:]
        assert assistant["role"] == "assistant"
        assert assistant["tool_calls"][0]["id"] == "call_1"
        assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"range": "A1"}
        assert result == {"role": "tool", "tool_call_id": "call_1", "content": "sheets_read ok"}


# ---------------------------------------------------------------------------
# Provider choice and the no-silent-fallback rule
# ---------------------------------------------------------------------------


def test_tool_capable_provider_is_first_in_fallback_chain(monkeypatch):
    import realize_core.llm.registry as llm_registry
    from realize_core.agents.tool_loop import tool_capable_provider
    from realize_core.llm.base_provider import Capability

    gemini, ollama = GeminiProvider(), object()
    asked: list = []

    def providers_with_capability(capability):
        asked.append(capability)
        return [gemini, ollama]

    monkeypatch.setattr(
        llm_registry, "get_registry", lambda: SimpleNamespace(providers_with_capability=providers_with_capability)
    )
    assert tool_capable_provider() is gemini
    assert asked == [Capability.TOOLS]

    monkeypatch.setattr(llm_registry, "get_registry", lambda: SimpleNamespace(providers_with_capability=lambda _c: []))
    assert tool_capable_provider() is None


async def _chat(monkeypatch, provider, events):
    import realize_core.agents.tool_loop as tl
    import realize_core.base_handler as bh
    from realize_core.agents.trail import TrailRecorder

    routed: list[str] = []

    async def fake_route(system_prompt, messages, task_class, **_):
        routed.append(system_prompt)
        return "I can't see the sheet right now."

    import realize_core.llm.registry as llm_registry

    # No LLM provider is registered: the tool loop can only get ``provider``.
    monkeypatch.setattr(llm_registry, "get_registry", lambda: llm_registry.ProviderRegistry())
    monkeypatch.setattr(tl, "tool_capable_provider", lambda: provider)
    monkeypatch.setattr(bh, "route_to_llm", fake_route)
    monkeypatch.setattr(bh, "build_system_prompt", lambda **_: "prompt")
    monkeypatch.setattr(bh, "get_history", lambda *_: [])
    monkeypatch.setattr(bh, "add_message", lambda *_: None)
    recorder = TrailRecorder(forward=events.append)
    reply = await bh.standard_llm_handling(
        system_key="acme",
        agent_key="finance",
        user_id="u1",
        message="what is the budget?",
        system_config={},
        features={"agent_tools": True},
        emit=recorder,
    )
    return reply, routed, recorder


@pytest.mark.asyncio
async def test_no_tool_provider_is_reported_and_answer_admits_no_data(registry, monkeypatch):
    from realize_core.base_handler import NO_LIVE_DATA_NOTE

    events: list[dict] = []
    reply, routed, recorder = await _chat(monkeypatch, None, events)

    assert reply == "I can't see the sheet right now."
    assert routed == [f"prompt\n\n{NO_LIVE_DATA_NOTE}"]
    notices = [e for e in events if e["type"] == "notice"]
    assert len(notices) == 1
    assert notices[0]["code"] == "tools_unavailable"
    assert notices[0]["message"]
    # The notice is part of the stored "what I used" trail.
    assert [s["type"] for s in recorder.stored()["steps"]] == ["notice"]


@pytest.mark.asyncio
async def test_tool_loop_error_is_reported_and_answer_admits_no_data(registry, monkeypatch):
    from realize_core.base_handler import NO_LIVE_DATA_NOTE
    from realize_core.llm.base_provider import STOP_ERROR, LLMResponse

    class Broken(ClaudeProvider):
        async def complete_with_tools(self, *a, **k):
            return LLMResponse(text="", error="boom", stop_reason=STOP_ERROR)

    events: list[dict] = []
    reply, routed, recorder = await _chat(monkeypatch, Broken(), events)

    assert reply == "I can't see the sheet right now."
    assert routed == [f"prompt\n\n{NO_LIVE_DATA_NOTE}"]
    assert [e["code"] for e in events if e["type"] == "notice"] == ["tools_error"]
    assert "notice" in [s["type"] for s in recorder.stored()["steps"]]


@pytest.mark.asyncio
async def test_agent_tools_off_routes_plainly_without_notice(registry, monkeypatch):
    import realize_core.base_handler as bh

    routed: list[str] = []

    async def fake_route(system_prompt, messages, task_class, **_):
        routed.append(system_prompt)
        return "plain"

    monkeypatch.setattr(bh, "route_to_llm", fake_route)
    monkeypatch.setattr(bh, "build_system_prompt", lambda **_: "prompt")
    monkeypatch.setattr(bh, "get_history", lambda *_: [])
    monkeypatch.setattr(bh, "add_message", lambda *_: None)
    events: list[dict] = []

    reply = await bh.standard_llm_handling(
        system_key="acme",
        agent_key="finance",
        user_id="u1",
        message="hi",
        system_config={},
        features={},
        emit=events.append,
    )

    assert reply == "plain"
    assert routed == ["prompt"]
    assert not [e for e in events if e["type"] == "notice"]


def test_trail_summary_keeps_notice():
    from realize_core.agents.trail import trail_summary

    trail = {"sources": [], "steps": [{"type": "notice", "code": "tools_unavailable", "message": "m", "extra": 1}]}
    assert trail_summary(trail)["steps"] == [{"type": "notice", "code": "tools_unavailable", "message": "m"}]
