"""
Authentication API routes — token creation and refresh.

Endpoints:
- POST /api/auth/token — create a JWT token pair (access + refresh)
- POST /api/auth/refresh — refresh an expired access token
- GET  /api/auth/me — get current user info from token
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from realize_api.dependencies import CurrentUser, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


class TokenRequest(BaseModel):
    """Request body for token creation."""

    user_id: str = "owner"
    role: str = "owner"
    api_key: str = ""  # Must match REALIZE_API_KEY to get a token


class RefreshRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


@router.post("/token")
async def create_token(body: TokenRequest):
    """
    Create a JWT token pair.

    Requires either:
    - A valid API key in the request body
    - A valid X-API-Key header (handled by APIKeyMiddleware)
    """
    expected_key = os.environ.get("REALIZE_API_KEY", "")

    # If API key auth is enabled, verify it
    if expected_key and body.api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        from realize_core.security.jwt_auth import create_token_pair

        pair = create_token_pair(
            user_id=body.user_id,
            role=body.role,
        )

        # Log the token creation
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

        return {
            "access_token": new_access,
            "token_type": "Bearer",
        }
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Refresh token has expired — please log in again")
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        logger.error("Token refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail="Token refresh failed")


@router.get("/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    """Get the current user's identity from their JWT or session."""
    return {
        "user_id": user.user_id,
        "role": user.role,
        "scopes": user.scopes,
    }
