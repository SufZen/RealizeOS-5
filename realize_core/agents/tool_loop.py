"""
Agent tool loop — lets an agent use tools while it answers.

One loop serves chat, skills and missions: the model is offered the tools the
agent may use; every ``tool_use`` it emits is executed **only** through
:class:`~realize_core.tools.tool_registry.ToolRegistry`, so governance (the
trust ladder and approval gate) applies to every call; results go back to the
model until it produces a final answer.

Progress is reported through an optional ``emit`` callback as plain dicts so
callers can stream a live "what I used" trail (STORY-17):

- ``{"type": "tool_call", "id", "name", "input"}``
- ``{"type": "tool_result", "id", "name", "success", "output", "error"}``
- ``{"type": "approval_requested", "id", "name", "request_id"}``
- ``{"type": "text", "text"}`` — final answer

The loop is wire-neutral: it runs on the first tool-capable provider in the
fallback chain and uses that provider's hooks to serialise tool schemas, the
assistant turn and the tool results.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from realize_core.llm.base_provider import STOP_ERROR, STOP_PAUSE, STOP_REFUSAL, STOP_TOOL_USE, ToolCall
from realize_core.tools.base_tool import convert_tool_schemas

logger = logging.getLogger(__name__)

Emit = Callable[[dict[str, Any]], Awaitable[None] | None]

#: Default cap on model round-trips per answer.
DEFAULT_MAX_ITERATIONS = 8
#: Characters of a tool result echoed into trail events (the model gets it all).
EVENT_PREVIEW_CHARS = 2_000


def _as_blocks(content: Any) -> list[Any]:
    return [{"type": "text", "text": content}] if isinstance(content, str) else list(content)


def _append_user_text(convo: list[dict[str, Any]], provider, text: str) -> None:
    """Add text to the trailing user turn (after its tool results), or a new user turn.

    The trailing user turn has not been sent yet, so this keeps the history
    append-only. The note is built with the provider's ``user_text_message``.
    """
    note = provider.user_text_message(text)
    last = convo[-1] if convo else None
    if last and last.get("role") == "user":
        old, new = last["content"], note["content"]
        if isinstance(old, str) and isinstance(new, str):
            merged: Any = f"{old}\n\n{new}"
        else:
            merged = [*_as_blocks(old), *_as_blocks(new)]
        convo[-1] = {**last, "content": merged}
    else:
        convo.append(note)


_WRAP_UP_NOTE = (
    "You have reached the tool-use limit for this answer. Do not call any more tools; "
    "answer now with what you have, and say what is still missing."
)
_HELD_NOTE = (
    "This action was NOT performed. It is waiting for an operator to approve it "
    "(approval request {request_id}). Tell the user it is pending approval; do not retry it."
)


@dataclass
class ToolCallRecord:
    """One tool call made during the loop."""

    id: str
    name: str
    input: dict[str, Any]
    success: bool = False
    output: str = ""
    error: str | None = None
    request_id: str | None = None  # set when the gate held the action
    duration_ms: float = 0.0

    @property
    def held(self) -> bool:
        """True when the action awaits operator approval instead of having run."""
        return self.request_id is not None


@dataclass
class LoopResult:
    """Outcome of :func:`run_tool_loop`."""

    text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    iterations: int = 0
    stop_reason: str = ""
    cost_usd: float = 0.0

    @property
    def pending_approvals(self) -> list[str]:
        return [c.request_id for c in self.tool_calls if c.request_id]


async def emit_event(emit: Emit | None, event: dict[str, Any]) -> None:
    """Send an event to the caller; a broken listener never breaks the loop."""
    if emit is None:
        return
    try:
        result = emit(event)
        if inspect.isawaitable(result):
            await result
    except Exception:
        logger.warning("Tool loop event listener failed for %s", event.get("type"), exc_info=True)


async def _run_one(registry, call: ToolCall, emit: Emit | None, allowed: frozenset[str]) -> ToolCallRecord:
    """Execute one model tool call through the registry (and its gate).

    Only tools that were offered to the model (``allowed``) are executed. The
    model may name any action — e.g. after a prompt injection — and the offered
    set is what encodes persona restrictions and the read-only policy when no
    gate is installed.
    """
    params = dict(call.arguments or {})
    record = ToolCallRecord(id=call.id, name=call.name, input=params)
    await emit_event(emit, {"type": "tool_call", "id": call.id, "name": call.name, "input": params})

    if call.name not in allowed:
        logger.warning("Tool loop: model called '%s', which was not offered; refused", call.name)
        record.error = f"Tool '{call.name}' is not available to this agent."
        await emit_event(
            emit,
            {
                "type": "tool_result",
                "id": call.id,
                "name": call.name,
                "success": False,
                "held": False,
                "output": "",
                "error": record.error,
                "duration_ms": 0.0,
            },
        )
        return record

    started = time.perf_counter()
    result = await registry.execute(call.name, params)
    record.duration_ms = (time.perf_counter() - started) * 1000

    record.request_id = result.metadata.get("request_id") if result.metadata.get("requires_human") else None
    record.success = result.success and record.request_id is None
    record.output = result.output or ""
    record.error = result.error

    if record.held:
        await emit_event(
            emit,
            {"type": "approval_requested", "id": call.id, "name": call.name, "request_id": record.request_id},
        )
    await emit_event(
        emit,
        {
            "type": "tool_result",
            "id": call.id,
            "name": call.name,
            "success": record.success,
            "held": record.held,
            "output": record.output[:EVENT_PREVIEW_CHARS],
            "error": record.error,
            "duration_ms": round(record.duration_ms, 1),
        },
    )
    return record


def _tool_result(record: ToolCallRecord) -> tuple[str, bool]:
    """The ``(output, is_error)`` pair sent back to the model for one call."""
    if record.held:
        return _HELD_NOTE.format(request_id=record.request_id), False
    if not record.success:
        return record.error or record.output or "The tool failed without an error message.", True
    return record.output or "(no output)", False


def tool_capable_provider():
    """Return the first available tool-capable provider in the fallback chain, or None."""
    from realize_core.llm.base_provider import Capability
    from realize_core.llm.registry import get_registry

    providers = get_registry().providers_with_capability(Capability.TOOLS)
    return providers[0] if providers else None


async def run_tool_loop(
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    registry=None,
    provider=None,
    model: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    max_tokens: int = 4096,
    emit: Emit | None = None,
) -> LoopResult:
    """Run the model with tools until it answers.

    Args:
        system_prompt: Agent system prompt.
        messages: Conversation so far (plain role/content messages); not mutated.
        tools: Tool schemas the agent may use (Claude format; converted to the
            provider's ``tools_format`` once, before the loop).
        registry: Tool registry to execute through (default: global registry).
        provider: LLM provider with ``complete_with_tools`` (default: the first
            tool-capable provider in the fallback chain).
        model: Model override; provider default when None.
        max_iterations: Max model round-trips before forcing a final answer.
        max_tokens: Per-response token cap.
        emit: Optional callback receiving progress events (sync or async).

    Returns:
        LoopResult with the final text and every tool call made.

    Raises:
        RuntimeError: No tool-capable provider is available.
    """
    from realize_core.llm.router import _check_cost_limit, _check_rate_limit, _record_cost
    from realize_core.tools.tool_registry import get_tool_registry

    registry = registry or get_tool_registry()
    provider = provider or tool_capable_provider()
    if provider is None:
        raise RuntimeError("No tool-capable LLM provider is available")

    convo: list[dict[str, Any]] = list(messages)
    allowed = frozenset(t["name"] for t in tools)
    wire_tools = convert_tool_schemas(tools, getattr(provider, "tools_format", "openai"))
    result = LoopResult(text="")
    prompt = system_prompt

    for iteration in range(1, max_iterations + 2):  # +1: the forced wrap-up turn
        wrap_up = iteration > max_iterations
        if not _check_rate_limit() or not _check_cost_limit():
            result.text = "I've hit this system's usage limit for now. Please try again in a few minutes."
            result.stop_reason = "limit"
            break

        if wrap_up:
            # Append the note instead of editing the system prompt: changing
            # `system` mid-conversation invalidates earlier thinking blocks.
            _append_user_text(convo, provider, _WRAP_UP_NOTE)
        response = await provider.complete_with_tools(
            system_prompt=prompt,
            messages=convo,
            tools=wire_tools,
            model=model,
            max_tokens=max_tokens,
        )
        result.iterations = iteration
        result.cost_usd += response.cost_usd
        _record_cost(response.cost_usd)
        stop = response.stop_reason

        if stop == STOP_REFUSAL:
            logger.info("Tool loop: model declined the request (%s)", response.provider)
            result.text = response.text
            result.stop_reason = STOP_REFUSAL
            break

        if response.error or stop == STOP_ERROR:
            logger.error("Tool loop: model call failed: %s", response.error)
            result.text = response.text or "Sorry — the AI service is unavailable right now."
            result.stop_reason = "error"
            break

        if stop == STOP_PAUSE:
            if response.assistant_message:
                convo.append(response.assistant_message)
            continue

        calls = response.tool_calls
        if stop != STOP_TOOL_USE or not calls or wrap_up:
            # End and max-tokens both finish the answer with whatever text came back.
            result.text = response.text
            result.stop_reason = "max_iterations" if (wrap_up and calls) else stop
            break

        # Run this turn's tool calls concurrently; answer them together.
        records = await asyncio.gather(*(_run_one(registry, c, emit, allowed) for c in calls))
        result.tool_calls.extend(records)
        convo.append(response.assistant_message or {"role": "assistant", "content": response.text})
        convo.extend(provider.tool_result_messages([(c, *_tool_result(r)) for c, r in zip(calls, records)]))

    await emit_event(emit, {"type": "text", "text": result.text})
    return result
