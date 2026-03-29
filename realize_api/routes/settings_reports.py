"""
Scheduled Reports API routes (on-demand triggers).
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/reports/morning-briefing")
async def trigger_morning_briefing(request: Request):
    """Generate a morning briefing on demand."""
    config = getattr(request.app.state, "config", {})
    systems = getattr(request.app.state, "systems", {})
    kb_path = getattr(request.app.state, "kb_path", Path("."))
    features = config.get("features", {})

    from realize_core.scheduler.reports import generate_morning_briefing

    content = await generate_morning_briefing(systems, kb_path, features)
    return {"report": "morning_briefing", "content": content}


@router.post("/reports/weekly-review")
async def trigger_weekly_review(request: Request):
    """Generate a weekly review on demand."""
    config = getattr(request.app.state, "config", {})
    systems = getattr(request.app.state, "systems", {})
    kb_path = getattr(request.app.state, "kb_path", Path("."))
    features = config.get("features", {})

    from realize_core.scheduler.reports import generate_weekly_review

    content = await generate_weekly_review(systems, kb_path, features)
    return {"report": "weekly_review", "content": content}
