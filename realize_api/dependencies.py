"""
FastAPI dependency injection for security features.

Provides reusable ``Depends(...)`` callables for routes:

- ``get_current_user``   — extract user info from request state (set by middleware)
- ``require_role``       — RBAC gate: ensure the user has a specific role/permission
- ``sanitized_body``     — run user input through the sanitizer before processing
- ``get_audit``          — inject the audit logger into a route
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException, Request

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Current User
# ---------------------------------------------------------------------------


class CurrentUser:
    """Lightweight user context extracted from request."""

    def __init__(self, user_id: str, role: str, scopes: list[str] | None = None):
        self.user_id = user_id
        self.role = role
        self.scopes = scopes or []

    def __repr__(self) -> str:
        return f"CurrentUser(user_id={self.user_id!r}, role={self.role!r})"


async def get_current_user(request: Request) -> CurrentUser:
    """
    Extract the current user from request state.

    Falls back to "anonymous" / "owner" when auth is off (dev mode).
    """
    user_id = getattr(request.state, "user_id", None) or request.headers.get("X-User-ID", "anonymous")
    role = getattr(request.state, "role", None) or "owner"  # default to owner when no auth
    scopes = getattr(request.state, "scopes", None) or []
    return CurrentUser(user_id=user_id, role=role, scopes=scopes)


# ---------------------------------------------------------------------------
# 2. RBAC Gate
# ---------------------------------------------------------------------------


def require_permission(permission: str):
    """
    FastAPI dependency that enforces a specific RBAC permission.

    Usage::

        @router.post("/agents/{key}/run")
        async def run_agent(
            key: str,
            user: CurrentUser = Depends(require_permission("agents:execute")),
        ):
            ...

    Returns the CurrentUser if access is granted.
    Raises HTTP 403 if denied.
    """

    async def _check(
        request: Request,
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        try:
            from realize_core.security.rbac import get_rbac_manager

            rbac = get_rbac_manager()
            system_key = request.path_params.get("system_key", "")
            decision = rbac.check_access(user.role, permission, system_key)

            if decision.denied:
                # Audit the denial
                try:
                    from realize_core.security.audit import get_audit_logger

                    get_audit_logger().log_access_denied(
                        user_id=user.user_id,
                        action=f"{request.method} {request.url.path}",
                        permission=permission,
                        role=user.role,
                        channel="api",
                        ip_address=request.client.host if request.client else "",
                    )
                except Exception as exc:
                    logger.debug("Audit log for access denial failed: %s", exc)

                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied: {decision.reason}",
                )
        except HTTPException:
            raise
        except Exception as exc:
            # If RBAC module is unavailable, fail open in dev mode
            logger.debug("RBAC check skipped: %s", exc)

        return user

    return _check


# ---------------------------------------------------------------------------
# 3. Input Sanitization
# ---------------------------------------------------------------------------


async def sanitized_body(request: Request) -> dict[str, Any]:
    """
    Dependency that sanitizes JSON request body.

    Runs every text field through the sanitizer, truncating
    overly-long inputs and flagging injection patterns.

    Attaches sanitization metadata to ``request.state.sanitization``.
    """
    body = await request.json()
    if not isinstance(body, dict):
        return body

    try:
        from realize_core.security.sanitizer import sanitize_input

        config = getattr(request.app.state, "config", None)
        channel = body.get("channel", "api")

        for key in ("message", "text", "prompt", "content", "query"):
            if key in body and isinstance(body[key], str):
                result = sanitize_input(body[key], channel=channel, config=config)
                body[key] = result["text"]

                if result["injection_detected"]:
                    logger.warning(
                        "Sanitizer: injection detected in field '%s' on %s",
                        key,
                        request.url.path,
                    )
                if result["warnings"]:
                    request.state.sanitization_warnings = result["warnings"]

    except Exception as exc:
        logger.debug("Body sanitization failed: %s", exc)

    return body


# ---------------------------------------------------------------------------
# 4. Audit Logger
# ---------------------------------------------------------------------------


async def get_audit():
    """Inject the global audit logger for explicit event recording."""
    try:
        from realize_core.security.audit import get_audit_logger

        return get_audit_logger()
    except Exception as exc:
        logger.debug("Audit logger unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 5. Venture scope + write permissions (STORY-18)
# ---------------------------------------------------------------------------

#: Path and query parameters that name a venture.
VENTURE_PARAMS = ("venture_key", "system_key", "venture")


def get_allowed_ventures(request: Request) -> frozenset[str] | None:
    """Ventures the caller may see, or None for all; resolved once per request.

    MCP tool handlers call REST handlers with a proxy request that has no
    ``state``; the MCP dispatcher applies venture scope itself.
    """
    state = getattr(request, "state", None)
    if state is None:
        return None
    if getattr(state, "_venture_scope_resolved", False):
        return state.allowed_ventures
    from realize_core.security.venture_scope import allowed_ventures

    state.allowed_ventures = allowed_ventures(getattr(state, "user_id", None), getattr(state, "scopes", None))
    state._venture_scope_resolved = True
    return state.allowed_ventures


def venture_allowed(request: Request, venture_key: str | None) -> bool:
    """True if the caller may see ``venture_key`` (or no venture is named)."""
    allowed = get_allowed_ventures(request)
    return allowed is None or not venture_key or venture_key in allowed


def visible_to(request: Request, venture_key: str | None) -> bool:
    """True if the caller may see data belonging to ``venture_key``.

    Stricter than :func:`venture_allowed`: for a caller limited to some
    ventures, data with no venture (system-wide) is not visible.
    """
    allowed = get_allowed_ventures(request)
    return allowed is None or (bool(venture_key) and venture_key in allowed)


def visible_systems(request: Request) -> dict:
    """The configured ventures (systems) this caller may see."""
    systems: dict = getattr(request.app.state, "systems", None) or {}
    allowed = get_allowed_ventures(request)
    if allowed is None:
        return systems
    return {key: conf for key, conf in systems.items() if key in allowed}


def _deny(request: Request, detail: str, permission: str = "") -> HTTPException:
    """Audit an access denial and build the 403."""
    try:
        from realize_core.security.audit import get_audit_logger

        get_audit_logger().log_access_denied(
            user_id=getattr(request.state, "user_id", "") or "",
            action=f"{request.method} {request.url.path}",
            permission=permission or "venture_scope",
            role=getattr(request.state, "role", "") or "",
            channel="api",
            ip_address=request.client.host if request.client else "",
        )
    except Exception as exc:
        logger.debug("Audit log for access denial failed: %s", exc)
    return HTTPException(status_code=403, detail=detail)


async def _body_ventures(request: Request, method: str) -> list[str]:
    """Venture keys named at the top level of a JSON write body.

    FastAPI caches the body, so the route reads it again without cost.
    """
    from realize_core.security.venture_scope import MUTATING_METHODS

    if method not in MUTATING_METHODS or "json" not in request.headers.get("content-type", ""):
        return []
    try:
        data = await request.json()
    except ValueError:
        return []  # malformed: the route's own validation answers
    if not isinstance(data, dict):
        return []
    return [str(data[k]) for k in VENTURE_PARAMS if isinstance(data.get(k), str) and data.get(k)]


async def enforce_access(request: Request) -> None:
    """App-wide guard: venture scope on every request, RBAC on every write.

    Applies only to authenticated callers; with auth off (dev mode) nothing
    changes. See :mod:`realize_core.security.venture_scope` for the rules.
    """
    # Only the REST API; MCP checks scope per tool in its dispatcher.
    if not getattr(request.state, "user_id", None) or not request.url.path.startswith("/api/"):
        return
    from realize_core.security.venture_scope import (
        has_permission,
        is_global_write,
        is_id_only_write,
        needs_named_venture,
        required_permission,
    )

    allowed = get_allowed_ventures(request)
    method, path = request.method.upper(), request.url.path
    if allowed is not None:
        named = [v for n in VENTURE_PARAMS for v in (request.path_params.get(n), request.query_params.get(n))]
        named += await _body_ventures(request, method)
        for value in filter(None, named):
            if value not in allowed:
                raise _deny(request, f"You don't have access to venture '{value}'")
        if needs_named_venture(path) and not any(named):
            raise _deny(request, "Name one of your ventures for this request")
        if is_id_only_write(method, path):
            raise _deny(request, "This change can't be limited to your ventures; ask an owner or admin")

    permission = required_permission(method, path)
    if permission is None:
        return
    role = getattr(request.state, "role", None)
    if not has_permission(role, permission):
        raise _deny(request, f"Your role ({role}) can't do this (needs {permission})", permission)
    if allowed is not None and is_global_write(method, path):
        raise _deny(request, "This change affects every venture; ask an owner or admin", permission)
