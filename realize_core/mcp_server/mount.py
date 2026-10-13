"""FastAPI mount helper for the built-in MCP server.

Single entry point — :func:`mount_mcp` — that wires the MCP router into a
FastAPI app *when MCP is enabled in config*. Calling it when MCP is
disabled is a no-op so callers can invoke it unconditionally.

Transports: HTTP+SSE on ``/mcp/sse`` (existing clients) and Streamable HTTP
on ``/mcp`` (Claude.ai connectors). With ``mcp.oauth.enabled`` it also
serves the OAuth 2.1 discovery, registration, authorize and token routes.
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

    app.state.mcp_streamable = None
    if mcp_config.streamable_http:
        from starlette.routing import Route

        from realize_core.mcp_server.streamable import StreamableHTTPEndpoint

        endpoint = StreamableHTTPEndpoint(server)
        app.state.mcp_streamable = endpoint  # started by the app lifespan
        app.router.routes.append(Route("/mcp", endpoint=endpoint, methods=["GET", "POST", "DELETE"]))

    app.state.mcp_oauth = None
    if mcp_config.oauth_enabled:
        _mount_oauth(app, mcp_config)

    logger.info(
        "MCP server mounted at /mcp/sse%s — families=%s, allow_admin=%s, oauth=%s, tools=%s",
        " and /mcp (Streamable HTTP)" if mcp_config.streamable_http else "",
        ",".join(mcp_config.families),
        mcp_config.allow_admin,
        app.state.mcp_oauth is not None,
        ",".join(mcp_config.tools) or "all",
    )
    if mcp_config.tools:
        from realize_core.mcp_server.registry import get_registry

        unknown = get_registry().unknown_names(mcp_config)
        if unknown:
            logger.warning("mcp.tools names tools that don't exist: %s", ", ".join(unknown))
    return mcp_config


def _mount_oauth(app: Any, mcp_config: McpConfig) -> None:
    """Serve the OAuth 2.1 authorization server routes (issue #21).

    Needs ``mcp.public_url`` (the issuer) and the auth middleware: without
    an API key or JWT the middleware isn't installed and ``/mcp`` is open,
    so OAuth would protect nothing.
    """
    import os

    from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
    from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
    from pydantic import AnyHttpUrl

    from realize_core.mcp_server.oauth import RealizeOAuthProvider

    if not mcp_config.public_url:
        logger.error("MCP OAuth not enabled: set MCP_PUBLIC_URL (or mcp.public_url) to the public https:// base URL")
        return
    jwt_enabled = os.environ.get("REALIZE_JWT_ENABLED", "").lower() in ("true", "1", "yes")
    if not os.environ.get("REALIZE_API_KEY") and not jwt_enabled:
        logger.error("MCP OAuth not enabled: auth is off (set REALIZE_API_KEY), so /mcp would stay open")
        return

    issuer = AnyHttpUrl(mcp_config.public_url)
    provider = (
        RealizeOAuthProvider(mcp_config.public_url, mcp_config.oauth_redirect_hosts)
        if mcp_config.oauth_redirect_hosts
        else RealizeOAuthProvider(mcp_config.public_url)
    )
    try:
        routes = create_auth_routes(
            provider,
            issuer_url=issuer,
            # Any scope a client asks for is accepted: access comes from the
            # user's users.yaml role and ventures, not from OAuth scopes.
            client_registration_options=ClientRegistrationOptions(enabled=True, default_scopes=["mcp"]),
            revocation_options=RevocationOptions(enabled=True),
        )
    except ValueError as exc:
        logger.error("MCP OAuth not enabled: %s", exc)
        return
    routes += create_protected_resource_routes(
        resource_url=AnyHttpUrl(mcp_config.resource_url),
        authorization_servers=[issuer],
        scopes_supported=["mcp"],
        resource_name="RealizeOS",
    )

    from realize_api.routes import mcp_oauth

    routes += mcp_oauth.routes()
    app.router.routes.extend(routes)
    app.state.mcp_oauth = provider
    logger.info("MCP OAuth authorization server enabled — issuer %s", mcp_config.public_url)
