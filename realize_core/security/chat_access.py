"""
Who may chat as, and see, which user's conversation.

One rule for every path to conversations (REST chat routes and the MCP chat
tools): an authenticated caller acts for themselves; only ``owner`` and
``admin`` principals — operators, and API-key integrations acting for their
end users — may name another user. An outside agent (agent token or stdio
session, STORY-37) always acts for itself, whatever its user's role. With no
authenticated principal (auth off, dev mode) the requested user is used as
given.
"""

from __future__ import annotations

from collections.abc import Iterable

#: Roles that may chat for, and read or clear, other users' conversations.
ACT_FOR_OTHERS_ROLES = frozenset({"owner", "admin"})


def _acts_for_others(principal: str, role: str | None, scopes: Iterable[str] | None) -> bool:
    from realize_core.security.agent_access import is_agent

    return (role or "") in ACT_FOR_OTHERS_ROLES and not is_agent(principal, scopes)


def chat_user_for(principal: str | None, role: str | None, requested: str, scopes: Iterable[str] | None = None) -> str:
    """The user a chat request acts for.

    Args:
        principal: Authenticated caller's user id, or None when auth is off.
        role: Caller's role.
        requested: User id named in the request.
        scopes: Caller's scopes (an outside agent's marker lives there).
    """
    if principal is None or _acts_for_others(principal, role, scopes):
        return requested
    return principal


def may_access_conversation(
    principal: str | None, role: str | None, user_id: str, scopes: Iterable[str] | None = None
) -> bool:
    """True if the caller may read or clear ``user_id``'s conversation."""
    return principal is None or _acts_for_others(principal, role, scopes) or principal == user_id
