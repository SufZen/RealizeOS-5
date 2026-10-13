"""
Dashboard API routes — overview endpoint for the main dashboard page.

Endpoints:
- GET /api/dashboard — ventures, agent counts, skill counts, recent activity
"""

import logging
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request

from realize_api.dependencies import get_allowed_ventures, visible_systems
from realize_api.routes.route_helpers import count_skills

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/dashboard")
async def get_dashboard_overview(request: Request):
    """
    Dashboard overview: ventures with health summary + recent activity.

    Returns:
        ventures: list of venture summaries (name, key, agent count, skill count)
        recent_activity: last 20 activity events across all ventures
        agent_total: configured agents across the visible ventures (the
            headline count; equals the sum of the ventures' ``agent_count``)
        agent_summary: those configured agents by runtime state. An agent
            with no runtime-state row yet has never run, so it counts as
            ``idle`` (the venture page shows it the same way); rows for agents
            that are no longer configured are not counted.
    """
    systems: dict = visible_systems(request)
    allowed = get_allowed_ventures(request)  # None = every venture
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    ventures = []
    for key, sys_conf in systems.items():
        agent_count = len(sys_conf.get("agents", {}))
        skill_count = count_skills(kb_path, sys_conf)
        ventures.append(
            {
                "key": key,
                "name": sys_conf.get("name", key),
                "agent_count": agent_count,
                "skill_count": skill_count,
            }
        )

    # Recent activity (last 20 across all ventures)
    recent_activity = []
    try:
        from realize_core.activity.store import query_events

        recent_activity = query_events(limit=20, venture_keys=allowed)
    except Exception as e:
        logger.debug(f"Activity query failed: {e}")

    configured = {(key, agent) for key, sys_conf in systems.items() for agent in sys_conf.get("agents", {})}
    return {
        "ventures": ventures,
        "venture_count": len(ventures),
        "recent_activity": recent_activity,
        "agent_total": len(configured),
        "agent_summary": _agent_state_counts(configured, allowed),
    }


def _agent_state_counts(configured: set[tuple[str, str]], allowed: frozenset[str] | None) -> dict[str, int]:
    """Configured agents by runtime state (Codex audit N12).

    Every configured agent is counted once. One without a runtime-state row
    (a fresh install, or an agent that has never run) is ``idle``.
    """
    states: dict[tuple[str, str], str] = {}
    try:
        from realize_core.db.schema import get_connection

        conn = get_connection()
        try:
            where, params = "", []
            if allowed is not None:
                keys = sorted(allowed) or [""]
                where = f"WHERE venture_key IN ({','.join('?' for _ in keys)})"
                params = keys
            rows = conn.execute(f"SELECT venture_key, agent_key, status FROM agent_states {where}", params).fetchall()
            states = {(row["venture_key"], row["agent_key"]): row["status"] for row in rows}
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        logger.debug("Agent status query failed: %s", exc)

    summary = {"idle": 0, "running": 0, "paused": 0, "error": 0}
    for agent in configured:
        status = states.get(agent, "idle")
        summary[status if status in summary else "idle"] += 1
    return summary
