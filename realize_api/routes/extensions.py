"""
Extensions API routes — manage RealizeOS extensions.

Endpoints:
- GET    /api/extensions                   — list all extensions
- GET    /api/extensions/{ext_key}         — get extension details
- POST   /api/extensions/{ext_key}/enable  — enable an extension
- POST   /api/extensions/{ext_key}/disable — disable an extension
- GET    /api/extensions/{ext_key}/status  — get extension runtime status
"""
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class ExtensionToggleBody(BaseModel):
    """Optional body for enable/disable with config."""
    config: dict | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/extensions")
async def list_extensions(
    request: Request,
    enabled_only: bool = False,
):
    """
    List all registered extensions.

    Query params:
    - enabled_only: if true, only return enabled extensions
    """
    try:
        from realize_core.extensions.registry import list_extensions as _list_ext
        extensions = _list_ext()
    except ImportError:
        # Extensions module may not be implemented yet (Agent 4)
        extensions = []
    except Exception as exc:
        logger.warning("Failed to list extensions: %s", exc)
        extensions = []

    if enabled_only:
        extensions = [e for e in extensions if e.get("enabled", False)]

    return {
        "extensions": [
            {
                "key": e.get("key", ""),
                "name": e.get("name", ""),
                "description": e.get("description", ""),
                "version": e.get("version", "0.0.0"),
                "enabled": e.get("enabled", False),
                "category": e.get("category", "general"),
                "provides_tools": e.get("provides_tools", []),
            }
            for e in extensions
        ],
        "total": len(extensions),
        "enabled_count": sum(1 for e in extensions if e.get("enabled", False)),
    }


@router.get("/extensions/{ext_key}")
async def get_extension(ext_key: str, request: Request):
    """Get detailed info about a specific extension."""
    try:
        from realize_core.extensions.registry import get_extension as _get_ext
        ext = _get_ext(ext_key)
    except ImportError:
        raise HTTPException(status_code=501, detail="Extensions module not available")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not ext:
        raise HTTPException(status_code=404, detail=f"Extension '{ext_key}' not found")

    return {
        "key": ext.get("key", ""),
        "name": ext.get("name", ""),
        "description": ext.get("description", ""),
        "version": ext.get("version", "0.0.0"),
        "enabled": ext.get("enabled", False),
        "category": ext.get("category", "general"),
        "provides_tools": ext.get("provides_tools", []),
        "config": ext.get("config", {}),
        "dependencies": ext.get("dependencies", []),
    }


@router.post("/extensions/{ext_key}/enable")
async def enable_extension(
    ext_key: str,
    request: Request,
    body: ExtensionToggleBody | None = None,
):
    """Enable an extension, optionally with config."""
    try:
        from realize_core.extensions.registry import enable_extension as _enable
    except ImportError:
        raise HTTPException(status_code=501, detail="Extensions module not available")

    config = body.config if body else None
    try:
        _enable(ext_key, config=config)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Extension '{ext_key}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info("Enabled extension '%s' via API", ext_key)
    return {"key": ext_key, "status": "enabled"}


@router.post("/extensions/{ext_key}/disable")
async def disable_extension(ext_key: str, request: Request):
    """Disable an extension."""
    try:
        from realize_core.extensions.registry import disable_extension as _disable
    except ImportError:
        raise HTTPException(status_code=501, detail="Extensions module not available")

    try:
        _disable(ext_key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Extension '{ext_key}' not found")

    logger.info("Disabled extension '%s' via API", ext_key)
    return {"key": ext_key, "status": "disabled"}


@router.get("/extensions/{ext_key}/status")
async def get_extension_status(ext_key: str, request: Request):
    """Get the runtime status of an extension."""
    try:
        from realize_core.extensions.registry import (
            get_extension as _get_ext,
        )
        from realize_core.extensions.registry import (
            get_extension_status as _get_status,
        )
    except ImportError:
        raise HTTPException(status_code=501, detail="Extensions module not available")

    ext = _get_ext(ext_key)
    if not ext:
        raise HTTPException(status_code=404, detail=f"Extension '{ext_key}' not found")

    try:
        status = _get_status(ext_key)
    except Exception as exc:
        status = {"status": "unknown", "error": str(exc)}

    return {
        "key": ext_key,
        "enabled": ext.get("enabled", False),
        **status,
    }
