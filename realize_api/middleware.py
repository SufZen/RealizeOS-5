"""
Unified API authentication middleware.

Replaces the v5.1.0 ``APIKeyMiddleware`` (and the ``JWTAuthMiddleware`` that
used to live in ``security_middleware.py``) with a single middleware that
accepts any of three credential types:

1. **Cookie session** — ``realize_session`` (HttpOnly) → looked up in
   ``user_sessions``. The browser dashboard uses this exclusively.
2. **API key** — ``X-API-Key`` header, ``Authorization: Bearer <key>``, or
   ``?api_key=<key>``. Used by CLI, Telegram bot, and any programmatic caller.
3. **JWT bearer** — ``Authorization: Bearer <jwt>`` when ``REALIZE_JWT_ENABLED=true``.

A request is authenticated as soon as any of the three succeed. Public paths
(health, docs, static assets, login endpoint, favicon) skip auth entirely.

Mutating cookie-session requests must additionally pass a CSRF check
(double-submit pattern): the ``X-Realize-CSRF`` header must match the
``realize_csrf`` cookie. API-key and JWT requests are exempt — they're
programmatic, not browser-driven.
"""

from __future__ import annotations

import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from realize_core.security import session_store

logger = logging.getLogger(__name__)


# Paths that bypass authentication entirely.
_PUBLIC_API_PATHS = frozenset({
    "/api/health",
    "/api/status",
    "/api/auth/login",
    "/api/auth/session",   # SPA can ask "am I logged in?" without being logged in
    "/api/auth/token",     # bootstraps a JWT pair from an API key
    "/api/auth/refresh",   # refreshes a JWT using a refresh token (self-authenticating)
})

_PUBLIC_NON_API_PATHS = frozenset({
    "/health",
    "/status",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.svg",
    "/icons.svg",
})

_PUBLIC_PREFIXES = ("/assets/",)

# Methods that must pass the CSRF double-submit check when authenticated via cookie.
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _is_public(path: str) -> bool:
    """True for paths that need no authentication."""
    if path in _PUBLIC_API_PATHS or path in _PUBLIC_NON_API_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        return True
    # Anything that isn't under /api/, /mcp/, or a static dotfile is dashboard SPA HTML.
    # The SPA itself is harmless to serve unauthenticated — the auth-guard inside React
    # handles redirecting to /login.
    if not path.startswith("/api/") and not path.startswith("/mcp/"):
        return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """Unified credential check for the API.

    Resolution order on each request:
    1. Public path → pass through.
    2. ``realize_session`` cookie → look up session, attach user, enforce CSRF.
    3. ``X-API-Key`` / ``Authorization: Bearer <api-key>`` / ``?api_key=`` → match
       ``REALIZE_API_KEY``, attach the configured owner identity.
    4. ``Authorization: Bearer <jwt>`` → verify via ``jwt_auth``, attach claims.
    5. No match → 401.
    """

    def __init__(self, app, api_key: str = "", jwt_enabled: bool = False):
        super().__init__(app)
        self.api_key = api_key or ""
        self.jwt_enabled = bool(jwt_enabled)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if _is_public(path):
            return await call_next(request)

        # 1. Cookie session
        session_id = request.cookies.get(session_store.SESSION_COOKIE_NAME, "")
        if session_id:
            record = session_store.get_session(session_id)
            if record is not None:
                csrf_failure = self._enforce_csrf(request, record)
                if csrf_failure is not None:
                    return csrf_failure

                request.state.user_id = record.user_id
                request.state.role = record.role
                request.state.scopes = []
                request.state.auth_source = "session"
                # Best-effort: keep last_seen_at fresh on activity.
                try:
                    session_store.touch_session(session_id)
                except Exception as exc:
                    logger.debug("touch_session failed: %s", exc)
                return await call_next(request)
            # Cookie present but session unknown — fall through to other methods.

        # 2. API key
        provided_key = self._extract_api_key(request)
        if self.api_key and provided_key and provided_key == self.api_key:
            request.state.user_id = os.environ.get("REALIZE_API_KEY_USER", "api-key")
            request.state.role = "owner"
            request.state.scopes = []
            request.state.auth_source = "api_key"
            return await call_next(request)

        # 3. JWT bearer
        if self.jwt_enabled:
            jwt_failure_or_pass = await self._try_jwt(request)
            if jwt_failure_or_pass is True:  # authenticated
                return await call_next(request)
            if jwt_failure_or_pass is not None:  # explicit failure response
                return jwt_failure_or_pass
            # else: no Bearer token present — keep going

        # Nothing matched.
        return JSONResponse(
            status_code=401,
            content={"error": "auth_required", "message": "Authentication required."},
        )

    # ------------------------------------------------------------------ helpers

    def _enforce_csrf(self, request: Request, record: session_store.SessionRecord):
        """Return a 403 response if CSRF check fails, else None."""
        if request.method not in _MUTATING_METHODS:
            return None
        header = request.headers.get(session_store.CSRF_HEADER_NAME, "")
        if not header or header != record.csrf_token:
            logger.warning(
                "CSRF check failed on %s for user %s (header=%r)",
                request.url.path, record.user_id, bool(header),
            )
            return JSONResponse(
                status_code=403,
                content={"error": "csrf_failed", "message": "CSRF token missing or invalid."},
            )
        return None

    def _extract_api_key(self, request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        api_key_header = request.headers.get("X-API-Key", "")
        query_key = request.query_params.get("api_key", "")

        if api_key_header:
            return api_key_header
        if query_key:
            return query_key
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            # Ambiguous: could be API key or JWT. JWTs have two dots — API keys typically don't.
            if "." not in token:
                return token
        return ""

    async def _try_jwt(self, request: Request):
        """Attempt JWT auth. Returns True on success, a Response on failure, None if no token."""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:]
        if "." not in token:
            return None  # looks like an API key, not a JWT — already handled above

        try:
            from realize_core.security.jwt_auth import (
                InvalidTokenError,
                TokenExpiredError,
                TokenRevokedError,
                verify_token,
            )

            claims = verify_token(token, require_type="access")
            request.state.user_id = claims.sub
            request.state.role = claims.role
            request.state.scopes = claims.scopes
            request.state.jwt_claims = claims
            request.state.auth_source = "jwt"
            return True
        except TokenExpiredError:
            return JSONResponse(
                status_code=401,
                content={"error": "token_expired", "message": "Your session has expired. Please log in again."},
            )
        except InvalidTokenError as exc:
            return JSONResponse(
                status_code=401,
                content={"error": "invalid_token", "message": str(exc)},
            )
        except TokenRevokedError:
            return JSONResponse(
                status_code=401,
                content={"error": "token_revoked", "message": "This token has been revoked."},
            )
        except Exception as exc:
            logger.debug("JWT verification failed: %s", exc)
            return JSONResponse(
                status_code=401,
                content={"error": "auth_error", "message": "Authentication failed."},
            )


# Backwards-compatibility alias — some external code (tests, plugins) may still
# import ``APIKeyMiddleware`` from this module. Make it a thin wrapper.
class APIKeyMiddleware(AuthMiddleware):
    """Deprecated: prefer ``AuthMiddleware``. Kept as an alias for v5.1.x compatibility."""

    def __init__(self, app, api_key: str):
        super().__init__(app, api_key=api_key, jwt_enabled=False)
