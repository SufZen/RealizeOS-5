"""
"What I used" trail — records what an answer was built from (STORY-17).

A :class:`TrailRecorder` is passed as the ``emit`` callback of
``process_message``. It keeps, in order:

- ``source`` events — the numbered KB hits ([S1]…) and pack rule cards
  ([R1]…) the prompt included. A rule card keeps its provenance: the layer
  and pack that supplied it, its verification level and its dates, so the
  level is shown on every answer whatever the model wrote (Codex audit N03);
- ``tool_call`` / ``tool_result`` / ``approval_requested`` events from the
  agent tool loop;
- ``notice`` events (``code``, ``message``) when an answer had to be given
  without tools, e.g. no tool-capable provider is configured;
- the id of the stored assistant message (``message_saved``, internal).

Every event except ``message_saved`` is forwarded to an optional downstream
listener (the SSE stream). The recorded trail is shown to people and stored
per message; it is never fed back into a model call.
"""

from __future__ import annotations

from typing import Any

from realize_core.agents.tool_loop import Emit, emit_event

#: Loop events that become trail steps.
STEP_TYPES = frozenset({"tool_call", "tool_result", "approval_requested", "notice"})
#: Characters of tool output kept in a stored trail.
STORED_OUTPUT_CHARS = 500
#: Internal event carrying the stored assistant message id.
MESSAGE_SAVED = "message_saved"
#: Fields every trail source has.
SOURCE_FIELDS = ("id", "title", "path")
#: Provenance a pack rule card ([R1]…) adds (spec 010 §3). KB sources have none.
PROVENANCE_FIELDS = ("layer", "pack", "verification", "as_of", "review_by")
#: The verification ladder (ADR 0005): 0 unverified … 4 field-proven.
MIN_LEVEL, MAX_LEVEL = 0, 4


def _level(value: Any) -> int | None:
    """A verification level as an int on the 0-4 ladder, or None when unreadable."""
    if isinstance(value, bool):
        return None
    try:
        level = int(value)
    except (TypeError, ValueError):
        return None
    return max(MIN_LEVEL, min(MAX_LEVEL, level))


def trail_source(event: dict[str, Any]) -> dict[str, Any]:
    """A trail source from a ``source`` event or a stored source.

    Always ``id``, ``title`` and ``path``; a rule card also keeps whichever
    of ``layer``, ``pack``, ``verification``, ``as_of`` and ``review_by`` it
    carries. Absent provenance stays absent rather than becoming null.
    """
    source: dict[str, Any] = {k: str(event.get(k) or "") for k in SOURCE_FIELDS}
    for key in PROVENANCE_FIELDS:
        value = event.get(key)
        if value is None or value == "":
            continue
        if key == "verification":
            level = _level(value)
            if level is not None:
                source[key] = level
        else:
            source[key] = str(value)
    return source


class TrailRecorder:
    """Collects trail events for one answer and forwards progress to a listener."""

    def __init__(self, forward: Emit | None = None) -> None:
        self.sources: list[dict[str, Any]] = []
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
            source = trail_source(event)
            self.sources.append(source)
            # Live listeners get the same shape the stored trail keeps.
            event = {"type": "source", **source}
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
    cells); like approval results, it is not echoed to MCP callers. Sources
    keep their provenance, so an outside agent sees each rule's level too.
    """
    keep = {
        "tool_call": ("type", "name"),
        "tool_result": ("type", "name", "success", "held"),
        "approval_requested": ("type", "name", "request_id"),
        "notice": ("type", "code", "message"),
    }
    steps = []
    for step in trail.get("steps", []):
        fields = keep.get(step.get("type"))
        if fields:
            steps.append({f: step.get(f) for f in fields})
    sources = [trail_source(s) for s in trail.get("sources", [])]
    return {"sources": sources, "steps": steps}
