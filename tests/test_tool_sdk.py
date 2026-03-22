"""Tests for realize_core.tools.base_tool and tool_registry."""
from typing import Any

import pytest
from realize_core.tools.base_tool import (
    BaseTool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)
from realize_core.tools.tool_registry import ToolRegistry, get_tool_registry

# ---------------------------------------------------------------------------
# Test fixtures: concrete tool implementations
# ---------------------------------------------------------------------------


class MockTool(BaseTool):
    """A concrete test tool with two actions."""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.CUSTOM

    def get_schemas(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="mock_read",
                description="Read something",
                input_schema={"type": "object", "properties": {"key": {"type": "string"}}},
                is_destructive=False,
            ),
            ToolSchema(
                name="mock_write",
                description="Write something",
                input_schema={"type": "object", "properties": {"data": {"type": "string"}}},
                is_destructive=True,
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if action == "mock_read":
            return ToolResult.ok(f"Read: {params.get('key', 'default')}")
        elif action == "mock_write":
            return ToolResult.ok(f"Wrote: {params.get('data', '')}")
        return ToolResult.fail(f"Unknown action: {action}")

    def is_available(self) -> bool:
        return True


class UnavailableTool(BaseTool):

    @property
    def name(self) -> str:
        return "unavailable_tool"

    @property
    def description(self) -> str:
        return "Always unavailable"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.CUSTOM

    def get_schemas(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="unavailable_action",
                description="Won't work",
                input_schema={"type": "object", "properties": {}},
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        return ToolResult.fail("Not available")

    def is_available(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# ToolCategory tests
# ---------------------------------------------------------------------------


class TestToolCategory:
    def test_all_categories(self):
        expected = {
            "communication", "research", "productivity", "development",
            "media", "data", "automation", "custom",
        }
        assert {c.value for c in ToolCategory} == expected


# ---------------------------------------------------------------------------
# ToolSchema tests
# ---------------------------------------------------------------------------


class TestToolSchema:
    def test_to_claude_format(self):
        schema = ToolSchema(
            name="test_action",
            description="Test",
            input_schema={"type": "object", "properties": {}},
        )
        claude = schema.to_claude_format()
        assert claude["name"] == "test_action"
        assert claude["description"] == "Test"
        assert "input_schema" in claude

    def test_to_mcp_format(self):
        schema = ToolSchema(
            name="test_action",
            description="Test",
            input_schema={"type": "object", "properties": {}},
        )
        mcp = schema.to_mcp_format()
        assert mcp["name"] == "test_action"
        assert "inputSchema" in mcp


# ---------------------------------------------------------------------------
# ToolResult tests
# ---------------------------------------------------------------------------


class TestToolResult:
    def test_ok_factory(self):
        r = ToolResult.ok("Success", data={"key": "val"}, extra="info")
        assert r.success
        assert r.output == "Success"
        assert r.data == {"key": "val"}
        assert r.metadata["extra"] == "info"
        assert r.error is None

    def test_fail_factory(self):
        r = ToolResult.fail("Something broke", output="partial")
        assert not r.success
        assert r.error == "Something broke"
        assert r.output == "partial"


# ---------------------------------------------------------------------------
# BaseTool tests
# ---------------------------------------------------------------------------


class TestBaseTool:
    def test_action_names(self):
        tool = MockTool()
        assert tool.get_action_names() == ["mock_read", "mock_write"]

    def test_claude_schemas(self):
        tool = MockTool()
        schemas = tool.get_claude_schemas()
        assert len(schemas) == 2
        assert schemas[0]["name"] == "mock_read"

    def test_read_actions(self):
        tool = MockTool()
        reads = tool.get_read_actions()
        assert "mock_read" in reads
        assert "mock_write" not in reads

    def test_write_actions(self):
        tool = MockTool()
        writes = tool.get_write_actions()
        assert "mock_write" in writes
        assert "mock_read" not in writes


# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_register(self):
        reg = ToolRegistry()
        assert reg.register(MockTool())
        assert reg.tool_count == 1
        assert reg.action_count == 2

    def test_register_duplicate(self):
        reg = ToolRegistry()
        reg.register(MockTool())
        assert not reg.register(MockTool())

    def test_unregister(self):
        reg = ToolRegistry()
        reg.register(MockTool())
        assert reg.unregister("mock_tool")
        assert reg.tool_count == 0
        assert reg.action_count == 0

    def test_unregister_nonexistent(self):
        reg = ToolRegistry()
        assert not reg.unregister("doesnt_exist")

    @pytest.mark.asyncio
    async def test_execute_success(self):
        reg = ToolRegistry()
        reg.register(MockTool())
        result = await reg.execute("mock_read", {"key": "test"})
        assert result.success
        assert "Read: test" in result.output

    @pytest.mark.asyncio
    async def test_execute_unknown_action(self):
        reg = ToolRegistry()
        result = await reg.execute("nonexistent_action", {})
        assert not result.success
        assert "Unknown action" in result.error

    @pytest.mark.asyncio
    async def test_execute_unavailable_tool(self):
        reg = ToolRegistry()
        reg.register(UnavailableTool())
        result = await reg.execute("unavailable_action", {})
        assert not result.success
        assert "not available" in result.error

    def test_get_all_schemas_available_only(self):
        reg = ToolRegistry()
        reg.register(MockTool())
        reg.register(UnavailableTool())
        schemas = reg.get_all_schemas(available_only=True)
        names = {s["name"] for s in schemas}
        assert "mock_read" in names
        assert "unavailable_action" not in names

    def test_get_all_schemas_include_unavailable(self):
        reg = ToolRegistry()
        reg.register(MockTool())
        reg.register(UnavailableTool())
        schemas = reg.get_all_schemas(available_only=False)
        names = {s["name"] for s in schemas}
        assert "unavailable_action" in names

    def test_get_tools_by_category(self):
        reg = ToolRegistry()
        reg.register(MockTool())
        custom = reg.get_tools_by_category(ToolCategory.CUSTOM)
        assert len(custom) == 1
        assert custom[0].name == "mock_tool"

    def test_get_tool(self):
        reg = ToolRegistry()
        reg.register(MockTool())
        assert reg.get_tool("mock_tool") is not None
        assert reg.get_tool("nope") is None

    def test_get_tool_for_action(self):
        reg = ToolRegistry()
        reg.register(MockTool())
        tool = reg.get_tool_for_action("mock_read")
        assert tool is not None
        assert tool.name == "mock_tool"

    def test_status_summary(self):
        reg = ToolRegistry()
        reg.register(MockTool())
        summary = reg.status_summary()
        assert summary["total_tools"] == 1
        assert summary["total_actions"] == 2
        assert summary["available"] == 1
        assert "mock_tool" in summary["tools"]


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------


class TestToolRegistrySingleton:
    def test_singleton(self):
        import realize_core.tools.tool_registry as mod
        mod._registry = None
        r1 = get_tool_registry()
        r2 = get_tool_registry()
        assert r1 is r2
        mod._registry = None
