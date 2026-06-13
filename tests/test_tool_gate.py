"""Tests for the governance tool gate at the ToolRegistry dispatch chokepoint.

Verifies the safety-critical contract:
- No gate injected (default) -> tools execute exactly as before.
- An ALLOW gate -> tool executes.
- A HOLD (needs-approval) gate -> tool is NOT executed and a requires_human
  result with the request id is returned.
- A gate that RAISES -> fails OPEN (tool executes), never bricks dispatch.
- ToolGate.decide never raises and fails open on internal error.
"""

from __future__ import annotations

import asyncio

from realize_core.governance.tool_gate import GateDecision, GateOutcome
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema
from realize_core.tools.tool_registry import ToolRegistry


class _FakeTool(BaseTool):
    """Minimal tool that records whether it actually executed."""

    def __init__(self) -> None:
        self.ran = False

    @property
    def name(self) -> str:
        return "faketool"

    @property
    def description(self) -> str:
        return "fake tool for gate tests"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.AUTOMATION

    def is_available(self) -> bool:
        return True

    def get_schemas(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="fake_action",
                description="does nothing",
                input_schema={"type": "object", "properties": {}},
                category=ToolCategory.AUTOMATION,
            )
        ]

    async def execute(self, action: str, params: dict) -> ToolResult:
        self.ran = True
        return ToolResult.ok(output="ran")


def _registry_with_tool() -> tuple[ToolRegistry, _FakeTool]:
    reg = ToolRegistry()
    tool = _FakeTool()
    reg.register(tool)
    return reg, tool


class _AllowGate:
    def decide(self, action_name, params=None):
        return GateDecision(GateOutcome.ALLOW, action_name)


class _HoldGate:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def decide(self, action_name, params=None):
        self.calls.append(action_name)
        return GateDecision(
            GateOutcome.NEEDS_APPROVAL, action_name, request_id="req-123", reason="needs approval"
        )


class _RaiseGate:
    def decide(self, action_name, params=None):
        raise RuntimeError("gate boom")


def test_no_gate_executes_tool() -> None:
    reg, tool = _registry_with_tool()
    res = asyncio.run(reg.execute("fake_action", {}))
    assert res.success
    assert res.output == "ran"
    assert tool.ran is True


def test_allow_gate_executes_tool() -> None:
    reg, tool = _registry_with_tool()
    reg.set_gate(_AllowGate())
    res = asyncio.run(reg.execute("fake_action", {}))
    assert res.success
    assert tool.ran is True


def test_hold_gate_blocks_execution_and_returns_request() -> None:
    reg, tool = _registry_with_tool()
    gate = _HoldGate()
    reg.set_gate(gate)
    res = asyncio.run(reg.execute("fake_action", {}))
    assert tool.ran is False  # tool was NOT executed
    assert res.metadata.get("requires_human") is True
    assert res.metadata.get("request_id") == "req-123"
    assert gate.calls == ["fake_action"]


def test_raising_gate_fails_open() -> None:
    reg, tool = _registry_with_tool()
    reg.set_gate(_RaiseGate())
    res = asyncio.run(reg.execute("fake_action", {}))
    assert res.success  # fail-open: tool ran
    assert tool.ran is True


def test_toolgate_decide_returns_decision_and_never_raises() -> None:
    from realize_core.governance.tool_gate import ToolGate

    gate = ToolGate(config={})
    decision = gate.decide("some_action", {})
    assert isinstance(decision, GateDecision)
    assert decision.outcome in (GateOutcome.ALLOW, GateOutcome.NEEDS_APPROVAL, GateOutcome.BLOCK)


def test_toolgate_fails_open_on_internal_error(monkeypatch) -> None:
    from realize_core.governance import tool_gate as tg

    def _boom(*_a, **_k):
        raise RuntimeError("trust ladder exploded")

    monkeypatch.setattr(tg, "check_trust", _boom)
    gate = tg.ToolGate(config={})
    decision = gate.decide("anything", {})
    assert decision.outcome is GateOutcome.ALLOW  # fail-open
