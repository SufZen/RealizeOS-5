"""
Tests for Per-Agent Tool Gating — Intent 3.2.

Covers:
- gate_tools_for_persona() with allowlist, denylist, fallback
- check_tool_access() logic
- get_gated_schemas()
- Edge cases: empty lists, no persona
"""

from __future__ import annotations

import pytest
from realize_core.agents.persona import AgentPersona
from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema
from realize_core.tools.gating import (
    check_tool_access,
    gate_tools_for_persona,
    get_gated_schemas,
)

# ---------------------------------------------------------------------------
# Stub tools for testing
# ---------------------------------------------------------------------------


class StubTool(BaseTool):
    """Minimal tool for testing."""

    def __init__(self, tool_name: str, available: bool = True):
        self._name = tool_name
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Stub tool: {self._name}"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.CUSTOM

    def is_available(self) -> bool:
        return self._available

    def get_schemas(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name=f"{self._name}_action",
                description=f"Action for {self._name}",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def execute(self, action: str, params: dict) -> ToolResult:
        return ToolResult.ok(f"Executed {action}")


@pytest.fixture
def all_tools():
    return [
        StubTool("crm"),
        StubTool("email"),
        StubTool("web_search"),
        StubTool("code_review"),
        StubTool("calendar"),
    ]


# ---------------------------------------------------------------------------
# gate_tools_for_persona
# ---------------------------------------------------------------------------


class TestGateTools:
    """Test the tool gating function."""

    def test_no_persona_returns_all(self, all_tools):
        result = gate_tools_for_persona(all_tools, None)
        assert len(result) == 5

    def test_empty_lists_returns_all(self, all_tools):
        persona = AgentPersona(name="Agent")
        result = gate_tools_for_persona(all_tools, persona)
        assert len(result) == 5

    def test_allowlist_filters(self, all_tools):
        persona = AgentPersona(
            name="Sales Rep",
            tools_allowlist=["crm", "email"],
        )
        result = gate_tools_for_persona(all_tools, persona)
        names = [t.name for t in result]
        assert names == ["crm", "email"]

    def test_denylist_filters(self, all_tools):
        persona = AgentPersona(
            name="Junior Dev",
            tools_denylist=["code_review"],
        )
        result = gate_tools_for_persona(all_tools, persona)
        names = [t.name for t in result]
        assert "code_review" not in names
        assert len(result) == 4

    def test_allowlist_takes_priority(self, all_tools):
        """When both are set, allowlist wins."""
        persona = AgentPersona(
            name="Hybrid",
            tools_allowlist=["crm"],
            tools_denylist=["email"],
        )
        result = gate_tools_for_persona(all_tools, persona)
        names = [t.name for t in result]
        assert names == ["crm"]

    def test_allowlist_missing_tool(self, all_tools):
        """Allowlist with a tool that doesn't exist — no crash."""
        persona = AgentPersona(
            name="Missing",
            tools_allowlist=["nonexistent_tool"],
        )
        result = gate_tools_for_persona(all_tools, persona)
        assert len(result) == 0

    def test_empty_allowlist_returns_all(self, all_tools):
        """Empty allowlist (not None) falls through to fallback."""
        persona = AgentPersona(
            name="Agent",
            tools_allowlist=[],
        )
        result = gate_tools_for_persona(all_tools, persona)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# check_tool_access
# ---------------------------------------------------------------------------


class TestCheckToolAccess:
    def test_no_persona(self):
        allowed, reason = check_tool_access("crm", None)
        assert allowed is True
        assert "all tools accessible" in reason

    def test_allowed_by_allowlist(self):
        persona = AgentPersona(name="Rep", tools_allowlist=["crm", "email"])
        allowed, reason = check_tool_access("crm", persona)
        assert allowed is True

    def test_blocked_by_allowlist(self):
        persona = AgentPersona(name="Rep", tools_allowlist=["crm", "email"])
        allowed, reason = check_tool_access("code_review", persona)
        assert allowed is False
        assert "not in allowlist" in reason

    def test_blocked_by_denylist(self):
        persona = AgentPersona(name="Dev", tools_denylist=["web_search"])
        allowed, reason = check_tool_access("web_search", persona)
        assert allowed is False
        assert "in denylist" in reason

    def test_allowed_when_not_in_denylist(self):
        persona = AgentPersona(name="Dev", tools_denylist=["web_search"])
        allowed, reason = check_tool_access("crm", persona)
        assert allowed is True


# ---------------------------------------------------------------------------
# get_gated_schemas
# ---------------------------------------------------------------------------


class TestGatedSchemas:
    def test_schemas_filtered(self, all_tools):
        persona = AgentPersona(name="Rep", tools_allowlist=["crm"])
        schemas = get_gated_schemas(all_tools, persona)
        assert len(schemas) == 1
        assert schemas[0]["name"] == "crm_action"

    def test_unavailable_tool_excluded(self):
        tools = [StubTool("crm", available=True), StubTool("email", available=False)]
        persona = AgentPersona(name="Rep", tools_allowlist=["crm", "email"])
        schemas = get_gated_schemas(tools, persona)
        # Only crm is available
        assert len(schemas) == 1

    def test_no_persona_all_available(self, all_tools):
        schemas = get_gated_schemas(all_tools, None)
        assert len(schemas) == 5
