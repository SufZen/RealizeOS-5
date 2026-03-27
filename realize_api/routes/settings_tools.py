"""
Tools & Integrations API routes.
"""

import logging
import os

from fastapi import APIRouter, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/tools")
async def get_tools(request: Request):
    """List all registered tools with availability and action schemas."""
    tools = []
    try:
        from realize_core.tools.tool_registry import get_tool_registry

        registry = get_tool_registry()
        for tool in registry._tools.values():
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category.value if hasattr(tool.category, "value") else str(tool.category),
                    "available": tool.is_available(),
                    "actions": [s.name for s in tool.get_schemas()],
                }
            )
    except Exception as exc:
        logger.debug("Tool registry lookup failed: %s", exc)

    # Google Workspace status
    google_status = {"gmail": False, "calendar": False, "drive": False}
    try:
        from realize_core.tools.google_auth import get_credentials

        creds = get_credentials()
        if creds:
            google_status = {"gmail": True, "calendar": True, "drive": True}
    except Exception as exc:
        logger.debug("Google auth check failed: %s", exc)

    # MCP status
    mcp_servers = []
    try:
        from realize_core.tools.mcp import get_mcp_hub

        hub = get_mcp_hub()
        for name, conn in hub._connections.items():
            mcp_servers.append(
                {
                    "name": name,
                    "connected": conn.connected if hasattr(conn, "connected") else False,
                    "tools_count": len(conn.tools) if hasattr(conn, "tools") else 0,
                }
            )
    except Exception as exc:
        logger.debug("MCP hub lookup failed: %s", exc)

    # Browser status
    browser_enabled = os.getenv("BROWSER_ENABLED", "false").lower() == "true"

    # Channels
    config = getattr(request.app.state, "config", {})
    channels_config = config.get("channels", [])
    channels = []
    channels.append({"name": "API", "type": "api", "enabled": True})
    for ch in channels_config:
        channels.append(
            {
                "name": ch.get("name", ch.get("type", "unknown")),
                "type": ch.get("type", "unknown"),
                "enabled": ch.get("enabled", True),
            }
        )

    return {
        "tools": tools,
        "google_workspace": google_status,
        "mcp_servers": mcp_servers,
        "browser_enabled": browser_enabled,
        "channels": channels,
    }
