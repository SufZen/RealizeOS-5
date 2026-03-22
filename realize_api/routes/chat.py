"""
Chat API routes: POST /chat, GET /conversations.
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, field_validator

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096
CHAT_TIMEOUT_SECONDS = 120


class ChatRequest(BaseModel):
    message: str
    system_key: str
    user_id: str = "api-user"
    agent_key: Optional[str] = None
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


class ChatResponse(BaseModel):
    response: str
    system_key: str
    agent_key: str
    user_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    """Send a message and get an AI response."""
    systems = getattr(request.app.state, "systems", {})
    kb_path = getattr(request.app.state, "kb_path", None)
    shared_config = getattr(request.app.state, "shared_config", {
        "identity": "shared/identity.md",
        "preferences": "shared/user-preferences.md",
    })

    if not systems:
        raise HTTPException(status_code=503, detail="No systems configured. Run setup first.")

    if body.system_key not in systems:
        available = list(systems.keys())
        raise HTTPException(
            status_code=404,
            detail=f"System '{body.system_key}' not found. Available: {available}",
        )

    system_config = systems[body.system_key]

    from realize_core.base_handler import process_message
    try:
        response = await asyncio.wait_for(
            process_message(
                system_key=body.system_key,
                user_id=body.user_id,
                message=body.message,
                kb_path=kb_path,
                system_config=system_config,
                shared_config=shared_config,
                channel=body.channel,
            ),
            timeout=CHAT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(f"Chat timeout after {CHAT_TIMEOUT_SECONDS}s for {body.system_key}")
        raise HTTPException(status_code=504, detail=f"Request timed out after {CHAT_TIMEOUT_SECONDS}s")
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)[:200]}")

    # Determine which agent handled it
    agent_used = body.agent_key or "orchestrator"
    try:
        from realize_core.pipeline.session import get_session
        session = get_session(body.system_key, body.user_id)
        if session:
            agent_used = session.active_agent
    except Exception:
        pass

    # Humanize output
    try:
        from realize_core.utils.humanizer import clean_output
        response = clean_output(response, channel=body.channel)
    except Exception:
        pass

    return ChatResponse(
        response=response,
        system_key=body.system_key,
        agent_key=agent_used,
        user_id=body.user_id,
    )


@router.get("/conversations/{system_key}/{user_id}")
async def get_conversations(system_key: str, user_id: str, limit: int = 50):
    """Get conversation history for a user in a system."""
    try:
        from realize_core.memory.conversation import get_history
        history = get_history(system_key, user_id, limit=min(limit, 200))
        return {"system_key": system_key, "user_id": user_id, "messages": history}
    except Exception as e:
        logger.warning(f"Failed to load conversations: {e}")
        return {"system_key": system_key, "user_id": user_id, "messages": []}


@router.delete("/conversations/{system_key}/{user_id}")
async def clear_conversations(system_key: str, user_id: str):
    """Clear conversation history for a user."""
    try:
        from realize_core.memory.conversation import clear_history
        clear_history(system_key, user_id)
        return {"status": "cleared", "system_key": system_key, "user_id": user_id}
    except Exception as e:
        logger.warning(f"Failed to clear conversations: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear conversation history")
