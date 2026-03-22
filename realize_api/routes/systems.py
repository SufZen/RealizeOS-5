"""
Systems API routes: CRUD for system configurations, agents, and skills.
"""
import logging

from fastapi import APIRouter, Request, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/systems")
async def list_systems(request: Request):
    """List all configured systems."""
    systems = request.app.state.systems
    result = []
    for key, config in systems.items():
        result.append({
            "key": key,
            "name": config.get("name", key),
            "agents": list(config.get("agents", {}).keys()),
            "routing": {k: v for k, v in config.get("routing", {}).items()},
        })
    return {"systems": result}


@router.get("/systems/{system_key}")
async def get_system(system_key: str, request: Request):
    """Get detailed information about a specific system."""
    systems = request.app.state.systems
    if system_key not in systems:
        raise HTTPException(status_code=404, detail=f"System '{system_key}' not found")

    config = systems[system_key]
    return {
        "key": system_key,
        "name": config.get("name", system_key),
        "agents": list(config.get("agents", {}).keys()),
        "routing": config.get("routing", {}),
        "brand_identity": config.get("brand_identity"),
        "brand_voice": config.get("brand_voice"),
    }


@router.get("/systems/{system_key}/agents")
async def list_agents(system_key: str, request: Request):
    """List agents for a system."""
    systems = request.app.state.systems
    if system_key not in systems:
        raise HTTPException(status_code=404, detail=f"System '{system_key}' not found")

    agents = systems[system_key].get("agents", {})
    return {
        "system_key": system_key,
        "agents": [{"key": k, "path": v} for k, v in agents.items()],
    }


@router.get("/systems/{system_key}/skills")
async def list_skills(system_key: str, request: Request):
    """List available skills for a system."""
    try:
        from realize_core.skills.detector import get_skills_for_system
        skills = get_skills_for_system(system_key)
        return {
            "system_key": system_key,
            "skills": [
                {"name": s.get("name", ""), "triggers": s.get("triggers", []),
                 "version": s.get("_version", 1)}
                for s in skills
            ],
        }
    except Exception as e:
        return {"system_key": system_key, "skills": [], "error": str(e)}


@router.get("/systems/{system_key}/sessions/{user_id}")
async def get_session(system_key: str, user_id: str):
    """Get the active creative session for a user."""
    from realize_core.pipeline.session import get_session as _get
    session = _get(system_key, user_id)
    if not session:
        return {"session": None}
    return {
        "session": {
            "id": session.id, "stage": session.stage,
            "active_agent": session.active_agent,
            "task_type": session.task_type,
            "pipeline": session.pipeline,
            "pipeline_index": session.pipeline_index,
            "drafts_count": len(session.drafts),
            "brief": session.brief,
            "summary": session.summary(),
        }
    }


@router.post("/systems/reload")
async def reload_systems(request: Request):
    """Reload system configurations from YAML."""
    from realize_core.config import load_config, build_systems_dict
    from realize_core.prompt.builder import clear_cache

    config = load_config()
    request.app.state.config = config
    request.app.state.systems = build_systems_dict(config)

    clear_cache()

    return {
        "status": "reloaded",
        "systems": list(request.app.state.systems.keys()),
    }
