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
    FORBIDDEN = "MCP_FORBIDDEN"
    ADMIN_DISABLED = "MCP_ADMIN_DISABLED"
    INTERNAL = "MCP_INTERNAL"
    #: An outside agent (agent token) may not approve, reject or dismiss (STORY-37).
    AGENT_CANNOT_DECIDE = "MCP_AGENT_CANNOT_DECIDE"
    #: An outside agent may not call this tool (STORY-37).
    AGENT_REFUSED = "MCP_AGENT_REFUSED"


def build_mcp_server(
    *,
    app_state: Any,
    mcp_config: McpConfig,
    registry: ToolRegistry | None = None,
    name: str = "realize-os",
    version: str | None = None,
) -> Server:
    """Build a configured :class:`mcp.server.lowlevel.Server` instance.

    ``app_state`` is the live ``FastAPI.app.state`` namespace so tools can
    read systems/kb_path/etc. as if they were inside a REST handler.
    """
    registry = registry or get_registry()
    from realize_core.mcp_server.held_writes import bind_app_state

    bind_app_state(app_state)  # approved held writes run against this state
    if version is None:
        from realize_core import __version__ as version  # the release, not a hard-coded string
    server: Server = Server(name=name, version=version)

    @server.list_tools()
    async def _list_tools() -> list[mcp_types.Tool]:
        out: list[mcp_types.Tool] = []
        pilot = _is_pilot(current_mcp_user())
        for tool in registry.visible_tools(mcp_config):
            if pilot and not _pilot_may_call(tool.name):
                continue
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


def _is_pilot(user: Any) -> bool:
    """True for a self-serve pilot account (STORY-46)."""
    from realize_core.security.users import is_pilot_user

    return is_pilot_user(getattr(user, "user_id", None))


def _pilot_may_call(name: str) -> bool:
    """Pilot accounts may only call the pilot tools, whatever the host's ``mcp.tools``."""
    from realize_core.wedge.pilot import PILOT_TOOLS

    return name in PILOT_TOOLS


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

    if _is_pilot(user) and not _pilot_may_call(name):
        _audit_call(tool, user, status="forbidden", duration_ms=0, mcp_config=mcp_config)
        return _error(MCPErrorCode.FORBIDDEN, "Pilot accounts can only use the tender register tools.")

    from realize_core.security import agent_access

    # Outside agents (agent tokens and stdio sessions, STORY-37): the same rules
    # as the REST guard. People decide, and a tool without a rule is refused.
    # Checked before any lookup by id.
    agent = agent_access.is_agent_subject(user)
    if agent:
        refused = agent_access.tool_refusal(name)
        if refused:
            _audit_call(tool, user, status="forbidden", duration_ms=0, mcp_config=mcp_config)
            return _error(*refused)

    from realize_core.mcp_server.venture_guard import is_rbac_role, permission_refusal

    # RBAC roles get the same per-tool permissions as the REST API; the
    # MCP-only roles (e.g. "editor") keep the tool-family scope check.
    refusal = permission_refusal(name, user.role)
    if refusal:
        _audit_call(tool, user, status="forbidden", duration_ms=0, mcp_config=mcp_config)
        return _error(MCPErrorCode.INSUFFICIENT_SCOPE, refusal)
    if not is_rbac_role(user.role) and not role_meets_scope(user.role, tool.scope):
        _audit_call(tool, user, status="forbidden", duration_ms=0, mcp_config=mcp_config)
        return _error(
            MCPErrorCode.INSUFFICIENT_SCOPE,
            f"Tool '{name}' requires scope '{tool.scope}'; caller has role '{user.role}'.",
        )

    from realize_core.mcp_server import venture_guard

    allowed = venture_guard.caller_ventures(user)
    refusal = venture_guard.check_call(name, arguments, allowed)
    if refusal:
        _audit_call(tool, user, status="forbidden", duration_ms=0, mcp_config=mcp_config)
        return _error(MCPErrorCode.FORBIDDEN, refusal)

    try:
        if agent and agent_access.must_hold(name):
            # A write by an outside agent: queued for a person, nothing runs now.
            from realize_core.mcp_server.held_writes import hold_write

            result = hold_write(tool, arguments, user)
            held_id = result.get("approval_id")
            _audit_call(
                tool,
                user,
                status="held" if held_id else "error",
                duration_ms=int((time.monotonic() - started) * 1000),
                mcp_config=mcp_config,
                args=arguments,
                result=result,
                approval_id=held_id,
            )
            return [mcp_types.TextContent(type="text", text=_to_text(result))]
        result = venture_guard.filter_result(name, await tool.handler(arguments, app_state, user), allowed)
        if agent:
            from realize_core.mcp_server.held_writes import agent_result

            result = agent_result(name, result, user)
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
    approval_id: str | None = None,
) -> None:
    """Emit an audit log entry for an MCP tool call.

    Args + result are only included when ``mcp_config.audit_full_payload``
    is set or the tool family is ``admin`` (admin calls always log full
    detail regardless of the toggle). A write held for approval
    (``status="held"``) records its ``approval_id``.
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
    if approval_id:
        metadata["approval_id"] = approval_id

    outcome = {"ok": "success", "forbidden": "denied", "held": "held"}.get(status, "error")
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
