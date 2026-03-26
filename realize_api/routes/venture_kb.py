"""
Venture Knowledge Base routes — KB file browser, search, and ingestion.

Endpoints:
- GET  /api/ventures/{key}/kb/files — FABRIC directory tree
- GET  /api/ventures/{key}/kb/file — read KB file content
- GET  /api/ventures/{key}/kb/search — search KB
- POST /api/ventures/{key}/ingest — ingest content from URL/text
- PUT  /api/ventures/{key}/kb/file — save/update KB file
- POST /api/ventures/{key}/kb/file — create KB file
- DELETE /api/ventures/{key}/kb/file — delete KB file
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
logger = logging.getLogger(__name__)


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
                files.append(
                    {
                        "name": f.name,
                        "relative_path": str(f.relative_to(kb_path)),
                        "size": f.stat().st_size,
                    }
                )
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
    except Exception as exc:
        logger.warning("Failed to read KB file %s: %s", file_path, exc)
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
            venture_key=venture_key,
            actor_type="user",
            actor_id="dashboard",
            action="content_ingested",
            entity_type="kb_file",
            entity_id=result["path"],
            details=f'{{"source": "{url or "text"}", "chars": {extracted["char_count"]}}}',
        )
    except Exception as exc:
        logger.debug("Activity log failed for content_ingested: %s", exc)

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
        except Exception as exc:
            logger.debug("Config reload after agent edit failed: %s", exc)


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
        except Exception as exc:
            logger.debug("Config reload after agent create failed: %s", exc)


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
        except Exception as exc:
            logger.debug("Config reload after agent delete failed: %s", exc)
