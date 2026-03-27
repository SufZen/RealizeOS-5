"""
Venture Agent routes — agent lifecycle management per venture.

Endpoints:
- GET  /api/ventures/{key}/agents — agent list with status
- GET  /api/ventures/{key}/agents/{agent} — agent detail
- POST /api/ventures/{key}/agents/{agent}/pause — pause agent
- POST /api/ventures/{key}/agents/{agent}/resume — resume agent
- PUT  /api/ventures/{key}/agents/{agent}/schedule — set schedule
- DELETE /api/ventures/{key}/agents/{agent}/schedule — clear schedule
"""

import logging
from datetime import UTC
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from realize_api.routes.route_helpers import get_agents_with_status

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/ventures/{venture_key}/agents")
async def list_venture_agents(venture_key: str, request: Request):
    """List agents for a venture with current status from DB."""
    systems: dict = getattr(request.app.state, "systems", {})

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    sys_conf = systems[venture_key]
    agents = get_agents_with_status(sys_conf, venture_key)

    return {"agents": agents, "venture_key": venture_key}


@router.get("/ventures/{venture_key}/agents/{agent_key}")
async def get_agent_detail(venture_key: str, agent_key: str, request: Request):
    """Get detailed agent info including config, status, and recent activity."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    sys_conf = systems[venture_key]
    agents = sys_conf.get("agents", {})
    if agent_key not in agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found in venture '{venture_key}'")

    # Read agent definition file
    definition = ""
    agent_path = kb_path / agents[agent_key]
    if agent_path.exists():
        try:
            definition = agent_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed to read agent definition %s: %s", agent_path, exc)

    # Get status from DB
    status_data = {"status": "idle", "last_run_at": None, "last_error": None}
    try:
        from realize_core.scheduler.lifecycle import get_agent_status

        state = get_agent_status(agent_key, venture_key)
        if state:
            status_data = {
                "status": state["status"],
                "last_run_at": state.get("last_run_at"),
                "last_error": state.get("last_error"),
                "schedule_cron": state.get("schedule_cron"),
                "schedule_interval_sec": state.get("schedule_interval_sec"),
                "next_run_at": state.get("next_run_at"),
            }
    except Exception as exc:
        logger.debug("Agent status lookup failed for %s/%s: %s", agent_key, venture_key, exc)

    # Recent activity for this agent
    recent_activity = []
    try:
        from realize_core.activity.store import query_events

        recent_activity = query_events(venture_key=venture_key, actor_id=agent_key, limit=20)
    except Exception as exc:
        logger.debug("Activity query failed for %s/%s: %s", venture_key, agent_key, exc)

    return {
        "key": agent_key,
        "venture_key": venture_key,
        "definition_path": agents[agent_key],
        "definition": definition,
        **status_data,
        "recent_activity": recent_activity,
    }


@router.post("/ventures/{venture_key}/agents/{agent_key}/pause")
async def pause_agent(venture_key: str, agent_key: str, request: Request):
    """Pause an agent — it will be skipped during message routing."""
    systems: dict = getattr(request.app.state, "systems", {})
    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")
    if agent_key not in systems[venture_key].get("agents", {}):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    from realize_core.scheduler.lifecycle import set_agent_status

    set_agent_status(agent_key, venture_key, "paused")

    try:
        from realize_core.activity.logger import log_event

        log_event(
            venture_key=venture_key,
            actor_type="user",
            actor_id="dashboard",
            action="agent_paused",
            entity_type="agent",
            entity_id=agent_key,
        )
    except Exception as exc:
        logger.debug("Activity log failed for agent_paused: %s", exc)

    return {
        "agent_key": agent_key,
        "venture_key": venture_key,
        "status": "paused",
    }


@router.post("/ventures/{venture_key}/agents/{agent_key}/resume")
async def resume_agent(venture_key: str, agent_key: str, request: Request):
    """Resume a paused agent — sets status back to idle."""
    systems: dict = getattr(request.app.state, "systems", {})
    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")
    if agent_key not in systems[venture_key].get("agents", {}):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    from realize_core.scheduler.lifecycle import set_agent_status

    set_agent_status(agent_key, venture_key, "idle")

    try:
        from realize_core.activity.logger import log_event

        log_event(
            venture_key=venture_key,
            actor_type="user",
            actor_id="dashboard",
            action="agent_resumed",
            entity_type="agent",
            entity_id=agent_key,
        )
    except Exception as exc:
        logger.debug("Activity log failed for agent_resumed: %s", exc)

    return {
        "agent_key": agent_key,
        "venture_key": venture_key,
        "status": "idle",
    }


@router.put("/ventures/{venture_key}/agents/{agent_key}/schedule")
async def set_agent_schedule(venture_key: str, agent_key: str, request: Request):
    """Set or update an agent's schedule (cron or interval)."""
    systems: dict = getattr(request.app.state, "systems", {})
    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")
    if agent_key not in systems[venture_key].get("agents", {}):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    body = await request.json()
    cron = body.get("schedule_cron")
    interval = body.get("schedule_interval_sec")

    if not cron and not interval:
        raise HTTPException(status_code=400, detail="Provide schedule_cron or schedule_interval_sec")

    from datetime import datetime, timedelta

    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        # Ensure agent_states row exists
        existing = conn.execute(
            "SELECT 1 FROM agent_states WHERE agent_key = ? AND venture_key = ?",
            (agent_key, venture_key),
        ).fetchone()

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        next_run = None
        if interval:
            next_run = (datetime.now(UTC) + timedelta(seconds=int(interval))).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        if existing:
            conn.execute(
                """UPDATE agent_states
                   SET schedule_cron = ?, schedule_interval_sec = ?, next_run_at = ?, updated_at = ?
                   WHERE agent_key = ? AND venture_key = ?""",
                (cron, int(interval) if interval else None, next_run, now, agent_key, venture_key),
            )
        else:
            conn.execute(
                """INSERT INTO agent_states
                   (agent_key, venture_key, status, schedule_cron, schedule_interval_sec, next_run_at, updated_at)
                   VALUES (?, ?, 'idle', ?, ?, ?, ?)""",
                (agent_key, venture_key, cron, int(interval) if interval else None, next_run, now),
            )
        conn.commit()
    finally:
        conn.close()

    # Reload scheduler if running
    try:
        from realize_core.scheduler.heartbeat import reload_schedules

        reload_schedules()
    except Exception as exc:
        logger.debug("Scheduler reload failed: %s", exc)

    try:
        from realize_core.activity.logger import log_event

        log_event(
            venture_key=venture_key,
            actor_type="user",
            actor_id="dashboard",
            action="schedule_updated",
            entity_type="agent",
            entity_id=agent_key,
            details=f'{{"cron": "{cron or ""}", "interval_sec": {interval or 0}}}',
        )
    except Exception as exc:
        logger.debug("Activity log failed for schedule_updated: %s", exc)

    return {
        "agent_key": agent_key,
        "venture_key": venture_key,
        "schedule_cron": cron,
        "schedule_interval_sec": int(interval) if interval else None,
        "next_run_at": next_run,
    }


@router.delete("/ventures/{venture_key}/agents/{agent_key}/schedule")
async def clear_agent_schedule(venture_key: str, agent_key: str, request: Request):
    """Remove an agent's schedule."""
    systems: dict = getattr(request.app.state, "systems", {})
    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")
    if agent_key not in systems[venture_key].get("agents", {}):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        conn.execute(
            """UPDATE agent_states
               SET schedule_cron = NULL, schedule_interval_sec = NULL, next_run_at = NULL
               WHERE agent_key = ? AND venture_key = ?""",
            (agent_key, venture_key),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        from realize_core.scheduler.heartbeat import reload_schedules

        reload_schedules()
    except Exception as exc:
        logger.debug("Scheduler reload failed: %s", exc)

    return {
        "agent_key": agent_key,
        "venture_key": venture_key,
        "schedule": None,
    }
