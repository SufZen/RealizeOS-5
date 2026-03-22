"""
Venture API routes — detailed venture data for the dashboard.

Endpoints:
- GET /api/ventures — list with health summary
- GET /api/ventures/{key} — detail with FABRIC analysis, agents, skills
- GET /api/ventures/{key}/agents — agent list with current states
- GET /api/ventures/{key}/skills — skill list with execution stats
"""
import logging
from datetime import UTC
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/ventures")
async def list_ventures(request: Request):
    """List all ventures with health summary."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    ventures = []
    for key, sys_conf in systems.items():
        fabric = _analyze_fabric(kb_path, sys_conf)
        ventures.append({
            "key": key,
            "name": sys_conf.get("name", key),
            "description": sys_conf.get("description", ""),
            "agent_count": len(sys_conf.get("agents", {})),
            "skill_count": _count_skills(kb_path, sys_conf),
            "fabric_completeness": fabric["completeness"],
        })

    return {"ventures": ventures}


@router.get("/ventures/{venture_key}")
async def get_venture_detail(venture_key: str, request: Request):
    """Get detailed venture information including FABRIC analysis."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    sys_conf = systems[venture_key]
    fabric = _analyze_fabric(kb_path, sys_conf)
    agents = _get_agents_with_status(sys_conf, venture_key)
    skills = _get_skills(kb_path, sys_conf)

    return {
        "key": venture_key,
        "name": sys_conf.get("name", venture_key),
        "description": sys_conf.get("description", ""),
        "fabric": fabric,
        "agents": agents,
        "skills": skills,
    }


@router.get("/ventures/{venture_key}/agents")
async def list_venture_agents(venture_key: str, request: Request):
    """List agents for a venture with current status from DB."""
    systems: dict = getattr(request.app.state, "systems", {})

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    sys_conf = systems[venture_key]
    agents = _get_agents_with_status(sys_conf, venture_key)

    return {"agents": agents, "venture_key": venture_key}


@router.get("/ventures/{venture_key}/skills")
async def list_venture_skills(venture_key: str, request: Request):
    """List skills for a venture with execution stats."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    sys_conf = systems[venture_key]
    skills = _get_skills(kb_path, sys_conf)

    return {"skills": skills, "venture_key": venture_key}


@router.get("/ventures/{venture_key}/org-tree")
async def get_org_tree(venture_key: str, request: Request):
    """Get the agent hierarchy / org tree for a venture."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    from realize_core.scheduler.hierarchy import build_org_tree
    tree = build_org_tree(kb_path, systems[venture_key])
    return {"venture_key": venture_key, **tree}


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
        except Exception:
            pass

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
    except Exception:
        pass

    # Recent activity for this agent
    recent_activity = []
    try:
        from realize_core.activity.store import query_events
        recent_activity = query_events(venture_key=venture_key, actor_id=agent_key, limit=20)
    except Exception:
        pass

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
            venture_key=venture_key, actor_type="user", actor_id="dashboard",
            action="agent_paused", entity_type="agent", entity_id=agent_key,
        )
    except Exception:
        pass

    return {"status": "paused", "agent_key": agent_key, "venture_key": venture_key}


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
            venture_key=venture_key, actor_type="user", actor_id="dashboard",
            action="agent_resumed", entity_type="agent", entity_id=agent_key,
        )
    except Exception:
        pass

    return {"status": "idle", "agent_key": agent_key, "venture_key": venture_key}


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
            next_run = (datetime.now(UTC) + timedelta(seconds=int(interval))).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )

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
    except Exception:
        pass

    try:
        from realize_core.activity.logger import log_event
        log_event(
            venture_key=venture_key, actor_type="user", actor_id="dashboard",
            action="schedule_updated", entity_type="agent", entity_id=agent_key,
            details=f'{{"cron": "{cron or ""}", "interval_sec": {interval or 0}}}',
        )
    except Exception:
        pass

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
    except Exception:
        pass

    return {"agent_key": agent_key, "venture_key": venture_key, "schedule": None}


# ---------------------------------------------------------------------------
# Venture CRUD
# ---------------------------------------------------------------------------

@router.post("/ventures")
async def create_venture(request: Request):
    """Create a new venture with FABRIC scaffolding."""
    body = await request.json()
    key = body.get("key", "").strip()
    name = body.get("name", "").strip()
    description = body.get("description", "").strip()

    if not key:
        raise HTTPException(status_code=400, detail="Venture key is required")
    if len(key) > 50:
        raise HTTPException(status_code=400, detail="Key must be 50 characters or less")
    if not key.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Key must be alphanumeric (hyphens and underscores allowed)")

    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    from realize_core.scaffold import scaffold_venture
    result = scaffold_venture(str(kb_path), key, name=name, description=description)

    if not result.get("created"):
        raise HTTPException(status_code=409, detail=result.get("error", "Venture already exists"))

    # Reload config to pick up the new venture
    from realize_core.config import build_systems_dict, load_config
    config = load_config()
    request.app.state.config = config
    request.app.state.systems = build_systems_dict(config)

    try:
        from realize_core.activity.logger import log_event
        log_event(
            venture_key=key, actor_type="user", actor_id="dashboard",
            action="venture_created", entity_type="venture", entity_id=key,
        )
    except Exception:
        pass

    return {"status": "created", "key": key, "name": name}


@router.delete("/ventures/{venture_key}")
async def delete_venture(venture_key: str, request: Request):
    """Delete a venture and its FABRIC directories."""
    systems: dict = getattr(request.app.state, "systems", {})
    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    from realize_core.scaffold import delete_venture as _delete
    success = _delete(str(kb_path), venture_key, confirm_name=venture_key)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete venture")

    # Reload config
    from realize_core.config import build_systems_dict, load_config
    config = load_config()
    request.app.state.config = config
    request.app.state.systems = build_systems_dict(config)

    return {"status": "deleted", "key": venture_key}


@router.post("/ventures/{venture_key}/export")
async def export_venture(venture_key: str, request: Request):
    """Export a venture as a zip file."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    import tempfile

    from realize_core.plugins.venture_io import export_venture as _export

    export_dir = Path(tempfile.mkdtemp())
    zip_path = _export(kb_path, systems[venture_key], venture_key, export_dir)

    if not zip_path or not zip_path.exists():
        raise HTTPException(status_code=500, detail="Export failed")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(zip_path),
        filename=f"{venture_key}.zip",
        media_type="application/zip",
    )


# ---------------------------------------------------------------------------
# Knowledge Base Browser
# ---------------------------------------------------------------------------

@router.get("/ventures/{venture_key}/kb/files")
async def list_kb_files(venture_key: str, request: Request):
    """List FABRIC directory structure with files."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    sys_conf = systems[venture_key]
    fabric_dirs = {
        "F-foundations": sys_conf.get("foundations", ""),
        "A-agents": sys_conf.get("agents_dir", ""),
        "B-brain": sys_conf.get("brain_dir", ""),
        "R-routines": sys_conf.get("routines_dir", ""),
        "I-insights": sys_conf.get("insights_dir", ""),
        "C-creations": sys_conf.get("creations_dir", ""),
    }

    tree = {}
    for label, rel_path in fabric_dirs.items():
        if not rel_path:
            tree[label] = {"exists": False, "files": []}
            continue
        full_path = kb_path / rel_path
        if not full_path.exists():
            tree[label] = {"exists": False, "files": []}
            continue

        files = []
        for f in sorted(full_path.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                files.append({
                    "name": f.name,
                    "relative_path": str(f.relative_to(kb_path)),
                    "size": f.stat().st_size,
                })
        tree[label] = {"exists": True, "files": files}

    return {"venture_key": venture_key, "tree": tree}


@router.get("/ventures/{venture_key}/kb/file")
async def read_kb_file(venture_key: str, path: str, request: Request):
    """Read a specific KB file content."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path_root: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    # Security: prevent path traversal
    if ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path = kb_path_root / path
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Ensure file is within kb_path
    try:
        file_path.resolve().relative_to(kb_path_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(status_code=500, detail="Cannot read file")

    return {"path": path, "content": content, "size": file_path.stat().st_size}


@router.get("/ventures/{venture_key}/kb/search")
async def search_kb(venture_key: str, q: str, request: Request):
    """Search the knowledge base."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query required")

    try:
        from realize_core.kb.indexer import semantic_search
        results = semantic_search(q.strip(), system_key=venture_key, top_k=10)
        return {"query": q, "results": results}
    except Exception as e:
        return {"query": q, "results": [], "error": str(e)}


@router.post("/ventures/{venture_key}/ingest")
async def ingest_content(venture_key: str, request: Request):
    """Ingest content from a URL or text into the venture's KB."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    body = await request.json()
    url = body.get("url", "").strip()
    text = body.get("text", "").strip()
    title = body.get("title", "").strip()
    category = body.get("category", "brain")

    from realize_core.ingestion.extractor import extract_from_text, extract_from_url, save_to_kb

    if url:
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
        extracted = await extract_from_url(url)
    elif text:
        extracted = extract_from_text(text, title=title)
    else:
        raise HTTPException(status_code=400, detail="Provide 'url' or 'text'")

    if extracted.get("error"):
        raise HTTPException(status_code=422, detail=extracted["error"])

    result = save_to_kb(
        content=extracted["content"],
        title=extracted.get("title", title or "Ingested Content"),
        kb_path=kb_path,
        system_config=systems[venture_key],
        source_url=url,
        category=category,
    )

    if not result.get("saved"):
        raise HTTPException(status_code=500, detail=result.get("error", "Save failed"))

    try:
        from realize_core.activity.logger import log_event
        log_event(
            venture_key=venture_key, actor_type="user", actor_id="dashboard",
            action="content_ingested", entity_type="kb_file", entity_id=result["path"],
            details=f'{{"source": "{url or "text"}", "chars": {extracted["char_count"]}}}',
        )
    except Exception:
        pass

    return {
        "status": "ingested",
        "title": extracted.get("title", ""),
        "char_count": extracted.get("char_count", 0),
        "saved_path": result["path"],
    }


@router.put("/ventures/{venture_key}/kb/file")
async def save_kb_file(venture_key: str, request: Request):
    """Save/update a KB file."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path_root: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    body = await request.json()
    path = body.get("path", "")
    content = body.get("content", "")

    if len(content) > 1_048_576:
        raise HTTPException(status_code=413, detail="File too large (max 1MB)")

    if not path or ".." in path or "\x00" in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path = kb_path_root / path
    try:
        file_path.resolve().relative_to(kb_path_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write failed: {e}")

    # Reload config if this was an agent file (auto-discovery)
    if "/A-agents/" in path or "\\A-agents\\" in path:
        try:
            from realize_core.config import build_systems_dict, load_config
            config = load_config()
            request.app.state.config = config
            request.app.state.systems = build_systems_dict(config)
        except Exception:
            pass

    return {"status": "saved", "path": path, "size": file_path.stat().st_size}


@router.post("/ventures/{venture_key}/kb/file")
async def create_kb_file(venture_key: str, request: Request):
    """Create a new KB file."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path_root: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    body = await request.json()
    path = body.get("path", "")
    content = body.get("content", "")

    if not path or ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path = kb_path_root / path
    try:
        file_path.resolve().relative_to(kb_path_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if file_path.exists():
        raise HTTPException(status_code=409, detail="File already exists")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Create failed: {e}")

    # Reload config if agent file
    if "/A-agents/" in path or "\\A-agents\\" in path:
        try:
            from realize_core.config import build_systems_dict, load_config
            config = load_config()
            request.app.state.config = config
            request.app.state.systems = build_systems_dict(config)
        except Exception:
            pass

    return {"status": "created", "path": path, "size": file_path.stat().st_size}


@router.delete("/ventures/{venture_key}/kb/file")
async def delete_kb_file(venture_key: str, path: str, request: Request):
    """Delete a KB file."""
    systems: dict = getattr(request.app.state, "systems", {})
    kb_path_root: Path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    if not path or ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path = kb_path_root / path
    try:
        file_path.resolve().relative_to(kb_path_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")

    # Reload config if agent file
    if "/A-agents/" in path or "\\A-agents\\" in path:
        try:
            from realize_core.config import build_systems_dict, load_config
            config = load_config()
            request.app.state.config = config
            request.app.state.systems = build_systems_dict(config)
        except Exception:
            pass

    return {"status": "deleted", "path": path}


# ---------------------------------------------------------------------------
# Shared files API
# ---------------------------------------------------------------------------

@router.get("/shared/files")
async def list_shared_files(request: Request):
    """List files in the shared directory."""
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))
    shared_dir = kb_path / "shared"

    if not shared_dir.exists():
        return {"files": []}

    files = []
    for f in sorted(shared_dir.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            files.append({
                "name": f.name,
                "relative_path": str(f.relative_to(kb_path)),
                "size": f.stat().st_size,
                "directory": str(f.parent.relative_to(shared_dir)) if f.parent != shared_dir else "",
            })
    return {"files": files}


@router.get("/shared/file")
async def read_shared_file(path: str, request: Request):
    """Read a shared file."""
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    if ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path = kb_path / path
    try:
        file_path.resolve().relative_to(kb_path.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    content = file_path.read_text(encoding="utf-8")
    return {"path": path, "content": content, "size": file_path.stat().st_size}


@router.put("/shared/file")
async def save_shared_file(request: Request):
    """Save a shared file."""
    kb_path: Path = getattr(request.app.state, "kb_path", Path("."))

    body = await request.json()
    path = body.get("path", "")
    content = body.get("content", "")

    if not path or ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path = kb_path / path
    try:
        file_path.resolve().relative_to(kb_path.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Write failed: {e}")

    return {"status": "saved", "path": path, "size": file_path.stat().st_size}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _analyze_fabric(kb_path: Path, sys_conf: dict) -> dict:
    """Analyze FABRIC directory completeness for a venture."""
    fabric_dirs = {
        "F-foundations": sys_conf.get("foundations", ""),
        "A-agents": sys_conf.get("agents_dir", ""),
        "B-brain": sys_conf.get("brain_dir", ""),
        "R-routines": sys_conf.get("routines_dir", ""),
        "I-insights": sys_conf.get("insights_dir", ""),
        "C-creations": sys_conf.get("creations_dir", ""),
    }

    analysis = {}
    present = 0
    for label, rel_path in fabric_dirs.items():
        full_path = kb_path / rel_path if rel_path else None
        exists = full_path is not None and full_path.exists()
        file_count = sum(1 for _ in full_path.glob("*") if _.is_file()) if exists else 0
        analysis[label] = {
            "exists": exists,
            "file_count": file_count,
        }
        if exists and file_count > 0:
            present += 1

    return {
        "directories": analysis,
        "completeness": round(present / 6 * 100),
    }


def _get_agents_with_status(sys_conf: dict, venture_key: str) -> list[dict]:
    """Get agent list with current status from DB."""
    agents = []
    for agent_key in sys_conf.get("agents", {}):
        agent_data = {
            "key": agent_key,
            "definition_path": sys_conf["agents"][agent_key],
            "status": "idle",
            "last_run_at": None,
            "last_error": None,
        }

        try:
            from realize_core.scheduler.lifecycle import get_agent_status
            state = get_agent_status(agent_key, venture_key)
            if state:
                agent_data["status"] = state["status"]
                agent_data["last_run_at"] = state.get("last_run_at")
                agent_data["last_error"] = state.get("last_error")
        except Exception:
            pass

        agents.append(agent_data)

    return agents


def _get_skills(kb_path: Path, sys_conf: dict) -> list[dict]:
    """Get skill list from YAML files."""
    routines_dir = sys_conf.get("routines_dir", "")
    if not routines_dir:
        return []

    skills_path = kb_path / routines_dir / "skills"
    if not skills_path.exists():
        return []

    skills = []
    try:
        import yaml
        for yaml_file in sorted(skills_path.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data and isinstance(data, dict):
                    skills.append({
                        "name": data.get("name", yaml_file.stem),
                        "version": "v2" if "steps" in data else "v1",
                        "triggers": data.get("triggers", []),
                        "task_type": data.get("task_type", "general"),
                    })
            except Exception:
                pass
    except ImportError:
        pass

    return skills


def _count_skills(kb_path: Path, sys_conf: dict) -> int:
    """Count YAML skill files."""
    routines_dir = sys_conf.get("routines_dir", "")
    if not routines_dir:
        return 0
    skills_path = kb_path / routines_dir / "skills"
    if not skills_path.exists():
        return 0
    return sum(1 for _ in skills_path.glob("*.yaml"))
