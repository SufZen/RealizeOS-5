"""Streamable HTTP transport for the built-in MCP server (issue #21, STORY-37).

Claude.ai custom connectors speak MCP over Streamable HTTP: one endpoint
(``/mcp``) that takes JSON-RPC ``POST``s. It runs next to the older
HTTP+SSE transport (``/mcp/sse``), which stays for existing clients.

The server runs **stateless**: each request is handled on its own, so
nothing breaks behind several workers or after a restart, and the caller
is resolved per request by the auth middleware (see
:func:`realize_core.mcp_server.auth.current_mcp_user`). Responses are plain
JSON, which passes through reverse proxies that buffer streams.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class StreamableHTTPEndpoint:
    """ASGI app for ``/mcp``.

    The SDK session manager can run only once, so a fresh one is made each
    time the app's lifespan starts (:meth:`running`). Requests outside the
    lifespan get a 503.
    """

    def __init__(self, server: Server):
        self.server = server
        self._manager: StreamableHTTPSessionManager | None = None

    @asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        """Run the transport for the lifetime of the app."""
        manager = StreamableHTTPSessionManager(app=self.server, stateless=True, json_response=True)
        async with manager.run():
            self._manager = manager
            logger.info("MCP Streamable HTTP transport running at /mcp")
            try:
                yield
            finally:
                self._manager = None

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if self._manager is None:
            response = JSONResponse(
                status_code=503,
                content={"error": "mcp_unavailable", "message": "MCP transport is not running."},
            )
            await response(scope, receive, send)
            return
        await self._manager.handle_request(scope, receive, send)
