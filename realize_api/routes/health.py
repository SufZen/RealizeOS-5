"""
Health and status endpoints.
"""

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from realize_core import __version__

from realize_api.dependencies import visible_systems

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health(request: Request):
    """Liveness plus store readiness.

    503 when a required store (the operational DB) failed to initialize, so a
    probe notices instead of seeing "ok" while sign-in and approvals are broken.
    Optional stores that failed make the status "degraded". Only store names
    are reported: this endpoint is public.
    """
    errors: dict[str, str] = getattr(request.app.state, "store_errors", None) or {}
    required = sorted(name for name, kind in errors.items() if kind == "required")
    optional = sorted(name for name, kind in errors.items() if kind != "required")
    if required:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "service": "realize-os", "failed": required + optional},
        )
    if optional:
        return {"status": "degraded", "service": "realize-os", "failed": optional}
    return {"status": "ok", "service": "realize-os"}


@router.get("/status")
async def status(request: Request):
    """Detailed system status."""
    systems = visible_systems(request)

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

    # Only attempt Google Workspace check if credentials file exists
    try:
        import importlib

        if importlib.util.find_spec("google.auth") and os.path.exists(
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ".credentials/google-oauth.json")
        ):
            from realize_core.tools.google_auth import get_credentials

            if get_credentials():
                tools_status["google_workspace"] = "authenticated"
            else:
                tools_status["google_workspace"] = "not configured"
        else:
            tools_status["google_workspace"] = "not configured"
    except Exception as exc:
        logger.debug("Google workspace check failed: %s", exc)
        tools_status["google_workspace"] = "not available"

    # MCP status
    try:
        from realize_core.tools.mcp import get_mcp_hub

        hub = get_mcp_hub()
        if hub.servers:
            connected = sum(1 for s in hub.servers.values() if s.connected)
            tools_status["mcp"] = f"{connected}/{len(hub.servers)} servers"
    except Exception as exc:
        logger.debug("MCP status check failed: %s", exc)

    # Memory stats
    memory_status = {}
    try:
        from realize_core.utils.cost_tracker import get_usage_summary

        memory_status["llm_usage"] = get_usage_summary()
    except Exception as exc:
        logger.debug("LLM usage stats failed: %s", exc)

    return {
        "status": "ok",
        "version": __version__,
        "systems": {
            k: {
                "name": v.get("name", k),
                "agents": list(v.get("agents", {}).keys()),
                "warnings": list(v.get("warnings") or []),
            }
            for k, v in systems.items()
        },
        "llm": llm_status,
        "tools": tools_status,
        "memory": memory_status,
    }
