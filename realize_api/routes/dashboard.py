"""
Dashboard API routes — overview endpoint for the main dashboard page.

Endpoints:
- GET /api/dashboard — ventures, agent counts, skill counts, recent activity
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/dashboard")
async def get_dashboard_overview(request: Request):
    """
    Dashboard overview: ventures with health summary + recent activity.

    Returns:
        ventures: list of venture summaries (name, key, agent count, skill count)
        recent_activity: last 20 activity events across all ventures
        system_health: provider status, venture count
    """
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    ventures = []
    for key, sys_conf in systems.items():
        agent_count = len(sys_conf.get("agents", {}))
        skill_count = _count_skills(kb_path, sys_conf)
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

        recent_activity = query_events(limit=20)
    except Exception as e:
        logger.debug(f"Activity query failed: {e}")

    # Agent status summary
    agent_summary = {"idle": 0, "running": 0, "paused": 0, "error": 0}
    try:
        from realize_core.db.schema import get_connection

        conn = get_connection()
        rows = conn.execute("SELECT status, COUNT(*) as c FROM agent_states GROUP BY status").fetchall()
        for row in rows:
            if row["status"] in agent_summary:
                agent_summary[row["status"]] = row["c"]
        conn.close()
    except Exception:
        pass

    return {
        "ventures": ventures,
        "venture_count": len(ventures),
        "recent_activity": recent_activity,
        "agent_summary": agent_summary,
    }


def _count_skills(kb_path: Path, sys_conf: dict) -> int:
    """Count YAML skill files in a venture's R-routines/skills/ directory."""
    routines_dir = sys_conf.get("routines_dir", "")
    if not routines_dir:
        return 0
    skills_path = kb_path / routines_dir / "skills"
    if not skills_path.exists():
        return 0
    return sum(1 for f in skills_path.glob("*.yaml"))
