"""
Chat API routes: POST /chat, POST /chat/stream, GET /conversations.

Every answer carries a "what I used" trail (STORY-17): the numbered KB
sources the prompt included and the tools the agent called, in order.
``/chat/stream`` sends the same events live over SSE.
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096
CHAT_TIMEOUT_SECONDS = 120
#: Seconds between SSE keepalive comments while the answer is being prepared.
STREAM_KEEPALIVE_SECONDS = 15


def _principal(request: Request) -> tuple[str | None, str]:
    """The authenticated caller as ``(user_id, role)``; user_id is None when auth is off.

    MCP calls arrive through a proxy request without ``state``; the MCP chat
    tool applies the same rule with its own authenticated user before calling.
    """
    state = getattr(request, "state", None)
    return getattr(state, "user_id", None), getattr(state, "role", None) or ""


def _scopes(request: Request) -> list[str]:
    """The caller's scopes (an outside agent's marker lives there)."""
    return list(getattr(getattr(request, "state", None), "scopes", None) or [])


def _chat_user(request: Request, requested: str) -> str:
    """The user a chat request acts for: the signed-in user unless owner/admin."""
    from realize_core.security.chat_access import chat_user_for

    return chat_user_for(*_principal(request), requested, scopes=_scopes(request))


def _require_own_conversation(request: Request, user_id: str) -> None:
    """403 unless the caller may read or clear ``user_id``'s conversation."""
    from realize_core.security.chat_access import may_access_conversation

    if not may_access_conversation(*_principal(request), user_id, scopes=_scopes(request)):
        raise HTTPException(status_code=403, detail="You can only access your own conversations")


class ChatRequest(BaseModel):
    message: str
    system_key: str
    user_id: str = "api-user"
    agent_key: str | None = None
    channel: str = "api"

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Message cannot be empty")
        if len(stripped) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message too long ({len(stripped)} chars, max {MAX_MESSAGE_LENGTH})")
        return stripped


class TrailSource(BaseModel):
    """A numbered KB source the answer's prompt included."""

    id: str
    title: str
    path: str


class Trail(BaseModel):
    """What an answer was built from: sources and tool steps, in order."""

    sources: list[TrailSource] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    response: str
    system_key: str
    agent_key: str
    user_id: str
    message_id: int | None = None
    trail: Trail = Field(default_factory=Trail)


def _resolve_system(body: ChatRequest, request: Request) -> tuple[dict, dict]:
    """Return ``(systems, system_config)`` or raise the matching HTTP error.

    Only ventures the caller may see count: another venture is "not found".
    """
    from realize_api.dependencies import visible_systems

    systems = visible_systems(request)
    if not systems:
        raise HTTPException(status_code=503, detail="No systems configured. Run setup first.")
    if body.system_key not in systems:
        raise HTTPException(
            status_code=404,
            detail=f"System '{body.system_key}' not found. Available: {list(systems.keys())}",
        )
    return systems, systems[body.system_key]


def _check_agent(body: ChatRequest, system_config: dict) -> None:
    """A chosen agent must belong to the venture (Codex audit F18)."""
    agent = body.agent_key
    if agent and agent != "orchestrator" and agent not in (system_config.get("agents") or {}):
        raise HTTPException(status_code=400, detail=f"Agent '{agent}' is not part of venture '{body.system_key}'")


async def _process(
    body: ChatRequest, request: Request, systems: dict, system_config: dict, recorder, selected: dict
) -> str:
    """Run the message through the pipeline, reporting the trail to ``recorder``.

    ``selected`` receives the agent that actually answered.
    """
    from realize_core.security.agent_access import acting_for_outside_agent, is_agent_subject
    from realize_core.security.agent_tokens import principal_id_for

    state = getattr(request, "state", None)
    if is_agent_subject(state):
        # An outside agent's chat: write tools are held for a person and
        # trigger phrases don't run skills (STORY-37).
        with acting_for_outside_agent(principal_id_for(state.user_id, getattr(state, "scopes", None))):
            return await _run_pipeline(body, request, systems, system_config, recorder, selected)
    return await _run_pipeline(body, request, systems, system_config, recorder, selected)


async def _run_pipeline(
    body: ChatRequest, request: Request, systems: dict, system_config: dict, recorder, selected: dict
) -> str:
    """The message through ``base_handler.process_message``."""
    from realize_core import base_handler
    from realize_core.config import get_features

    shared_config = getattr(
        request.app.state,
        "shared_config",
        {
            "identity": "shared/identity.md",
            "preferences": "shared/user-preferences.md",
        },
    )
    return await base_handler.process_message(
        system_key=body.system_key,
        user_id=body.user_id,
        message=body.message,
        kb_path=getattr(request.app.state, "kb_path", None),
        system_config=system_config,
        shared_config=shared_config,
        channel=body.channel,
        # Without these, activity logging, cross-system context and
        # every other feature-flagged branch is silently off for API chat.
        features=get_features(getattr(request.app.state, "config", None) or {}),
        all_systems=systems,
        emit=recorder,
        requested_agent=body.agent_key,
        selected=selected,
    )


def _finish(body: ChatRequest, response: str, recorder, selected: dict) -> ChatResponse:
    """Build the response: the agent that actually answered, humanized text, stored trail."""
    agent_used = selected.get("agent_key")
    if not agent_used:
        # Not routed to an agent (creative session, skill, resumed skill).
        agent_used = "orchestrator"
        try:
            from realize_core.pipeline.session import get_session

            session = get_session(body.system_key, body.user_id)
            if session:
                agent_used = session.active_agent
        except Exception as exc:
            logger.debug("Session lookup failed: %s", exc)

    try:
        from realize_core.utils.humanizer import clean_output

        response = clean_output(response, channel=body.channel)
    except Exception as exc:
        logger.debug("Humanizer clean_output failed: %s", exc)

    if recorder.message_id is not None and not recorder.is_empty:
        from realize_core.memory.conversation import save_trail

        save_trail(recorder.message_id, recorder.stored())

    return ChatResponse(
        response=response,
        system_key=body.system_key,
        agent_key=agent_used,
        user_id=body.user_id,
        message_id=recorder.message_id,
        trail=Trail(**recorder.to_dict()),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    """Send a message and get an AI response with its "what I used" trail."""
    from realize_core.agents.trail import TrailRecorder

    body.user_id = _chat_user(request, body.user_id)
    systems, system_config = _resolve_system(body, request)
    _check_agent(body, system_config)
    recorder = TrailRecorder()
    selected: dict = {}
    try:
        response = await asyncio.wait_for(
            _process(body, request, systems, system_config, recorder, selected),
            timeout=CHAT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.error("Chat timeout after %ss for %s", CHAT_TIMEOUT_SECONDS, body.system_key)
        raise HTTPException(status_code=504, detail=f"Request timed out after {CHAT_TIMEOUT_SECONDS}s")
    except Exception:
        logger.error("Chat processing failed for %s", body.system_key, exc_info=True)
        raise HTTPException(status_code=500, detail="Processing error — see server logs")

    return _finish(body, response, recorder, selected)


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, request: Request):
    """Send a message and stream the trail live over SSE.

    Events (``data:`` JSON with a ``type``): ``source``, ``tool_call``,
    ``tool_result``, ``approval_requested``, ``text``, then one ``final``
    (the full chat response) — or ``error`` without internal detail.
    """
    from realize_core.agents.trail import TrailRecorder

    body.user_id = _chat_user(request, body.user_id)
    systems, system_config = _resolve_system(body, request)  # plain HTTP errors before streaming starts
    _check_agent(body, system_config)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    recorder = TrailRecorder(forward=queue.put_nowait)
    selected: dict = {}

    async def event_stream():
        task = asyncio.ensure_future(
            asyncio.wait_for(_process(body, request, systems, system_config, recorder, selected), CHAT_TIMEOUT_SECONDS)
        )
        try:
            while not task.done() or not queue.empty():
                if not queue.empty():
                    yield _sse(queue.get_nowait())
                    continue
                getter = asyncio.ensure_future(queue.get())
                done, _ = await asyncio.wait(
                    {getter, task}, timeout=STREAM_KEEPALIVE_SECONDS, return_when=asyncio.FIRST_COMPLETED
                )
                if getter in done:
                    yield _sse(getter.result())
                    continue
                getter.cancel()  # an unread item stays in the queue
                if not done:
                    if await request.is_disconnected():
                        logger.info("Chat stream client left; cancelling (%s)", body.system_key)
                        return
                    yield ": keepalive\n\n"

            try:
                response = task.result()
            except TimeoutError:
                logger.error("Chat stream timeout after %ss for %s", CHAT_TIMEOUT_SECONDS, body.system_key)
                yield _sse({"type": "error", "detail": f"Request timed out after {CHAT_TIMEOUT_SECONDS}s"})
                return
            except Exception:
                logger.error("Chat stream processing failed for %s", body.system_key, exc_info=True)
                yield _sse({"type": "error", "detail": "Processing error — see server logs"})
                return

            final = _finish(body, response, recorder, selected)
            yield _sse({"type": "final", **final.model_dump()})
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations/{system_key}/{user_id}")
async def get_conversations(system_key: str, user_id: str, request: Request, limit: int = 50):
    """Get conversation history for a user in a system, with each answer's trail."""
    _require_own_conversation(request, user_id)
    try:
        from realize_core.memory.conversation import get_history, get_trails

        history = get_history(system_key, user_id, limit=min(limit, 200))
        trails = get_trails([m.get("id") for m in history if m.get("role") == "assistant"])
        messages = [{**m, "trail": trails[m["id"]]} if m.get("id") in trails else dict(m) for m in history]
        return {"system_key": system_key, "user_id": user_id, "messages": messages}
    except Exception as e:
        logger.warning(f"Failed to load conversations: {e}")
        return {"system_key": system_key, "user_id": user_id, "messages": []}


@router.delete("/conversations/{system_key}/{user_id}")
async def clear_conversations(system_key: str, user_id: str, request: Request):
    """Clear conversation history for a user."""
    _require_own_conversation(request, user_id)
    try:
        from realize_core.memory.conversation import clear_history

        clear_history(system_key, user_id)
        return {"status": "cleared", "system_key": system_key, "user_id": user_id}
    except Exception as e:
        logger.warning(f"Failed to clear conversations: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear conversation history")
