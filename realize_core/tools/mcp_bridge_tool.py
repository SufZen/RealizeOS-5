"""
MCP bridge — expose tools from connected MCP servers through the ToolRegistry.

MCP servers are configured in ``mcp-servers.yaml`` and connected at startup
when ``features.mcp`` is on. Their tools appear here as registry actions named
``mcp__<server>__<tool>``, so agents call them through the same dispatch point
(and governance gate) as built-in tools. The action list is dynamic: it
reflects whichever servers are connected right now.
"""

from __future__ import annotations

import logging
from typing import Any

from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

logger = logging.getLogger(__name__)


class MCPBridgeTool(BaseTool):
    """Registry adapter over :class:`realize_core.tools.mcp.MCPClientHub`."""

    #: Tells the registry to resolve actions at call time, not registration.
    dynamic_actions = True

    @property
    def name(self) -> str:
        return "mcp"

    @property
    def description(self) -> str:
        return "Tools provided by connected MCP servers"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.CUSTOM

    @staticmethod
    def _hub():
        from realize_core.tools.mcp import get_mcp_hub

        return get_mcp_hub()

    def get_schemas(self) -> list[ToolSchema]:
        schemas: list[ToolSchema] = []
        for server in self._hub().servers.values():
            if not server.connected:
                continue
            for claude_schema, read_only in server.describe_tools():
                schemas.append(
                    ToolSchema(
                        name=claude_schema["name"],
                        description=claude_schema.get("description", ""),
                        input_schema=claude_schema.get("input_schema", {"type": "object", "properties": {}}),
                        category=ToolCategory.CUSTOM,
                        is_destructive=not read_only,
                    )
                )
        return schemas

    def is_available(self) -> bool:
        return any(s.connected for s in self._hub().servers.values())

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        output = await self._hub().call_tool(action, params)
        # The hub reports failures in-band ("Error: ..." / "Error calling ...").
        if output.startswith(("Error:", "Error calling ")):
            return ToolResult.fail(output)
        return ToolResult.ok(output=output)


def get_tool() -> MCPBridgeTool:
    """Factory function for auto-discovery."""
    return MCPBridgeTool()
