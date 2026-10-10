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

Tool use currently runs on providers with a native tool API (Claude). When
none is available the caller falls back to plain text routing.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

Emit = Callable[[dict[str, Any]], Awaitable[None] | None]

#: Default cap on model round-trips per answer.
DEFAULT_MAX_ITERATIONS = 8
#: Characters of a tool result echoed into trail events (the model gets it all).
EVENT_PREVIEW_CHARS = 2_000

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


async def _emit(emit: Emit | None, event: dict[str, Any]) -> None:
    """Send an event to the caller; a broken listener never breaks the loop."""
    if emit is None:
        return
    try:
        result = emit(event)
        if inspect.isawaitable(result):
            await result
    except Exception:
        logger.warning("Tool loop event listener failed for %s", event.get("type"), exc_info=True)


def _block_text(content: list[Any]) -> str:
    return "\n".join(b.text for b in content if getattr(b, "type", "") == "text" and getattr(b, "text", ""))


async def _run_one(registry, block, emit: Emit | None, allowed: frozenset[str]) -> ToolCallRecord:
    """Execute one ``tool_use`` block through the registry (and its gate).

    Only tools that were offered to the model (``allowed``) are executed. The
    model may name any action — e.g. after a prompt injection — and the offered
    set is what encodes persona restrictions and the read-only policy when no
    gate is installed.
    """
    params = dict(block.input or {})
    record = ToolCallRecord(id=block.id, name=block.name, input=params)
    await _emit(emit, {"type": "tool_call", "id": block.id, "name": block.name, "input": params})

    if block.name not in allowed:
        logger.warning("Tool loop: model called '%s', which was not offered; refused", block.name)
        record.error = f"Tool '{block.name}' is not available to this agent."
        await _emit(
            emit,
            {
                "type": "tool_result",
                "id": block.id,
                "name": block.name,
                "success": False,
                "held": False,
                "output": "",
                "error": record.error,
                "duration_ms": 0.0,
            },
        )
        return record

    started = time.perf_counter()
    result = await registry.execute(block.name, params)
    record.duration_ms = (time.perf_counter() - started) * 1000

    record.request_id = result.metadata.get("request_id") if result.metadata.get("requires_human") else None
    record.success = result.success and record.request_id is None
    record.output = result.output or ""
    record.error = result.error

    if record.held:
        await _emit(
            emit,
            {"type": "approval_requested", "id": block.id, "name": block.name, "request_id": record.request_id},
        )
    await _emit(
        emit,
        {
            "type": "tool_result",
            "id": block.id,
            "name": block.name,
            "success": record.success,
            "held": record.held,
            "output": record.output[:EVENT_PREVIEW_CHARS],
            "error": record.error,
            "duration_ms": round(record.duration_ms, 1),
        },
    )
    return record


def _tool_result_block(record: ToolCallRecord) -> dict[str, Any]:
    """Build the ``tool_result`` content block sent back to the model."""
    if record.held:
        content = _HELD_NOTE.format(request_id=record.request_id)
        return {"type": "tool_result", "tool_use_id": record.id, "content": content}
    if not record.success:
        content = record.error or record.output or "The tool failed without an error message."
        return {"type": "tool_result", "tool_use_id": record.id, "content": content, "is_error": True}
    return {"type": "tool_result", "tool_use_id": record.id, "content": record.output or "(no output)"}


def tool_capable_provider():
    """Return an available provider with native tool use (Claude), or None."""
    from realize_core.llm.registry import get_registry

    provider = get_registry().get_provider_by_name("claude")
    if provider is not None and provider.is_available():
        return provider
    return None


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
        messages: Conversation so far (Claude message format); not mutated.
        tools: Claude-format tool schemas the agent may use.
        registry: Tool registry to execute through (default: global registry).
        provider: LLM provider with ``complete_with_tools`` (default: Claude).
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
    result = LoopResult(text="")
    prompt = system_prompt

    for iteration in range(1, max_iterations + 2):  # +1: the forced wrap-up turn
        wrap_up = iteration > max_iterations
        if not _check_rate_limit() or not _check_cost_limit():
            result.text = "I've hit this system's usage limit for now. Please try again in a few minutes."
            result.stop_reason = "limit"
            break

        response = await provider.complete_with_tools(
            system_prompt=f"{prompt}\n\n{_WRAP_UP_NOTE}" if wrap_up else prompt,
            messages=convo,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
        )
        result.iterations = iteration
        result.cost_usd += response.cost_usd
        _record_cost(response.cost_usd)

        if response.error or response.raw is None:
            logger.error("Tool loop: model call failed: %s", response.error)
            result.text = response.text or "Sorry — the AI service is unavailable right now."
            result.stop_reason = "error"
            break

        message = response.raw
        stop = getattr(message, "stop_reason", "") or ""
        tool_blocks = [b for b in message.content if getattr(b, "type", "") == "tool_use"]

        if stop == "pause_turn":
            convo.append({"role": "assistant", "content": message.content})
            continue

        if stop != "tool_use" or not tool_blocks or wrap_up:
            result.text = _block_text(message.content) or response.text
            result.stop_reason = "max_iterations" if (wrap_up and tool_blocks) else stop
            if stop == "refusal":
                details = getattr(message, "stop_details", None)
                logger.info("Tool loop: model declined (%s)", getattr(details, "category", None))
            break

        # Run this turn's tool calls concurrently; answer them in ONE user message.
        records = await asyncio.gather(*(_run_one(registry, b, emit, allowed) for b in tool_blocks))
        result.tool_calls.extend(records)
        convo.append({"role": "assistant", "content": message.content})
        convo.append({"role": "user", "content": [_tool_result_block(r) for r in records]})

    await _emit(emit, {"type": "text", "text": result.text})
    return result
