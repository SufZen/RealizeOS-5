"""
Activity API routes — paginated event queries and SSE streaming.

Endpoints:
- GET /api/ventures/{key}/activity — paginated, filterable activity events
- GET /api/activity/stream — SSE stream of real-time events
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/ventures/{venture_key}/activity")
async def get_venture_activity(
    venture_key: str,
    actor_id: str = Query(None, description="Filter by actor ID"),
    action: str = Query(None, description="Filter by action type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get paginated activity events for a venture."""
    from realize_core.activity.store import count_events, query_events

    events = query_events(
        venture_key=venture_key,
        actor_id=actor_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    total = count_events(venture_key=venture_key)

    return {
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/activity/stream")
async def activity_stream(request: Request):
    """SSE endpoint streaming real-time activity events."""
    from realize_core.activity.bus import get_recent_events, subscribe, unsubscribe

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        def on_event(event: dict):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        subscribe(on_event)
        try:
            # Send recent events as initial batch
            for event in get_recent_events(limit=10):
                data = json.dumps(event, default=str)
                yield f"data: {data}\n\n"

            # Stream new events
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    data = json.dumps(event, default=str)
                    yield f"data: {data}\n\n"
                except TimeoutError:
                    # Send keepalive ping
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(on_event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
