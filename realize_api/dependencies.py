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
