"""
Authentication API routes.

Two coexisting credential flows:

1. **Cookie sessions (v5.2.0+)** — for the browser dashboard.
   - ``POST   /api/auth/login``          create session, set HttpOnly cookie
   - ``POST   /api/auth/logout``         revoke session, clear cookie
   - ``GET    /api/auth/session``        introspect current session
   - ``GET    /api/auth/sessions``       list active sessions for current user
   - ``DELETE /api/auth/sessions/{id}``  revoke a specific session

2. **JWT bearer tokens** — for programmatic / CLI callers.
   - ``POST /api/auth/token``    issue access + refresh pair
   - ``POST /api/auth/refresh``  refresh an expired access token
   - ``GET  /api/auth/me``       current user from any credential type
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from realize_api.dependencies import CurrentUser, get_current_user
from realize_core.security import session_store, users

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------


def _cookie_secure() -> bool:
    """Set Secure cookies only when the deployment is HTTPS-aware.

    Heuristic: production env implies a real domain on HTTPS. Plain HTTP
    deployments (Hetzner-IP-style) keep Secure off so the cookie actually
    works; the SameSite=Strict + HttpOnly settings still protect them.
    """
    return os.environ.get("REALIZE_ENV", "").lower() == "production" and \
        os.environ.get("REALIZE_FORCE_INSECURE_COOKIES", "").lower() not in ("1", "true", "yes")


def _set_session_cookies(response: Response, record: session_store.SessionRecord) -> None:
    secure = _cookie_secure()
    max_age = int(session_store.REMEMBER_ME_TTL.total_seconds()) if record.remember_me \
        else int(session_store.DEFAULT_TTL.total_seconds())

    response.set_cookie(
        key=session_store.SESSION_COOKIE_NAME,
        value=record.session_id,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        key=session_store.CSRF_COOKIE_NAME,
        value=record.csrf_token,
        max_age=max_age,
        httponly=False,  # readable by the SPA so it can echo in X-Realize-CSRF
        secure=secure,
        samesite="strict",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(session_store.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(session_store.CSRF_COOKIE_NAME, path="/")


# ---------------------------------------------------------------------------
# Cookie session endpoints (v5.2.0+)
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    """Authenticate via email + password and start a cookie session."""
    user = users.verify_password(body.email, body.password)
    if user is None:
        # Audit the failed attempt — useful for rate-limit / brute-force triage.
        try:
            from realize_core.security.audit import get_audit_logger
            get_audit_logger().log(
                user_id=(body.email or "unknown").strip().lower(),
                action="auth_login_failed",
                outcome="error",
                channel="api",
                ip_address=request.client.host if request.client else "",
                severity="warning",
            )
        except Exception as exc:
            logger.debug("Audit log for failed login skipped: %s", exc)

        raise HTTPException(status_code=401, detail="invalid_credentials")

    record = session_store.create_session(
        user_id=user.email,
        role=user.role,
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", "")[:255],
        remember_me=body.remember_me,
    )
    _set_session_cookies(response, record)

    try:
        from realize_core.security.audit import get_audit_logger
        get_audit_logger().log(
            user_id=user.email,
            action="auth_login",
            outcome="success",
            channel="api",
            ip_address=request.client.host if request.client else "",
            severity="info",
        )
    except Exception as exc:
        logger.debug("Audit log for login skipped: %s", exc)

    return {"user_id": user.email, "role": user.role}


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Revoke the current session and clear cookies."""
    session_id = request.cookies.get(session_store.SESSION_COOKIE_NAME, "")
    revoked = session_store.revoke_session(session_id) if session_id else False
    _clear_session_cookies(response)

    if revoked:
        try:
            from realize_core.security.audit import get_audit_logger
            get_audit_logger().log(
                user_id=getattr(request.state, "user_id", "unknown"),
                action="auth_logout",
                outcome="success",
                channel="api",
                ip_address=request.client.host if request.client else "",
                severity="info",
            )
        except Exception as exc:
            logger.debug("Audit log for logout skipped: %s", exc)

    return {"revoked": revoked}


@router.get("/session")
async def get_session_info(request: Request):
    """Return whether the caller has a live cookie session (used by the SPA on load)."""
    session_id = request.cookies.get(session_store.SESSION_COOKIE_NAME, "")
    if not session_id:
        return {"authenticated": False}

    record = session_store.get_session(session_id)
    if record is None:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "user_id": record.user_id,
        "role": record.role,
        "expires_at": record.expires_at,
    }


@router.get("/sessions")
async def list_my_sessions(user: CurrentUser = Depends(get_current_user)):
    """List the current user's active sessions (for a Settings UI)."""
    if user.user_id in ("anonymous", ""):
        raise HTTPException(status_code=401, detail="auth_required")

    sessions = session_store.list_sessions_for_user(user.user_id)
    return {
        "sessions": [
            {
                "session_id": s.session_id[:12] + "…",  # truncated — never expose the full ID
                "created_at": s.created_at,
                "last_seen_at": s.last_seen_at,
                "expires_at": s.expires_at,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
            }
            for s in sessions
        ]
    }


@router.delete("/sessions")
async def revoke_all_my_sessions(
    response: Response,
    user: CurrentUser = Depends(get_current_user),
):
    """Sign out everywhere for the current user."""
    if user.user_id in ("anonymous", ""):
        raise HTTPException(status_code=401, detail="auth_required")

    count = session_store.revoke_all_for_user(user.user_id)
    _clear_session_cookies(response)
    return {"revoked": count}


# ---------------------------------------------------------------------------
# JWT bearer endpoints (kept from 5.1.0 for programmatic callers)
# ---------------------------------------------------------------------------


class TokenRequest(BaseModel):
    user_id: str = "owner"
    role: str = "owner"
    api_key: str = ""


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/token")
async def create_token(body: TokenRequest):
    """Create a JWT access+refresh pair. Requires the configured REALIZE_API_KEY."""
    expected_key = os.environ.get("REALIZE_API_KEY", "")
    if expected_key and body.api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        from realize_core.security.jwt_auth import create_token_pair

        pair = create_token_pair(user_id=body.user_id, role=body.role)

        try:
            from realize_core.security.audit import get_audit_logger
            get_audit_logger().log_token_event(
                user_id=body.user_id,
                action="token_created",
                token_type="access+refresh",
            )
        except Exception as exc:
            logger.debug("Audit log for token creation failed: %s", exc)

        return {
            "access_token": pair.access_token,
            "refresh_token": pair.refresh_token,
            "expires_in": pair.expires_in,
            "token_type": pair.token_type,
        }
    except Exception as exc:
        logger.error("Token creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Token creation failed")


@router.post("/refresh")
async def refresh_token(body: RefreshRequest):
    """Refresh an expired access token using a valid refresh token."""
    try:
        from realize_core.security.jwt_auth import (
            InvalidTokenError,
            TokenExpiredError,
            refresh_access_token,
        )

        new_access = refresh_access_token(body.refresh_token)
        return {"access_token": new_access, "token_type": "Bearer"}
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Refresh token has expired — please log in again")
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        logger.error("Token refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail="Token refresh failed")


@router.get("/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    """Get the current user's identity (works for cookie, API key, or JWT)."""
    if user.user_id in ("anonymous", ""):
        raise HTTPException(status_code=401, detail="auth_required")
    return {
        "user_id": user.user_id,
        "role": user.role,
        "scopes": user.scopes,
    }
