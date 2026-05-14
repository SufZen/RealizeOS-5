"""MCP server dispatcher.

Wraps the ``mcp.server.lowlevel.Server`` from the official SDK and wires
its ``list_tools`` / ``call_tool`` handlers to our :class:`ToolRegistry`.
Auth + scope enforcement + audit logging happen here, not in individual
tool handlers.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import Server

from realize_core.mcp_server.auth import current_mcp_user
from realize_core.mcp_server.config import McpConfig
from realize_core.mcp_server.registry import (
    MCPTool,
    ToolRegistry,
    get_registry,
    role_meets_scope,
)

logger = logging.getLogger(__name__)


# Stable MCP error codes surfaced in the response payload's ``data.code``
# field. Keep these stable across versions — programmatic clients depend
# on them.
class MCPErrorCode:
    NOT_FOUND = "MCP_TOOL_NOT_FOUND"
    DISABLED = "MCP_TOOL_DISABLED"
    INSUFFICIENT_SCOPE = "MCP_INSUFFICIENT_SCOPE"
    ADMIN_DISABLED = "MCP_ADMIN_DISABLED"
    INTERNAL = "MCP_INTERNAL"


def build_mcp_server(
    *,
    app_state: Any,
    mcp_config: McpConfig,
    registry: ToolRegistry | None = None,
    name: str = "realize-os",
    version: str = "5.2.0",
) -> Server:
    """Build a configured :class:`mcp.server.lowlevel.Server` instance.

    ``app_state`` is the live ``FastAPI.app.state`` namespace so tools can
    read systems/kb_path/etc. as if they were inside a REST handler.
    """
    registry = registry or get_registry()
    server: Server = Server(name=name, version=version)

    @server.list_tools()
    async def _list_tools() -> list[mcp_types.Tool]:
        out: list[mcp_types.Tool] = []
        for tool in registry.visible_tools(mcp_config):
            out.append(
                mcp_types.Tool(
                    name=tool.name,
                    description=tool.description,
                    inputSchema=tool.input_schema,
                )
            )
        return out

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[mcp_types.TextContent]:
        return await _dispatch(registry, mcp_config, app_state, name, arguments or {})

    return server


async def _dispatch(
    registry: ToolRegistry,
    mcp_config: McpConfig,
    app_state: Any,
    name: str,
    arguments: dict[str, Any],
) -> list[mcp_types.TextContent]:
    """Look up + scope-check + invoke a tool, returning MCP TextContent."""
    user = current_mcp_user()
    started = time.monotonic()

    tool = registry.get(name)
    if tool is None:
        return _error(MCPErrorCode.NOT_FOUND, f"Tool '{name}' is not registered.")

    if not registry.is_visible(tool, mcp_config):
        code = MCPErrorCode.ADMIN_DISABLED if tool.family == "admin" else MCPErrorCode.DISABLED
        return _error(code, f"Tool '{name}' is not enabled on this RealizeOS instance.")

    if not role_meets_scope(user.role, tool.scope):
        _audit_call(tool, user, status="forbidden", duration_ms=0, mcp_config=mcp_config)
        return _error(
            MCPErrorCode.INSUFFICIENT_SCOPE,
            f"Tool '{name}' requires scope '{tool.scope}'; caller has role '{user.role}'.",
        )

    try:
        result = await tool.handler(arguments, app_state, user)
    except Exception as exc:
        logger.exception("MCP tool '%s' raised an exception", name)
        _audit_call(
            tool,
            user,
            status="error",
            duration_ms=int((time.monotonic() - started) * 1000),
            mcp_config=mcp_config,
        )
        return _error(MCPErrorCode.INTERNAL, f"Tool '{name}' failed: {str(exc)[:300]}")

    _audit_call(
        tool,
        user,
        status="ok",
        duration_ms=int((time.monotonic() - started) * 1000),
        mcp_config=mcp_config,
        args=arguments,
        result=result,
    )

    return [mcp_types.TextContent(type="text", text=_to_text(result))]


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, ensure_ascii=False, indent=2)
    except Exception:
        return repr(value)


def _error(code: str, message: str) -> list[mcp_types.TextContent]:
    return [
        mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": message, "code": code}, ensure_ascii=False),
        )
    ]


def _audit_call(
    tool: MCPTool,
    user: Any,
    *,
    status: str,
    duration_ms: int,
    mcp_config: McpConfig,
    args: dict[str, Any] | None = None,
    result: Any = None,
) -> None:
    """Emit an audit log entry for an MCP tool call.

    Args + result are only included when ``mcp_config.audit_full_payload``
    is set or the tool family is ``admin`` (admin calls always log full
    detail regardless of the toggle).
    """
    try:
        from realize_core.security.audit import get_audit_logger

        audit = get_audit_logger()
    except Exception as exc:
        logger.debug("Audit logger unavailable for MCP call '%s': %s", tool.name, exc)
        return

    full_payload = mcp_config.audit_full_payload or tool.family == "admin"
    metadata: dict[str, Any] = {
        "family": tool.family,
        "scope": tool.scope,
        "duration_ms": duration_ms,
    }
    if full_payload:
        metadata["args"] = args
        metadata["result"] = result

    outcome = "success" if status == "ok" else ("denied" if status == "forbidden" else "error")
    severity = "warning" if status == "forbidden" else "info"

    try:
        audit.log(
            user_id=getattr(user, "user_id", "anonymous"),
            action=f"mcp.{tool.name}",
            outcome=outcome,
            channel="mcp",
            resource_type="mcp_tool",
            resource_id=tool.name,
            severity=severity,
            metadata=metadata,
        )
    except Exception as exc:
        logger.debug("Audit log emit failed for MCP call '%s': %s", tool.name, exc)
