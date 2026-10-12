"""
In-process log of agent routing decisions (Codex audit F19).

Routing Analytics used to show only what the routing *test* endpoint
recorded; real chat routing wrote nothing. ``process_message`` now records
each decision here: which venture, which agent, how it was chosen, when.
Real chat text is not kept (only the routing test stores its preview).
The log is per process and bounded; it resets on restart.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

MAX_DECISIONS = 1000

#: How an agent was chosen.
METHODS = ("requested", "keyword", "default", "fallback", "test")

#: Newest last. The routing route reads (and its tests write) this same list.
DECISIONS: list[dict] = []


def record_decision(
    system_key: str,
    agent_key: str,
    method: str,
    *,
    message_preview: str = "",
    scores: dict | None = None,
) -> dict:
    """Append one routing decision and return it."""
    entry = {
        "id": uuid.uuid4().hex[:12],
        "timestamp": datetime.now(UTC).isoformat(),
        "system_key": system_key,
        "selected_agent": agent_key,
        "method": method,
        "message_preview": message_preview,
        "scores": scores or {},
    }
    DECISIONS.append(entry)
    if len(DECISIONS) > MAX_DECISIONS:
        del DECISIONS[: len(DECISIONS) - MAX_DECISIONS]
    return entry
