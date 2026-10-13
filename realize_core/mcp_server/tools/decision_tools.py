"""Decision log tools (STORY-44), in the ``ops`` family.

``log_decision`` lets an outside agent record a decision made outside
RealizeOS (a meeting, a call, a WhatsApp thread). Nothing is written straight
away: the proposal goes to the approval queue, and the decision is recorded
only when a person approves it there.
"""

from __future__ import annotations

import logging
from typing import Any

from realize_api.dependencies import CurrentUser

from realize_core.mcp_server.registry import MCPTool, ToolRegistry

logger = logging.getLogger(__name__)

LOG_DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "venture_key": {"type": "string"},
        "title": {"type": "string", "maxLength": 200},
        "statement": {"type": "string", "maxLength": 5000, "description": "What was decided, and why."},
        "basis": {
            "type": "array",
            "maxItems": 20,
            "description": "Where the decision is recorded: source (file, message, URL) and locator (page, timestamp).",
            "items": {
                "type": "object",
                "properties": {"source": {"type": "string"}, "locator": {"type": "string"}},
                "required": ["source"],
            },
        },
        "affects": {"type": "array", "items": {"type": "string"}, "maxItems": 50},
        "project": {"type": "string"},
    },
    "required": ["venture_key", "title", "statement"],
    "additionalProperties": False,
}


async def log_decision(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Propose a decision for the venture's decision log; a person confirms it."""
    venture_key = (args.get("venture_key") or "").strip()
    systems = getattr(app_state, "systems", {}) or {}
    if venture_key not in systems:
        return {"error": f"Venture '{venture_key}' not found", "code": "MCP_NOT_FOUND"}
    title = (args.get("title") or "").strip()
    statement = (args.get("statement") or "").strip()
    if not title or not statement:
        return {"error": "title and statement are required", "code": "MCP_VALIDATION"}

    from realize_core.governance.decision_log import propose_decision
    from realize_core.governance.gates import TooManyPendingError
    from realize_core.security.agent_tokens import principal_id_for

    basis = args.get("basis") or []
    user_id = getattr(user, "user_id", None)
    # An outside agent proposes as itself (agent:<id>, or agent:stdio:<email> for a
    # stdio session), so the queue shows it came from outside.
    requested_by = principal_id_for(user_id, getattr(user, "scopes", None)) or user_id or "mcp"
    try:
        approval_id = propose_decision(
            venture_key,
            title=title,
            statement=statement,
            basis=basis,
            affects=args.get("affects"),
            project=args.get("project"),
            requested_by=requested_by,
        )
    except TooManyPendingError as exc:
        return {"error": str(exc), "code": "MCP_TOO_MANY_PENDING"}
    located = any(isinstance(b, dict) and b.get("locator") for b in basis)
    return {
        "status": "pending_approval",
        "approval_id": approval_id,
        "message": "Queued for a person to confirm. It is recorded in the decision log once approved.",
        "unverified": not located,
    }


_TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="log_decision",
        family="ops",
        description=(
            "Propose a decision made outside RealizeOS (meeting, call, message) for the venture's decision log. "
            "Include the source and a locator. A person confirms it in the approval queue before it is recorded."
        ),
        input_schema=LOG_DECISION_SCHEMA,
        scope="editor",
        handler=log_decision,
    ),
)


def register(registry: ToolRegistry) -> None:
    """Register the decision tools with the shared registry."""
    for tool in _TOOLS:
        registry.register(tool)
