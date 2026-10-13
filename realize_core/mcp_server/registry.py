"""MCP tool registry.

Each tool is a thin async callable that wraps an existing REST handler.
The registry maps a stable MCP tool name to its metadata + handler, and
filters the public surface based on the active :class:`McpConfig`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from realize_api.dependencies import CurrentUser

from realize_core.mcp_server.config import McpConfig

logger = logging.getLogger(__name__)

#: Tool handler signature.
#:
#: Receives the call arguments dict, the FastAPI ``app.state``, and the
#: authenticated :class:`CurrentUser`. Returns a JSON-serializable value
#: that the dispatcher renders as ``TextContent``.
ToolHandler = Callable[[dict[str, Any], Any, CurrentUser], Awaitable[Any]]

#: Tool families. ``chat`` is always on; the rest are gated by config flags.
TOOL_FAMILIES = ("chat", "kb", "ops", "admin")

#: Scope hierarchy: ``read`` < ``editor`` < ``owner``.
SCOPE_LEVELS = {"read": 0, "editor": 1, "owner": 2}

_ROLE_LEVELS = {"viewer": 0, "read": 0, "editor": 1, "owner": 2, "admin": 2}


@dataclass(frozen=True)
class MCPTool:
    """Metadata + handler for a single MCP tool."""

    name: str
    family: str
    description: str
    input_schema: dict[str, Any]
    scope: str  # "read" | "editor" | "owner"
    handler: ToolHandler
    annotations: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.family not in TOOL_FAMILIES:
            raise ValueError(f"Unknown family '{self.family}' for tool '{self.name}'")
        if self.scope not in SCOPE_LEVELS:
            raise ValueError(f"Unknown scope '{self.scope}' for tool '{self.name}'")


class ToolRegistry:
    """In-memory registry of MCP tools."""

    def __init__(self) -> None:
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> MCPTool | None:
        return self._tools.get(name)

    def visible_tools(self, mcp_cfg: McpConfig) -> list[MCPTool]:
        """Return tools whose family is exposed and that pass the ``mcp.tools`` allowlist."""
        return [t for t in self._tools.values() if self.is_visible(t, mcp_cfg)]

    def is_visible(self, tool: MCPTool, mcp_cfg: McpConfig) -> bool:
        """True when ``tool`` is served: its family is exposed and the allowlist (if any) names it."""
        if tool.family not in mcp_cfg.families:
            return False
        return mcp_cfg.tools is None or tool.name in mcp_cfg.tools

    def unknown_names(self, mcp_cfg: McpConfig) -> list[str]:
        """Allowlist entries that match no registered tool (likely typos)."""
        return [name for name in mcp_cfg.tools or () if name not in self._tools]

    def all(self) -> list[MCPTool]:
        return list(self._tools.values())

    def clear(self) -> None:
        self._tools.clear()


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Return the singleton registry, populating it on first call."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _populate(_registry)
    return _registry


def _populate(registry: ToolRegistry) -> None:
    """Eager-load all tool families."""
    from realize_core.mcp_server.tools import (
        admin_tools,
        chat_tools,
        decision_tools,
        kb_tools,
        ops_tools,
        pack_tools,
        wedge_tools,
    )

    chat_tools.register(registry)
    kb_tools.register(registry)
    pack_tools.register(registry)
    ops_tools.register(registry)
    decision_tools.register(registry)
    wedge_tools.register(registry)
    admin_tools.register(registry)


def reset_for_tests() -> None:
    """Reset registry between tests so re-imports stay clean."""
    global _registry
    _registry = None


def role_meets_scope(role: str | None, scope: str) -> bool:
    """Check whether ``role`` satisfies the tool's required ``scope``."""
    if not role:
        return False
    role_level = _ROLE_LEVELS.get(role.lower())
    if role_level is None:
        return False
    return role_level >= SCOPE_LEVELS[scope]
