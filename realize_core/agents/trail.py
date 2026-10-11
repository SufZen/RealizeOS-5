"""
"What I used" trail — records what an answer was built from (STORY-17).

A :class:`TrailRecorder` is passed as the ``emit`` callback of
``process_message``. It keeps, in order:

- ``source`` events — the numbered KB hits ([S1]…) the prompt included;
- ``tool_call`` / ``tool_result`` / ``approval_requested`` events from the
  agent tool loop;
- the id of the stored assistant message (``message_saved``, internal).

Every event except ``message_saved`` is forwarded to an optional downstream
listener (the SSE stream). The recorded trail is shown to people and stored
per message; it is never fed back into a model call.
"""

from __future__ import annotations

from typing import Any

from realize_core.agents.tool_loop import Emit, emit_event

#: Loop events that become trail steps.
STEP_TYPES = frozenset({"tool_call", "tool_result", "approval_requested"})
#: Characters of tool output kept in a stored trail.
STORED_OUTPUT_CHARS = 500
#: Internal event carrying the stored assistant message id.
MESSAGE_SAVED = "message_saved"


class TrailRecorder:
    """Collects trail events for one answer and forwards progress to a listener."""

    def __init__(self, forward: Emit | None = None) -> None:
        self.sources: list[dict[str, str]] = []
        self.steps: list[dict[str, Any]] = []
        self.message_id: int | None = None
        self._forward = forward

    async def __call__(self, event: dict[str, Any]) -> None:
        """Record ``event`` and forward it (except internal bookkeeping)."""
        kind = event.get("type")
        if kind == MESSAGE_SAVED:
            self.message_id = event.get("message_id")
            return
        if kind == "source":
            self.sources.append({k: str(event.get(k) or "") for k in ("id", "title", "path")})
        elif kind in STEP_TYPES:
            self.steps.append(dict(event))
        await emit_event(self._forward, event)

    @property
    def is_empty(self) -> bool:
        """True when the answer used no sources and no tools."""
        return not self.sources and not self.steps

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        """The trail as returned to the caller of this answer."""
        return {"sources": [dict(s) for s in self.sources], "steps": [dict(s) for s in self.steps]}

    def stored(self) -> dict[str, list[dict[str, Any]]]:
        """The trail as persisted: tool output trimmed to a short preview."""
        trail = self.to_dict()
        for step in trail["steps"]:
            output = step.get("output")
            if isinstance(output, str) and len(output) > STORED_OUTPUT_CHARS:
                step["output"] = output[:STORED_OUTPUT_CHARS] + " ..."
        return trail


def trail_summary(trail: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """A trail without tool inputs, outputs or errors — for MCP clients.

    Tool output can carry third-party text (email bodies, web pages, sheet
    cells); like approval results, it is not echoed to MCP callers.
    """
    keep = {
        "tool_call": ("type", "name"),
        "tool_result": ("type", "name", "success", "held"),
        "approval_requested": ("type", "name", "request_id"),
    }
    steps = []
    for step in trail.get("steps", []):
        fields = keep.get(step.get("type"))
        if fields:
            steps.append({f: step.get(f) for f in fields})
    sources = [{k: s.get(k) for k in ("id", "title", "path")} for s in trail.get("sources", [])]
    return {"sources": sources, "steps": steps}
