"""
Memory Store API routes (search and statistics).

Memories belong to a venture (``system_key``). A search without ``venture``
covers only the ventures the caller may see (STORY-18): every venture for an
unrestricted caller, the caller's own for a venture-limited person or an
outside agent's token. ``/api/memory/stats`` reports LLM usage, which isn't
split by venture, so it is a system area closed to venture-limited callers
(:func:`realize_core.security.venture_scope.is_system_area`).
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from realize_api.dependencies import get_allowed_ventures

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/memory/search")
async def search_memory(request: Request, q: str, venture: str = "") -> dict:
    """Search stored memories within the caller's ventures.

    Args:
        request: The incoming request (its principal decides the ventures searched).
        q: FTS5 search text.
        venture: Only this venture (the access guard refuses one the caller can't see).
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query required")
    allowed = get_allowed_ventures(request)  # None = every venture
    if venture and allowed is not None and venture not in allowed:
        raise HTTPException(status_code=403, detail=f"You don't have access to venture '{venture}'")
    try:
        from realize_core.memory.store import search_memories

        results = search_memories(q.strip(), system_key=venture or None, limit=20, system_keys=allowed)
        return {"query": q, "results": results}
    except Exception:
        logger.warning("Memory search failed", exc_info=True)
        return {"query": q, "results": [], "error": "Memory search unavailable"}


@router.get("/memory/stats")
async def get_memory_stats() -> dict:
    """LLM usage statistics (every venture together; closed to venture-limited callers)."""
    try:
        from realize_core.memory.store import get_usage_stats

        stats = get_usage_stats()
        return {"stats": stats}
    except Exception:
        logger.warning("Memory stats failed", exc_info=True)
        return {"stats": {}, "error": "Memory statistics unavailable"}
