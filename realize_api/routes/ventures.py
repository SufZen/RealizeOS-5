"""
Venture routes — core venture CRUD and overview endpoints.

Agent management: see venture_agents.py
KB file operations: see venture_kb.py
Shared files:      see venture_shared.py

Endpoints:
- GET    /api/ventures — list ventures with health summary
- GET    /api/ventures/{key} — venture detail with FABRIC analysis
- GET    /api/ventures/{key}/org-tree — agent hierarchy tree
- GET    /api/ventures/{key}/skills — list skills (convenience)
- POST   /api/ventures — create venture
- DELETE /api/ventures/{key} — delete venture
- POST   /api/ventures/{key}/export — export as zip
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from realize_api.dependencies import visible_systems
from realize_api.routes.route_helpers import (
    analyze_fabric,
    count_skills,
    get_agents_with_status,
    get_skills,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class CreateVentureBody(BaseModel):
    """Request body for venture creation."""

    key: str
    name: str = ""
    description: str = ""


@router.get("/ventures")
async def list_ventures(request: Request):
    """List all ventures with health summary."""
    systems: dict = visible_systems(request)
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    ventures = []
    for key, sys_conf in systems.items():
        fabric = analyze_fabric(kb_path, sys_conf)
        ventures.append(
            {
                "key": key,
                "name": sys_conf.get("name", key),
                "description": sys_conf.get("description", ""),
                "locale": sys_conf.get("locale", ""),
                "agent_count": len(sys_conf.get("agents", {})),
                "skill_count": count_skills(kb_path, sys_conf),
                "fabric_completeness": fabric["completeness"],
                # Problems an operator should see, e.g. packs it relies on are switched off.
                "warnings": list(sys_conf.get("warnings") or []),
            }
        )

    from realize_core.scaffold import config_writable

    # The dashboard hides create/delete when realize-os.yaml can't be edited.
    return {"ventures": ventures, "config_writable": config_writable(kb_path)}


@router.get("/ventures/{venture_key}")
async def get_venture_detail(venture_key: str, request: Request):
    """Get detailed venture information including FABRIC analysis."""
    systems: dict = visible_systems(request)
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    sys_conf = systems[venture_key]
    fabric = analyze_fabric(kb_path, sys_conf)
    agents = get_agents_with_status(sys_conf, venture_key, kb_path)
    skills = get_skills(kb_path, sys_conf)

    return {
        "key": venture_key,
        "name": sys_conf.get("name", venture_key),
        "description": sys_conf.get("description", ""),
        "agent_count": len(sys_conf.get("agents", {})),
        "skill_count": len(skills),
        "agents": agents,
        "skills": skills,
        "fabric": fabric,
        "warnings": list(sys_conf.get("warnings") or []),
    }


@router.get("/ventures/{venture_key}/org-tree")
async def get_org_tree(venture_key: str, request: Request):
    """Get the agent hierarchy / org tree for a venture."""
    systems: dict = visible_systems(request)
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    from realize_core.scheduler.hierarchy import build_org_tree

    tree = build_org_tree(kb_path, systems[venture_key])
    return {"venture_key": venture_key, **tree}


@router.get("/ventures/{venture_key}/skills")
async def list_venture_skills(venture_key: str, request: Request):
    """List skills for a venture with execution stats."""
    systems: dict = visible_systems(request)
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    sys_conf = systems[venture_key]
    skills = get_skills(kb_path, sys_conf)

    return {"skills": skills, "venture_key": venture_key}


# ---------------------------------------------------------------------------
# Venture CRUD
# ---------------------------------------------------------------------------


@router.post("/ventures")
async def create_venture(body: CreateVentureBody, request: Request):
    """Create a new venture with FABRIC scaffolding."""
    key = body.key.strip()
    name = body.name.strip() if body.name else ""
    description = body.description.strip() if body.description else ""

    if not key:
        raise HTTPException(status_code=400, detail="Venture key is required")
    if len(key) > 50:
        raise HTTPException(status_code=400, detail="Key must be 50 characters or less")

    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    from realize_core.scaffold import scaffold_venture

    try:
        scaffold_venture(str(kb_path), key, name=name, description=description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"Venture '{key}' already exists") from exc
    except OSError as exc:
        logger.warning("Venture create '%s' failed: %s", key, exc)
        raise HTTPException(status_code=503, detail=f"Could not create venture: {exc}") from exc

    _reload_systems(request, kb_path)

    try:
        from realize_core.activity.logger import log_event

        log_event(
            venture_key=key,
            actor_type="user",
            actor_id="dashboard",
            action="venture_created",
            entity_type="venture",
            entity_id=key,
        )
    except Exception as exc:
        logger.debug("Activity log failed for venture_created: %s", exc)

    return {"status": "created", "key": key, "name": name or key}


@router.delete("/ventures/{venture_key}")
async def delete_venture(venture_key: str, request: Request):
    """Delete a venture and its FABRIC directories."""
    systems: dict = visible_systems(request)
    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    from realize_core.scaffold import delete_venture as _delete

    try:
        result = _delete(str(kb_path), venture_key, confirm_name=venture_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        logger.warning("Venture delete '%s' failed, nothing changed: %s", venture_key, exc)
        raise HTTPException(status_code=503, detail=f"Could not delete venture; nothing was changed. {exc}") from exc

    _reload_systems(request, kb_path)

    return {"status": "deleted", "key": venture_key, "warnings": result.get("warnings", [])}


def _reload_systems(request: Request, kb_path: Path) -> None:
    """Reload realize-os.yaml into app state after a venture was added or removed."""
    from realize_core.config_runtime import reload_app_config

    reload_app_config(request.app.state, kb_path)


@router.get("/ventures/{venture_key}/export")
@router.post("/ventures/{venture_key}/export")
async def export_venture(venture_key: str, request: Request):
    """Export a venture as a zip file.

    GET supports browser download buttons; POST is kept for existing API clients.
    """
    systems: dict = visible_systems(request)
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    import tempfile

    from realize_core.plugins.venture_io import export_venture as _export

    export_dir = Path(tempfile.mkdtemp())
    output_path = export_dir / f"{venture_key}.zip"
    zip_path = _export(
        venture_key=venture_key,
        kb_path=kb_path,
        output_path=output_path,
        sys_conf=systems[venture_key],
    )

    if not zip_path or not zip_path.exists():
        raise HTTPException(status_code=500, detail="Export failed")

    from fastapi.responses import FileResponse

    return FileResponse(
        path=str(zip_path),
        filename=f"{venture_key}.zip",
        media_type="application/zip",
    )
