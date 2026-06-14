"""FastAPI router exposing the built-in RealizeOS MCP server.

Two endpoints, both protected by the existing auth middleware stack:

* ``GET /mcp/sse``                       — SSE handshake (long-lived)
* ``POST /mcp/messages/{session_id}``    — JSON-RPC payloads from the client

The router is only mounted when MCP is enabled (``mcp.enabled: true`` or
``MCP_ENABLED=true``). When disabled, these routes do not exist and any
request to them returns 404 from FastAPI's default handler.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from realize_core.mcp_server.auth import bind_user, reset_user
from starlette.responses import Response

from realize_api.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def attach(mcp_server: Server, sse_transport: SseServerTransport) -> None:
    """Bind the FastAPI router to the configured MCP server + transport."""
    router.state = {"server": mcp_server, "transport": sse_transport}  # type: ignore[attr-defined]


def _resources() -> tuple[Server, SseServerTransport]:
    state = getattr(router, "state", None)
    if not state or "server" not in state or "transport" not in state:
        raise HTTPException(status_code=503, detail="MCP server not initialized")
    return state["server"], state["transport"]


@router.get("/sse", include_in_schema=False)
async def sse_endpoint(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    """Open an SSE stream for an MCP client and run the server loop on it."""
    server, transport = _resources()
    token = bind_user(user)
    try:
        async with transport.connect_sse(
            request.scope,
            request.receive,
            request._send,  # type: ignore[arg-type]
        ) as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        reset_user(token)
    return Response(status_code=200)


@router.get("/health", include_in_schema=False)
async def mcp_health(request: Request) -> dict:
    """Lightweight liveness probe for monitoring (no auth required)."""
    from realize_core.mcp_server.registry import get_registry

    try:
        server, _ = _resources()
    except HTTPException:
        return {"ok": False, "tools": 0, "reason": "not initialized"}

    registry = get_registry()
    mcp_config = getattr(request.app.state, "mcp_config", None)
    if mcp_config is None:
        visible = registry.all()
    else:
        visible = registry.visible_tools(mcp_config)
    return {
        "ok": True,
        "name": getattr(server, "name", "realize-os"),
        "tools": len(visible),
        "families": getattr(mcp_config, "families", []),
    }
