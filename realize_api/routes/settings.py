"""
Settings API routes — core feature flags, governance gates, and system info.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)


class FeatureUpdateRequest(BaseModel):
    features: dict[str, bool] = Field(..., description="Dictionary of feature flags to update")

class GateUpdateRequest(BaseModel):
    gates: dict[str, Any] = Field(..., description="Dictionary of governance gates to update")


@router.get("/settings")
async def get_settings(request: Request):
    """Get current settings: features, gates, providers, system info."""
    config = getattr(request.app.state, "config", {})
    features = config.get("features", {})
    governance = config.get("governance", {})
    gates = governance.get("gates", {})

    # LLM providers
    providers = []
    try:
        from realize_core.llm.registry import get_registry

        registry = get_registry()
        for name, provider in registry._providers.items():
            providers.append(
                {
                    "name": name,
                    "available": provider.is_available(),
                    "models": provider.list_models() if provider.is_available() else [],
                }
            )
    except Exception as exc:
        logger.debug("LLM registry lookup failed: %s", exc)

    # System info
    v = sys.version_info
    data_path = Path(os.getenv("DATA_PATH", "./data"))
    db_size = 0
    try:
        db_file = data_path / "realize_ops.db"
        if db_file.exists():
            db_size = db_file.stat().st_size
    except Exception as exc:
        logger.debug("DB size check failed: %s", exc)

    kb_path = getattr(request.app.state, "kb_path", Path("."))
    kb_file_count = 0
    try:
        kb_file_count = sum(1 for _ in kb_path.rglob("*.md") if _.is_file())
    except Exception as exc:
        logger.debug("KB file count failed: %s", exc)

    return {
        "features": features,
        "gates": gates,
        "providers": providers,
        "system_info": {
            "python_version": f"{v.major}.{v.minor}.{v.micro}",
            "db_size_bytes": db_size,
            "kb_file_count": kb_file_count,
            "config_path": str(Path(os.getenv("REALIZE_CONFIG", "realize-os.yaml")).resolve()),
        },
    }


@router.put("/settings/features")
async def update_features(body_req: FeatureUpdateRequest, request: Request):
    """Update feature flags in realize-os.yaml."""
    config_path = Path(os.getenv("REALIZE_CONFIG", "realize-os.yaml"))
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Config file not found")

    try:
        import yaml

        # Read existing
        original_text = config_path.read_text(encoding="utf-8")
        config = yaml.safe_load(original_text)
        if not isinstance(config, dict):
            config = {}

        if "features" not in config:
            config["features"] = {}
        config["features"].update(body_req.features)

        # Validate YAML can round-trip before writing
        new_text = yaml.dump(config, default_flow_style=False, sort_keys=False)
        yaml.safe_load(new_text)  # Validate the output parses

        config_path.write_text(new_text, encoding="utf-8")

        # Reload in-memory config
        from realize_core.config import build_systems_dict, load_config

        new_config = load_config()
        request.app.state.config = new_config
        request.app.state.systems = build_systems_dict(new_config)

        return {"status": "updated", "features": config["features"]}
    except HTTPException:
        raise
    except Exception as e:
        # Rollback on failure
        try:
            config_path.write_text(original_text, encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to rollback config: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)[:200]}")


@router.put("/settings/gates")
async def update_gates(body_req: GateUpdateRequest, request: Request):
    """Update governance gates in realize-os.yaml."""
    config_path = Path(os.getenv("REALIZE_CONFIG", "realize-os.yaml"))
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Config file not found")

    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if "governance" not in config:
            config["governance"] = {}
        if "gates" not in config["governance"]:
            config["governance"]["gates"] = {}
        config["governance"]["gates"].update(body_req.gates)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        # Reload
        from realize_core.config import build_systems_dict, load_config

        new_config = load_config()
        request.app.state.config = new_config
        request.app.state.systems = build_systems_dict(new_config)

        return {"status": "updated", "gates": config["governance"]["gates"]}
    except Exception as e:
        logger.error("Failed to update gates: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save governance gates")


@router.post("/settings/reindex")
async def reindex_kb(request: Request):
    """Trigger a KB re-index."""
    kb_path = getattr(request.app.state, "kb_path", Path("."))
    try:
        from realize_core.kb.indexer import index_kb_files

        count = index_kb_files(str(kb_path), force=True)
        return {"status": "reindexed", "files_indexed": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
