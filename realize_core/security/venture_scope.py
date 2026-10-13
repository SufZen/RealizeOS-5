"""
Venture scope and write permissions for API callers (STORY-18).

Two questions, answered in one place for every route:

1. **Which ventures may this caller see?** A user in ``users.yaml`` may list
   ``ventures: [...]`` (empty or missing means all). A JWT may narrow further
   with ``venture:<key>`` scopes. API-key callers and callers with no
   authenticated principal (auth off) see every venture. An outside agent
   (agent token, STORY-37) always carries venture scopes; without any it sees
   nothing.
2. **May this caller make this write?** Mutating requests need an RBAC
   permission picked from the route (see :func:`required_permission`). Writes
   that affect every venture (settings, integrations, agent definitions, ...)
   also need a caller who is not limited to specific ventures.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: JWT scope prefix that limits a token to one venture.
VENTURE_SCOPE_PREFIX = "venture:"

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Signing in and out, refreshing and listing one's own sessions.
_AUTH_PREFIX = "/api/auth/"
#: Chatting, and clearing one's own conversation.
_CHAT_PATHS = ("/api/chat", "/api/chat/stream")
_CONVERSATIONS_PREFIX = "/api/conversations/"
#: Decisions on held actions and proposals.
_DECISION_PREFIXES = ("/api/approvals/", "/api/dreams/", "/api/evolution/suggestions/")
_DECISION_SUFFIXES = ("/approve", "/reject", "/dismiss")
#: Writes that change configuration shared by every venture.
_GLOBAL_PREFIXES = (
    "/api/settings",
    "/api/security",
    "/api/setup",
    "/api/integrations",
    "/api/storage",
    "/api/devmode",
    "/api/extensions",
    "/api/trust",
    "/api/systems",
    "/api/routing",
    "/api/agents",
    "/api/shared",
    "/api/fabric/reindex",
    "/api/dreams",
    "/api/evolution",
    "/api/agent-tokens",
)
_VENTURES_PATH = "/api/ventures"
#: System-wide areas a venture-limited caller may not use at all (reads included):
#: configuration and data shared by every venture, and actions that can't be
#: tied to one venture.
_SYSTEM_AREA_PREFIXES = (
    "/api/settings",
    "/api/security",
    "/api/setup",
    "/api/integrations",
    "/api/storage",
    "/api/devmode",
    "/api/extensions",
    "/api/shared",
    "/api/trust",
    "/api/tools",
    "/api/evolution",
    # Pipeline definitions and runs aren't tied to one venture yet (STORY-18 review F4).
    "/api/pipelines",
    # Inbound webhook payloads have no trusted owner; LLM usage isn't split by venture.
    "/api/webhooks/events",
    "/api/llm",
    # LLM usage again, under the memory routes (search is scoped in its handler).
    "/api/memory/stats",
    # Issuing agent tokens spans ventures (STORY-37).
    "/api/agent-tokens",
)
#: Areas that span every venture unless one is named; a venture-limited caller must name one.
_NEEDS_VENTURE_PREFIXES = ("/api/fabric",)
#: Edits addressed by an item id alone (the item's venture can't be checked here).
_ID_ONLY_WRITE_PREFIXES = ("/api/fabric/entities/", "/api/workflows/")


def allowed_ventures(user_id: str | None, scopes: list[str] | None = None) -> frozenset[str] | None:
    """Ventures the caller may see, or None for all of them.

    Dashboard users (cookie sessions) are re-checked against ``users.yaml``
    by the auth middleware, so a deleted user never reaches this point. A
    principal that isn't a configured user is a service identity — the API
    key, or a JWT minted with the API key — and is unrestricted unless its
    token carries ``venture:<key>`` scopes.

    Args:
        user_id: Authenticated caller (email for dashboard users), or None
            when auth is off.
        scopes: JWT scopes; ``venture:<key>`` entries narrow the set.
    """
    if not user_id:
        return None
    allowed: frozenset[str] | None = None

    from realize_core.security.users import get_user

    user = get_user(user_id)
    if user is not None and user.ventures:
        allowed = frozenset(user.ventures)

    token_ventures = {s[len(VENTURE_SCOPE_PREFIX) :] for s in scopes or [] if s.startswith(VENTURE_SCOPE_PREFIX)}
    if token_ventures:
        allowed = frozenset(token_ventures) if allowed is None else allowed & token_ventures
    else:
        from realize_core.security.agent_access import is_agent

        if is_agent(user_id, scopes):
            # An outside agent is never unrestricted: no venture scope means no venture.
            return frozenset()
    return allowed


def is_global_write(method: str, path: str) -> bool:
    """True for a write that changes configuration shared by every venture."""
    if method not in MUTATING_METHODS:
        return False
    if path == _VENTURES_PATH:  # creating a venture
        return True
    return any(path == p or path.startswith(p + "/") for p in _GLOBAL_PREFIXES)


def required_permission(method: str, path: str) -> str | None:
    """The RBAC permission a request needs, or None when no check applies.

    Reads need nothing here (venture scope still applies). Unknown writes need
    ``system:write`` so new routes are closed to read-only roles by default.
    """
    if method not in MUTATING_METHODS or path.startswith(_AUTH_PREFIX):
        return None
    if path in _CHAT_PATHS or path.startswith(_CONVERSATIONS_PREFIX):
        return "agents:execute"
    if path.startswith(_DECISION_PREFIXES) and path.endswith(_DECISION_SUFFIXES):
        return "pipeline:approve"
    if method == "DELETE" and path.startswith(_VENTURES_PATH + "/") and path.count("/") == 3:
        return "system:delete"  # DELETE /api/ventures/{key}
    if is_global_write(method, path):
        return "system:manage"
    return "system:write"


def is_system_area(path: str) -> bool:
    """True for system-wide areas closed to venture-limited callers."""
    return any(path == p or path.startswith(p + "/") for p in _SYSTEM_AREA_PREFIXES)


def needs_named_venture(path: str) -> bool:
    """True for areas a venture-limited caller may use only by naming a venture."""
    return path.startswith(_NEEDS_VENTURE_PREFIXES)


def is_id_only_write(method: str, path: str) -> bool:
    """True for an edit or delete addressed by item id alone (refused for venture-limited callers)."""
    if method not in ("PUT", "PATCH", "DELETE"):
        return False
    return any(path.startswith(p) and len(path) > len(p) for p in _ID_ONLY_WRITE_PREFIXES)


def has_permission(role: str | None, permission: str) -> bool:
    """RBAC check for ``role`` (unknown roles have no permissions)."""
    from realize_core.security.rbac import get_rbac_manager

    return get_rbac_manager().check_access(role or "", permission).allowed


def role_permissions(role: str | None) -> list[str]:
    """Every permission ``role`` has (inherited included), sorted; empty for an unknown role.

    The dashboard uses this to hide controls a role can't use. It is a UX
    hint only: :func:`has_permission` still decides each request.
    """
    from realize_core.security.rbac import get_rbac_manager

    manager = get_rbac_manager()
    if not role or manager.get_role(role) is None:
        return []
    return sorted(manager.resolve_permissions(role))
