"""FastAPI mount helper for the built-in MCP server.

Single entry point — :func:`mount_mcp` — that wires the MCP router into a
FastAPI app *when MCP is enabled in config*. Calling it when MCP is
disabled is a no-op so callers can invoke it unconditionally.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.sse import SseServerTransport

from realize_core.mcp_server.auth import validate_production_auth
from realize_core.mcp_server.config import McpConfig, mcp_config_from_env
from realize_core.mcp_server.server import build_mcp_server

logger = logging.getLogger(__name__)

#: Path prefix used inside ``SseServerTransport`` for messages POSTs.
#: Must match the route prefix declared in ``realize_api/main.py``.
MCP_MESSAGES_ENDPOINT = "/mcp/messages/"


def mount_mcp(app: Any, *, config: dict | None = None) -> McpConfig:
    """Mount the MCP router on ``app`` when enabled.

    Returns the effective :class:`McpConfig` so callers can log it or
    stash it on ``app.state`` for the ``/mcp/health`` probe.
    """
    mcp_config = mcp_config_from_env(config)
    app.state.mcp_config = mcp_config

    if not mcp_config.enabled:
        logger.info("MCP server disabled (set MCP_ENABLED=true or mcp.enabled: true to enable)")
        return mcp_config

    validate_production_auth(allow_admin=mcp_config.allow_admin)

    from realize_api.routes import mcp as mcp_router_module

    server = build_mcp_server(app_state=app.state, mcp_config=mcp_config)
    transport = SseServerTransport(MCP_MESSAGES_ENDPOINT)
    mcp_router_module.attach(server, transport)

    app.include_router(mcp_router_module.router, prefix="/mcp", tags=["MCP"])
    # SDK-standard: serve the JSON-RPC POST endpoint as a raw ASGI app so the
    # query-param session URL (/mcp/messages/?session_id=) is matched and the
    # transport emits its own 202 (avoids the path-param 405 + double-send).
    from starlette.routing import Mount
    app.router.routes.append(Mount("/mcp/messages", app=transport.handle_post_message))

    logger.info(
        "MCP server mounted at /mcp/sse — families=%s, allow_admin=%s",
        ",".join(mcp_config.families),
        mcp_config.allow_admin,
    )
    return mcp_config
