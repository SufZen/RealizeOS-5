"""
FABRIC REST API routes.

Exposes the FABRIC knowledge system as REST endpoints:
- Entity CRUD: list, get, create, update, delete
- Synapse queries: search, TOC, graph queries
- Schema validation: lint entities
- Runtime status: list runtimes, health checks
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Request Models ───────────────────────────────────────────────────────────

class CreateEntityRequest(BaseModel):
    entity_type: str
    title: str
    body: str = ""
    frontmatter: dict = {}
    venture: str = ""
    layer: str = ""


class UpdateEntityRequest(BaseModel):
    updates: dict = {}
    body: str | None = None
    modified_by: str = ""


# ─── FABRIC Entity CRUD ──────────────────────────────────────────────────────

@router.get("/fabric/entities")
async def list_entities(
    request: Request,
    venture: str = "",
    entity_type: str = "",
    tag: str = "",
):
    """List FABRIC entities with optional filters."""
    synapse = _get_synapse(request)

    if tag:
        entities = synapse.by_tag(tag, scope=venture or None)
    elif entity_type:
        entities = synapse.by_type(entity_type, scope=venture or None)
    else:
        entities = synapse.toc(venture=venture or None)

    return {"entities": entities, "count": len(entities)}


@router.get("/fabric/entities/{entity_id}")
async def get_entity(entity_id: str, request: Request, depth: int = 0):
    """Get a single entity by ID, optionally with neighbors."""
    synapse = _get_synapse(request)
    entity = synapse.get(entity_id, depth=depth)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return {"entity": entity}


@router.post("/fabric/entities")
async def create_entity(body: CreateEntityRequest, request: Request):
    """Create a new FABRIC entity."""
    from realize_core.fabric.crud import create_entity as _create

    venture_dir = _resolve_venture_dir(request, body.venture)
    if not venture_dir:
        raise HTTPException(status_code=400, detail="No venture directory found")

    try:
        entity = _create(
            venture_dir=venture_dir,
            entity_type=body.entity_type,
            title=body.title,
            body=body.body,
            frontmatter=body.frontmatter,
            layer=body.layer,
            venture=body.venture,
        )

        # Re-index the new entity
        synapse = _get_synapse(request)
        synapse.index_entity(entity)

        return {
            "status": "created",
            "entity_id": entity.id,
            "path": str(entity.path),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/fabric/entities/{entity_id}")
async def update_entity(entity_id: str, body: UpdateEntityRequest, request: Request):
    """Update an existing FABRIC entity."""
    from realize_core.fabric.crud import read_entity, update_entity as _update

    synapse = _get_synapse(request)
    entity_data = synapse.get(entity_id)
    if entity_data is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    entity_path = Path(entity_data.get("path", ""))
    if not entity_path.exists():
        raise HTTPException(status_code=404, detail="Entity file not found on disk")

    try:
        entity = read_entity(entity_path)
        updated = _update(
            entity,
            updates=body.updates,
            body=body.body,
            modified_by=body.modified_by,
        )

        synapse.index_entity(updated)

        return {"status": "updated", "entity_id": updated.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/fabric/entities/{entity_id}")
async def delete_entity(entity_id: str, request: Request):
    """Delete a FABRIC entity."""
    from realize_core.fabric.crud import read_entity, delete_entity as _delete

    synapse = _get_synapse(request)
    entity_data = synapse.get(entity_id)
    if entity_data is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    entity_path = Path(entity_data.get("path", ""))
    if not entity_path.exists():
        raise HTTPException(status_code=404, detail="Entity file not found on disk")

    try:
        entity = read_entity(entity_path)
        result = _delete(entity)

        if result:
            synapse.remove_entity(entity_id)
            return {"status": "deleted", "entity_id": entity_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete entity")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Synapse Search & Queries ────────────────────────────────────────────────

@router.get("/fabric/search")
async def search_entities(
    request: Request,
    q: str = "",
    venture: str = "",
    entity_type: str = "",
    n: int = 10,
):
    """Search entities using full-text search."""
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    synapse = _get_synapse(request)
    results = synapse.search(
        query=q,
        scope=venture or None,
        entity_type=entity_type or None,
        n=n,
    )
    return {"results": results, "count": len(results), "query": q}


@router.get("/fabric/toc")
async def get_toc(request: Request, venture: str = ""):
    """Get the L1 Table of Contents — always loaded into agent context."""
    synapse = _get_synapse(request)
    toc = synapse.toc(venture=venture or None)
    return {"toc": toc, "count": len(toc)}


@router.get("/fabric/recent")
async def get_recent(request: Request, venture: str = "", n: int = 10):
    """Get recently modified entities."""
    synapse = _get_synapse(request)
    recent = synapse.recent(scope=venture or None, n=n)
    return {"entities": recent, "count": len(recent)}


@router.get("/fabric/orphans")
async def get_orphans(request: Request, venture: str = ""):
    """Get entities with zero inbound references."""
    synapse = _get_synapse(request)
    orphans = synapse.orphans(scope=venture or None)
    return {"entities": orphans, "count": len(orphans)}


@router.get("/fabric/stats")
async def get_stats(request: Request, venture: str = ""):
    """Get index statistics."""
    synapse = _get_synapse(request)
    stats = synapse.stats(venture=venture or None)
    return {"stats": stats}


# ─── Validation ───────────────────────────────────────────────────────────────

@router.post("/fabric/lint")
async def lint_entities(request: Request, venture: str = ""):
    """Validate all entities against their schemas."""
    from realize_core.fabric.crud import scan_venture
    from realize_core.fabric.validator import SchemaRegistry, validate_entity

    venture_dir = _resolve_venture_dir(request, venture)
    if not venture_dir:
        raise HTTPException(status_code=400, detail="No venture directory found")

    registry = SchemaRegistry()
    entities = scan_venture(venture_dir, venture=venture)

    warnings = []
    for entity in entities:
        result = validate_entity(
            entity.frontmatter,
            entity_type=entity.type,
            entity_id=entity.id,
            registry=registry,
        )
        if result.warnings:
            warnings.extend([str(w) for w in result.warnings])

    return {
        "entities_scanned": len(entities),
        "warnings_count": len(warnings),
        "warnings": warnings,
    }


# ─── Runtime Status ──────────────────────────────────────────────────────────

@router.get("/fabric/runtimes")
async def list_runtimes(request: Request):
    """List all registered agent runtimes."""
    registry = _get_runtime_registry(request)
    if registry is None:
        return {"runtimes": [], "message": "Runtime registry not initialized"}
    return {"runtimes": registry.status_summary()}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_synapse(request: Request):
    """Get or create the Synapse instance."""
    if not hasattr(request.app.state, "synapse") or request.app.state.synapse is None:
        from realize_core.fabric.synapse import Synapse
        from realize_core.config import KB_PATH

        db_path = Path(KB_PATH) / ".synapse" / "synapse.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        request.app.state.synapse = Synapse(db_path=db_path)

    return request.app.state.synapse


def _get_runtime_registry(request: Request):
    """Get the runtime registry if initialized."""
    return getattr(request.app.state, "runtime_registry", None)


def _resolve_venture_dir(request: Request, venture: str) -> Path | None:
    """Resolve a venture key to its directory on disk."""
    from realize_core.config import KB_PATH

    if not venture:
        return None

    # Try systems/ directory first (v5.5.0 path)
    systems_path = Path(KB_PATH) / "systems" / venture
    if systems_path.exists():
        return systems_path

    # Fallback to ventures/ (legacy path)
    ventures_path = Path(KB_PATH) / "ventures" / venture
    if ventures_path.exists():
        return ventures_path

    # Create new venture directory in systems/
    systems_path.mkdir(parents=True, exist_ok=True)
    for layer_dir in ["F-foundations", "A-agents", "B-brain", "R-routines", "I-insights", "C-creations"]:
        (systems_path / layer_dir).mkdir(exist_ok=True)
    return systems_path
