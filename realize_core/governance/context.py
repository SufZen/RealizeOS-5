"""
Who a tool call is for — context the governance gate records with approvals.

The tool registry and gate are process-wide singletons, but an approval must
say which venture, agent and user an action was requested for, so the
outcome can be reported back to that conversation once it is approved.
Callers that run tools on behalf of someone (the agent tool loop, skill tool
steps) wrap the call in :func:`tool_call_context`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolCallContext:
    """Origin of a tool call."""

    system_key: str = ""
    agent_key: str = ""
    user_id: str = ""
    channel: str = ""

    @property
    def session_ref(self) -> str:
        """Conversation key ``<venture>|<user>`` (empty when unknown)."""
        return f"{self.system_key}|{self.user_id}" if self.system_key and self.user_id else ""


_EMPTY = ToolCallContext()
_current: ContextVar[ToolCallContext | None] = ContextVar("realize_tool_call_context", default=None)


def current_tool_context() -> ToolCallContext:
    """The context of the tool call being made now (empty defaults outside one)."""
    return _current.get() or _EMPTY


@contextmanager
def tool_call_context(
    *, system_key: str = "", agent_key: str = "", user_id: str = "", channel: str = ""
) -> Iterator[ToolCallContext]:
    """Set the tool-call origin for the duration of the ``with`` block."""
    ctx = ToolCallContext(system_key=system_key, agent_key=agent_key, user_id=user_id, channel=channel)
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


def parse_session_ref(session_ref: str | None) -> tuple[str, str] | None:
    """Split ``<venture>|<user>`` into its parts, or None."""
    if not session_ref or "|" not in session_ref:
        return None
    system_key, user_id = session_ref.split("|", 1)
    return (system_key, user_id) if system_key and user_id else None
