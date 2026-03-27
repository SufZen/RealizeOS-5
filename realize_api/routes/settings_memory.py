"""
Memory Store API routes (search and statistics).
"""

import logging

from fastapi import APIRouter, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/memory/search")
async def search_memory(q: str, venture: str = ""):
    """Search stored memories."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query required")
    try:
        from realize_core.memory.store import search_memories

        results = search_memories(q.strip(), system_key=venture or None, limit=20)
        return {"query": q, "results": results}
    except Exception as e:
        return {"query": q, "results": [], "error": str(e)}


@router.get("/memory/stats")
async def get_memory_stats():
    """Get memory store statistics."""
    try:
        from realize_core.memory.store import get_usage_stats

        stats = get_usage_stats()
        return {"stats": stats}
    except Exception as e:
        return {"stats": {}, "error": str(e)}
