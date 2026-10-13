"""Per-principal rate limits for MCP tool calls.

The HTTP rate limiter (:class:`realize_api.security_middleware.RateLimitMiddleware`)
lets ``/mcp`` and ``/mcp/*`` stream through untouched: buffering them would
break the SSE and Streamable HTTP transports. So the dispatcher limits each
``tools/call`` itself, after the connection is open, and the stream is never
touched: a limited call gets an ``MCP_RATE_LIMITED`` error and the session
carries on.

Buckets match the HTTP limiter's (:func:`realize_api.security_middleware._rate_limit_key`):

- an agent token has its own bucket, ``agent:<token id>``, apart from the
  person it acts for;
- a local stdio session has ``agent:stdio:<email>``;
- anyone else signed in has ``user:<id>``;
- an anonymous caller (auth off) is limited by client address, ``ip:<address>``.

The limit is ``MCP_RATE_LIMIT_PER_MINUTE`` (or ``mcp.rate_limit_per_minute``),
else ``API_RATE_LIMIT_PER_MINUTE``. MCP calls are counted apart from HTTP
requests, so a person's dashboard traffic doesn't use up their agent's calls.
"""

from __future__ import annotations

import logging
from typing import Any

from realize_core.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

#: Seconds a limited caller is told to wait (the limiter's window).
RETRY_AFTER_SECONDS = 60

#: Limiter for dispatches with no app state to keep one on.
_fallback: RateLimiter | None = None


def limit_per_minute(configured: int | None = None) -> int:
    """Tool calls each principal may make per minute.

    Args:
        configured: ``McpConfig.rate_limit_per_minute`` (None when unset).

    Returns:
        ``configured`` when set, else ``API_RATE_LIMIT_PER_MINUTE``.
    """
    if configured:
        return configured
    from realize_core.config import API_RATE_LIMIT_PER_MINUTE

    return API_RATE_LIMIT_PER_MINUTE


def get_mcp_rate_limiter(app_state: Any, configured: int | None = None) -> RateLimiter:
    """The MCP tool-call limiter kept on ``app_state`` (one per app, like the HTTP one).

    Args:
        app_state: The app state the dispatcher runs against.
        configured: ``McpConfig.rate_limit_per_minute``, used when the limiter is created.
    """
    limiter = getattr(app_state, "mcp_rate_limiter", None)
    if isinstance(limiter, RateLimiter):
        return limiter
    limiter = RateLimiter(requests_per_minute=limit_per_minute(configured))
    try:
        app_state.mcp_rate_limiter = limiter
    except AttributeError:
        # No state to keep it on (None, or a frozen object): share one per process.
        global _fallback
        if _fallback is None:
            _fallback = limiter
        return _fallback
    return limiter


def principal_key(user: Any, request: Any = None) -> str:
    """The rate-limit bucket of an MCP caller.

    Args:
        user: The MCP caller (``user_id`` and ``scopes``).
        request: The HTTP request behind the call, for an anonymous caller's
            address; looked up from the MCP request context when omitted.

    Returns:
        ``agent:<token id>``, ``agent:stdio:<email>``, ``user:<id>`` or ``ip:<address>``.
    """
    from realize_core.security.agent_tokens import principal_id_for

    user_id = getattr(user, "user_id", None)
    agent = principal_id_for(user_id, getattr(user, "scopes", None))
    if agent:
        return agent
    if user_id and user_id != "anonymous":
        return f"user:{user_id}"
    request = request if request is not None else _current_request()
    if request is None or getattr(request, "client", None) is None:
        return "ip:anonymous"
    from realize_api.security_middleware import _client_address

    return f"ip:{_client_address(request)}"


def _current_request() -> Any:
    """The HTTP request behind the current MCP message, or None (stdio, tests)."""
    from mcp.server.lowlevel.server import request_ctx

    try:
        return request_ctx.get().request
    except LookupError:
        return None


def allow_call(app_state: Any, user: Any, configured: int | None = None) -> tuple[bool, str]:
    """Count one tool call by ``user`` and say whether it may run.

    A refused call is not counted, like the HTTP limiter: waiting a minute
    always frees the bucket.

    Returns:
        ``(allowed, bucket)``.
    """
    limiter = get_mcp_rate_limiter(app_state, configured)
    key = principal_key(user)
    if not limiter.check_rate_limit(key):
        return False, key
    limiter.record_request(key)
    return True, key
