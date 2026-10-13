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


def header_user_id(headers: Any) -> str:
    """The caller-supplied ``X-User-ID`` (used only when no principal was authenticated).

    It can never claim an outside agent's identity: that comes only from a
    verified agent token (STORY-37).
    """
    from realize_core.security.agent_access import is_agent

    value = (headers or {}).get("X-User-ID", "anonymous") or "anonymous"
    return "anonymous" if is_agent(value) else value


async def get_current_user(request: Request) -> CurrentUser:
    """
    Extract the current user from request state.

    Falls back to "anonymous" / "owner" when auth is off (dev mode).
    """
    user_id = getattr(request.state, "user_id", None) or header_user_id(request.headers)
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


#: Stands in for a venture value that isn't plain text (never an allowed key).
_INVALID_VENTURE = "<invalid venture value>"


def _venture_values(obj: Any, depth: int = 0) -> list[str]:
    """Every venture key named anywhere in a JSON value (nested objects and lists too)."""
    if depth > 16:
        return [_INVALID_VENTURE]  # too deep to check: refuse rather than guess
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in VENTURE_PARAMS and value not in (None, ""):
                found.append(value if isinstance(value, str) else _INVALID_VENTURE)
            found += _venture_values(value, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            found += _venture_values(item, depth + 1)
    return found


async def _body_ventures(request: Request, method: str) -> list[str]:
    """Venture keys named in a write body, parsed whatever its content type.

    FastAPI parses a body as JSON with no content type or any ``application/*json``
    type (case-insensitively), so the check parses any body that is JSON rather
    than trusting the header. The body is cached, so the route reads it again.
    """
    import json

    from realize_core.security.venture_scope import MUTATING_METHODS

    if method not in MUTATING_METHODS:
        return []
    raw = await request.body()
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return []  # not JSON: FastAPI won't read venture fields from it either
    return _venture_values(data)


async def _scope_param(request: Request, method: str) -> str | None:
    """The `venture` value the FABRIC handlers actually filter by (query, or top-level JSON body)."""
    import json

    from realize_core.security.venture_scope import MUTATING_METHODS

    value = request.query_params.get("venture")
    if value:
        return value
    if method in MUTATING_METHODS:
        raw = await request.body()
        try:
            data = json.loads(raw) if raw.strip() else None
        except (ValueError, UnicodeDecodeError):
            data = None
        if isinstance(data, dict) and isinstance(data.get("venture"), str):
            return data["venture"] or None
    return None


async def enforce_access(request: Request) -> None:
    """App-wide guard: venture scope on every request, RBAC on every write.

    Applies only to authenticated callers; with auth off (dev mode) nothing
    changes. See :mod:`realize_core.security.venture_scope` for the rules.
    """
    # Only the REST API; MCP checks scope per tool in its dispatcher.
    if not getattr(request.state, "user_id", None) or not request.url.path.startswith("/api/"):
        return
    from realize_core.security.agent_access import endpoint_name, is_agent_subject, rest_refusal
    from realize_core.security.users import is_pilot_user
    from realize_core.security.venture_scope import (
        has_permission,
        is_global_write,
        is_id_only_write,
        is_system_area,
        needs_named_venture,
        required_permission,
    )

    if is_pilot_user(request.state.user_id):
        # Pilot accounts (STORY-46) only use the pilot tools from their own agent.
        raise _deny(request, "Pilot accounts can only use the tender register from their own agent")

    allowed = get_allowed_ventures(request)
    method, path = request.method.upper(), request.url.path
    if is_agent_subject(request.state):
        # Outside agents: the same rules as the MCP dispatcher (agent_access),
        # matched on the endpoint the router chose, never on the raw URL.
        refusal = rest_refusal(method, endpoint_name(request.scope.get("endpoint")))
        if refusal:
            raise _deny(request, refusal, "agent_access")
    if allowed is not None:
        named = [request.path_params.get(n) for n in VENTURE_PARAMS]
        named += [v for n in VENTURE_PARAMS for v in request.query_params.getlist(n)]
        named += await _body_ventures(request, method)
        for value in filter(None, named):
            if value not in allowed:
                raise _deny(request, f"You don't have access to venture '{value}'")
        if is_system_area(path):
            raise _deny(request, "This area is shared by every venture; ask an owner or admin")
        if needs_named_venture(path) and not await _scope_param(request, method):
            # FABRIC handlers filter by `venture` only; an alias (system_key,
            # venture_key) would pass a generic check and query every venture.
            raise _deny(request, "Name one of your ventures with the `venture` parameter")
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
