"""
Health and status endpoints.
"""

import logging
import os

from fastapi import APIRouter, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health():
    """Basic health check."""
    return {"status": "ok", "service": "realize-os"}


@router.get("/status")
async def status(request: Request):
    """Detailed system status."""
    systems = request.app.state.systems

    # Check LLM availability
    llm_status = {}
    if os.environ.get("ANTHROPIC_API_KEY"):
        llm_status["anthropic"] = "configured"
    if os.environ.get("GOOGLE_AI_API_KEY"):
        llm_status["google"] = "configured"

    # Check tool availability
    tools_status = {}
    if os.environ.get("BRAVE_API_KEY"):
        tools_status["web_search"] = "configured"
    if os.environ.get("BROWSER_ENABLED", "").lower() == "true":
        tools_status["browser"] = "enabled"

    try:
        from realize_core.tools.google_auth import get_credentials

        if get_credentials():
            tools_status["google_workspace"] = "authenticated"
        else:
            tools_status["google_workspace"] = "not configured"
    except Exception:
        tools_status["google_workspace"] = "not available"

    # MCP status
    try:
        from realize_core.tools.mcp import get_mcp_hub

        hub = get_mcp_hub()
        if hub.servers:
            connected = sum(1 for s in hub.servers.values() if s.connected)
            tools_status["mcp"] = f"{connected}/{len(hub.servers)} servers"
    except Exception:
        pass

    # Memory stats
    memory_status = {}
    try:
        from realize_core.utils.cost_tracker import get_usage_summary

        memory_status["llm_usage"] = get_usage_summary()
    except Exception:
        pass

    return {
        "status": "ok",
        "version": "0.1.0",
        "systems": {
            k: {"name": v.get("name", k), "agents": list(v.get("agents", {}).keys())} for k, v in systems.items()
        },
        "llm": llm_status,
        "tools": tools_status,
        "memory": memory_status,
    }
