"""
Agent token API (STORY-37) — issue, list and revoke venture-scoped tokens for
outside agents.

Endpoints (owner/admin, not limited to some ventures):

- ``GET /api/agent-tokens`` — every token; secrets are never stored or shown.
- ``POST /api/agent-tokens`` — issue one; the token is in the response once.
- ``DELETE /api/agent-tokens/{token_id}`` — revoke now; the agent's pending
  held writes are withdrawn.

See :mod:`realize_core.security.agent_tokens` for what a token can do.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from realize_api.dependencies import get_allowed_ventures

router = APIRouter()
logger = logging.getLogger(__name__)

#: Who may manage agent tokens.
MANAGER_ROLES = frozenset({"owner", "admin"})
#: Role order: a token can't carry a role above the caller's own.
_ROLE_RANK = {"viewer": 0, "user": 1, "operator": 2, "admin": 3, "owner": 4}


class CreateAgentTokenBody(BaseModel):
    """Request body for ``POST /api/agent-tokens``."""

    name: str = Field(min_length=1, max_length=64, description="Label for people, e.g. claude-desktop-acme.")
    user: str = Field(min_length=1, max_length=254, description="users.yaml user the agent acts for.")
    ventures: list[str] = Field(min_length=1, max_length=50, description="Ventures the agent may see.")
    expires_in_days: int | None = Field(default=None, ge=1, le=3650, description="Optional lifetime in days.")


def _caller(request: Request) -> tuple[str | None, str | None]:
    state = request.state
    return getattr(state, "user_id", None), getattr(state, "role", None)


def _require_manager(request: Request) -> str:
    """The caller's id, or 403 unless an owner/admin who sees every venture.

    With auth off (dev mode) there is no caller and the route is open, like
    every other route.
    """
    from realize_core.security.agent_tokens import is_agent_principal

    user_id, role = _caller(request)
    if user_id is None:
        return "dev-mode"
    if is_agent_principal(user_id) or role not in MANAGER_ROLES or get_allowed_ventures(request) is not None:
        raise HTTPException(status_code=403, detail="Only an owner or admin can manage agent tokens")
    return user_id


def _enabled(request: Request) -> bool:
    from realize_core.config import get_features

    config = getattr(request.app.state, "config", None)
    return bool(get_features(config if isinstance(config, dict) else {}).get("agent_tokens"))


@router.get("/agent-tokens")
async def list_agent_tokens(request: Request) -> dict:
    """List agent tokens (no secrets)."""
    from realize_core.security.agent_tokens import list_tokens

    _require_manager(request)
    return {"tokens": [t.to_dict() for t in list_tokens()], "enabled": _enabled(request)}


@router.post("/agent-tokens", status_code=201)
async def create_agent_token(body: CreateAgentTokenBody, request: Request) -> dict:
    """Issue a venture-scoped agent token. The token is shown in this response only."""
    from realize_core.security.agent_tokens import AgentTokenError, create_token
    from realize_core.security.users import get_user

    creator = _require_manager(request)
    if not _enabled(request):
        raise HTTPException(status_code=409, detail="Agent tokens are turned off (features.agent_tokens)")
    _user_id, role = _caller(request)
    bound = get_user(body.user)
    if role and bound is not None and _ROLE_RANK.get(bound.role, 0) > _ROLE_RANK.get(role, 0):
        raise HTTPException(status_code=403, detail="An agent token can't act for a user with a higher role than yours")
    systems = getattr(request.app.state, "systems", None)
    try:
        token, secret = create_token(
            name=body.name,
            user_email=body.user,
            ventures=body.ventures,
            expires_in_days=body.expires_in_days,
            created_by=creator,
            known_ventures=list(systems) if isinstance(systems, dict) else None,
            channel="api",
        )
    except AgentTokenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "token": secret,
        "agent_token": token.to_dict(),
        "message": "Copy the token now: it is shown only once. Send it as 'Authorization: Bearer <token>'.",
    }


@router.delete("/agent-tokens/{token_id}")
async def revoke_agent_token(token_id: str, request: Request) -> dict:
    """Revoke an agent token now and withdraw its pending held writes."""
    from realize_core.security.agent_tokens import revoke_token

    revoker = _require_manager(request)
    revoked = revoke_token(token_id, revoked_by=revoker, channel="api")
    if revoked is None:
        raise HTTPException(status_code=404, detail="Agent token not found")
    token, withdrawn = revoked
    return {"agent_token": token.to_dict(), "withdrawn_approvals": withdrawn}
