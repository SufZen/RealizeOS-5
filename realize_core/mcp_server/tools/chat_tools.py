"""Chat & status MCP tools — always exposed when MCP is enabled.

Each tool wraps an existing REST route handler in
:mod:`realize_api.routes.chat`, :mod:`realize_api.routes.health`, or
:mod:`realize_api.routes.systems`. No business logic is duplicated; the
tool functions exist only to translate MCP JSON-RPC arguments into the
handler's pydantic-validated input shape.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from realize_api.dependencies import CurrentUser

from realize_core.mcp_server.registry import MCPTool, ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# realize_chat
# ---------------------------------------------------------------------------

REALIZE_CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "Natural-language prompt to send to RealizeOS.",
            "maxLength": 4096,
        },
        "system_key": {
            "type": "string",
            "description": "Target system key (e.g. 'arena', 'realization-il').",
        },
        "user_id": {
            "type": "string",
            "description": "Caller identifier for memory + audit. Defaults to MCP user id.",
        },
        "agent_key": {
            "type": ["string", "null"],
            "description": "Optional explicit agent. If omitted, the router picks one.",
        },
    },
    "required": ["message", "system_key"],
    "additionalProperties": False,
}


async def realize_chat(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Send a chat message through the standard RealizeOS pipeline."""
    from realize_api.routes.chat import ChatRequest
    from realize_api.routes.chat import chat as chat_handler

    body = ChatRequest(
        message=args["message"],
        system_key=args["system_key"],
        user_id=args.get("user_id") or user.user_id,
        agent_key=args.get("agent_key"),
        channel=args.get("channel", "mcp"),
    )

    request = _ProxyRequest(app_state)
    response = await chat_handler(body, request)
    return response.model_dump() if hasattr(response, "model_dump") else response


# ---------------------------------------------------------------------------
# realize_health
# ---------------------------------------------------------------------------

REALIZE_HEALTH_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


async def realize_health(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Lightweight liveness probe — same shape as ``GET /api/health``."""
    return {"status": "ok", "service": "realize-os"}


# ---------------------------------------------------------------------------
# realize_status
# ---------------------------------------------------------------------------

REALIZE_STATUS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


async def realize_status(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Detailed system status — mirrors ``GET /api/status``."""
    systems = getattr(app_state, "systems", {}) or {}

    llm = {}
    if os.environ.get("ANTHROPIC_API_KEY"):
        llm["anthropic"] = "configured"
    if os.environ.get("GOOGLE_AI_API_KEY"):
        llm["google"] = "configured"
    if os.environ.get("OPENAI_API_KEY"):
        llm["openai"] = "configured"

    return {
        "status": "ok",
        "service": "realize-os",
        "systems": {
            k: {"name": v.get("name", k), "agents": list(v.get("agents", {}).keys())} for k, v in systems.items()
        },
        "llm": llm,
    }


# ---------------------------------------------------------------------------
# list_systems / get_system
# ---------------------------------------------------------------------------

LIST_SYSTEMS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}

GET_SYSTEM_SCHEMA = {
    "type": "object",
    "properties": {"system_key": {"type": "string"}},
    "required": ["system_key"],
    "additionalProperties": False,
}


async def list_systems(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    systems = getattr(app_state, "systems", {}) or {}
    return {
        "systems": [
            {
                "key": key,
                "name": config.get("name", key),
                "agents": list(config.get("agents", {}).keys()),
                "routing": dict(config.get("routing", {})),
            }
            for key, config in systems.items()
        ]
    }


async def get_system(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    systems = getattr(app_state, "systems", {}) or {}
    key = args["system_key"]
    if key not in systems:
        return {"error": f"System '{key}' not found", "code": "MCP_NOT_FOUND"}
    config = systems[key]
    return {
        "key": key,
        "name": config.get("name", key),
        "agents": list(config.get("agents", {}).keys()),
        "routing": config.get("routing", {}),
        "brand_identity": config.get("brand_identity"),
        "brand_voice": config.get("brand_voice"),
    }


# ---------------------------------------------------------------------------
# list_agents
# ---------------------------------------------------------------------------

LIST_AGENTS_SCHEMA = {
    "type": "object",
    "properties": {"system_key": {"type": "string"}},
    "required": ["system_key"],
    "additionalProperties": False,
}


async def list_agents(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    systems = getattr(app_state, "systems", {}) or {}
    key = args["system_key"]
    if key not in systems:
        return {"error": f"System '{key}' not found", "code": "MCP_NOT_FOUND"}
    agents = systems[key].get("agents", {})
    return {
        "system_key": key,
        "agents": [{"key": agent_key, "path": path} for agent_key, path in agents.items()],
    }


# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------

LIST_SKILLS_SCHEMA = {
    "type": "object",
    "properties": {"system_key": {"type": "string"}},
    "required": ["system_key"],
    "additionalProperties": False,
}


async def list_skills(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    try:
        from realize_core.skills.detector import get_skills_for_system

        skills = get_skills_for_system(args["system_key"])
    except Exception as exc:
        logger.debug("list_skills failed: %s", exc)
        return {"system_key": args["system_key"], "skills": [], "error": str(exc)[:200]}

    return {
        "system_key": args["system_key"],
        "skills": [
            {
                "name": s.get("name", ""),
                "triggers": s.get("triggers", []),
                "version": s.get("_version", 1),
            }
            for s in skills
        ],
    }


# ---------------------------------------------------------------------------
# get_history / clear_history
# ---------------------------------------------------------------------------

GET_HISTORY_SCHEMA = {
    "type": "object",
    "properties": {
        "system_key": {"type": "string"},
        "user_id": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
    },
    "required": ["system_key", "user_id"],
    "additionalProperties": False,
}

CLEAR_HISTORY_SCHEMA = {
    "type": "object",
    "properties": {
        "system_key": {"type": "string"},
        "user_id": {"type": "string"},
    },
    "required": ["system_key", "user_id"],
    "additionalProperties": False,
}


async def get_history(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    try:
        from realize_core.memory.conversation import get_history as _get_history

        history = _get_history(args["system_key"], args["user_id"], limit=min(args.get("limit", 50), 200))
        return {
            "system_key": args["system_key"],
            "user_id": args["user_id"],
            "messages": history,
        }
    except Exception as exc:
        logger.warning("get_history failed: %s", exc)
        return {"system_key": args["system_key"], "user_id": args["user_id"], "messages": []}


async def clear_history(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    try:
        from realize_core.memory.conversation import clear_history as _clear_history

        _clear_history(args["system_key"], args["user_id"])
        return {"status": "cleared", "system_key": args["system_key"], "user_id": args["user_id"]}
    except Exception as exc:
        logger.warning("clear_history failed: %s", exc)
        return {"status": "error", "error": str(exc)[:200], "code": "MCP_INTERNAL"}


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------

GET_SESSION_SCHEMA = {
    "type": "object",
    "properties": {
        "system_key": {"type": "string"},
        "user_id": {"type": "string"},
    },
    "required": ["system_key", "user_id"],
    "additionalProperties": False,
}


async def get_session(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    try:
        from realize_core.pipeline.session import get_session as _get_session

        session = _get_session(args["system_key"], args["user_id"])
    except Exception as exc:
        logger.debug("get_session failed: %s", exc)
        return {"system_key": args["system_key"], "user_id": args["user_id"], "session": None}

    if session is None:
        return {"system_key": args["system_key"], "user_id": args["user_id"], "session": None}

    return {
        "system_key": args["system_key"],
        "user_id": args["user_id"],
        "active_agent": getattr(session, "active_agent", None),
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="realize_chat",
        family="chat",
        description="Send a message to a RealizeOS system and get an AI response.",
        input_schema=REALIZE_CHAT_SCHEMA,
        scope="read",
        handler=realize_chat,
    ),
    MCPTool(
        name="realize_health",
        family="chat",
        description="Lightweight liveness probe — confirms the RealizeOS instance is reachable.",
        input_schema=REALIZE_HEALTH_SCHEMA,
        scope="read",
        handler=realize_health,
    ),
    MCPTool(
        name="realize_status",
        family="chat",
        description="Detailed status: configured systems, available LLM providers.",
        input_schema=REALIZE_STATUS_SCHEMA,
        scope="read",
        handler=realize_status,
    ),
    MCPTool(
        name="list_systems",
        family="chat",
        description="List all configured systems (ventures + their routing).",
        input_schema=LIST_SYSTEMS_SCHEMA,
        scope="read",
        handler=list_systems,
    ),
    MCPTool(
        name="get_system",
        family="chat",
        description="Detailed config + brand profile for a single system.",
        input_schema=GET_SYSTEM_SCHEMA,
        scope="read",
        handler=get_system,
    ),
    MCPTool(
        name="list_agents",
        family="chat",
        description="List agents for a system.",
        input_schema=LIST_AGENTS_SCHEMA,
        scope="read",
        handler=list_agents,
    ),
    MCPTool(
        name="list_skills",
        family="chat",
        description="List available skills (R-routines) for a system.",
        input_schema=LIST_SKILLS_SCHEMA,
        scope="read",
        handler=list_skills,
    ),
    MCPTool(
        name="get_history",
        family="chat",
        description="Get recent conversation history for a (system, user) pair.",
        input_schema=GET_HISTORY_SCHEMA,
        scope="read",
        handler=get_history,
    ),
    MCPTool(
        name="clear_history",
        family="chat",
        description="Clear conversation history for a (system, user) pair.",
        input_schema=CLEAR_HISTORY_SCHEMA,
        scope="editor",
        handler=clear_history,
    ),
    MCPTool(
        name="get_session",
        family="chat",
        description="Get the active session (current agent) for a (system, user) pair.",
        input_schema=GET_SESSION_SCHEMA,
        scope="read",
        handler=get_session,
    ),
)


def register(registry: ToolRegistry) -> None:
    """Register every chat & status tool with the shared registry."""
    for tool in _TOOLS:
        registry.register(tool)


# ---------------------------------------------------------------------------
# Internal: proxy request object so we can call REST handlers in-process.
# ---------------------------------------------------------------------------


class _ProxyRequest:
    """Minimal stand-in for ``fastapi.Request`` used inside MCP tool handlers.

    REST route handlers only read ``request.app.state`` for the runtime
    state they need (systems, kb_path, shared_config). We give them a
    namespace object with that ``app.state`` and nothing else; any handler
    that reaches for something we haven't provided will fail loudly, which
    is the right outcome — that handler shouldn't be exposed as a tool
    yet.
    """

    __slots__ = ("app",)

    def __init__(self, app_state: Any) -> None:
        self.app = _ProxyApp(app_state)


class _ProxyApp:
    __slots__ = ("state",)

    def __init__(self, app_state: Any) -> None:
        self.state = app_state
