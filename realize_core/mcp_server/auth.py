"""Auth bridge between the MCP request and the existing user model.

The SSE endpoint runs through the existing :mod:`realize_api.middleware`
stack, which sets ``request.state.user_id`` / ``request.state.role``. When
the MCP session opens, we capture that :class:`CurrentUser` in a
contextvar; tool handlers retrieve it via :func:`current_mcp_user`.

Production gate: when ``REALIZE_ENV=production`` AND ``mcp.allow_admin``
is true, the server refuses to start unless JWT is enabled with a strong
secret. This prevents admin tools from being exposed over plain API-key
auth in production.
"""

from __future__ import annotations

import contextvars
import logging
import os

from realize_api.dependencies import CurrentUser

logger = logging.getLogger(__name__)

_current_user: contextvars.ContextVar[CurrentUser | None] = contextvars.ContextVar("mcp_current_user", default=None)


def bind_user(user: CurrentUser) -> contextvars.Token:
    """Bind ``user`` as the active MCP request context. Returns the token to reset with."""
    return _current_user.set(user)


def reset_user(token: contextvars.Token) -> None:
    """Reset the active MCP request context."""
    _current_user.reset(token)


def current_mcp_user() -> CurrentUser:
    """Get the user attached to the active MCP request.

    Falls back to an anonymous owner-role user when no binding is in place;
    this matches the dev-mode behaviour of :func:`realize_api.dependencies.get_current_user`
    and keeps unit tests simple. Real auth enforcement happens at the
    middleware layer before the request ever reaches a tool handler.
    """
    user = _current_user.get()
    if user is None:
        return CurrentUser(user_id="anonymous", role="owner", scopes=[])
    return user


class MCPProductionAuthError(RuntimeError):
    """Raised when MCP admin is enabled in production without strong auth."""


def validate_production_auth(*, allow_admin: bool) -> None:
    """Refuse to start the MCP server in unsafe production configurations.

    Called once at server initialization. No-op outside production.
    """
    if os.environ.get("REALIZE_ENV", "").lower() != "production":
        return
    if not allow_admin:
        return

    jwt_enabled = os.environ.get("REALIZE_JWT_ENABLED", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    jwt_secret = os.environ.get("REALIZE_JWT_SECRET", "")
    if not jwt_enabled:
        raise MCPProductionAuthError(
            "MCP admin tools enabled in production without JWT — set "
            "REALIZE_JWT_ENABLED=true (or disable mcp.allow_admin)."
        )
    if len(jwt_secret) < 32:
        raise MCPProductionAuthError(
            "MCP admin tools enabled in production with weak JWT secret — "
            "REALIZE_JWT_SECRET must be at least 32 characters."
        )
