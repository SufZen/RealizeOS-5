"""
Who may chat as, and see, which user's conversation.

One rule for every path to conversations (REST chat routes and the MCP chat
tools): an authenticated caller acts for themselves; only ``owner`` and
``admin`` principals — operators, and API-key integrations acting for their
end users — may name another user. With no authenticated principal (auth off,
dev mode) the requested user is used as given.
"""

from __future__ import annotations

#: Roles that may chat for, and read or clear, other users' conversations.
ACT_FOR_OTHERS_ROLES = frozenset({"owner", "admin"})


def chat_user_for(principal: str | None, role: str | None, requested: str) -> str:
    """The user a chat request acts for.

    Args:
        principal: Authenticated caller's user id, or None when auth is off.
        role: Caller's role.
        requested: User id named in the request.
    """
    if principal is None or (role or "") in ACT_FOR_OTHERS_ROLES:
        return requested
    return principal


def may_access_conversation(principal: str | None, role: str | None, user_id: str) -> bool:
    """True if the caller may read or clear ``user_id``'s conversation."""
    return principal is None or (role or "") in ACT_FOR_OTHERS_ROLES or principal == user_id
