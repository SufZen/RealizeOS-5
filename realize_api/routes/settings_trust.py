"""
Trust Matrix and Level Update API routes.
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class TrustLevelUpdate(BaseModel):
    level: int


@router.get("/trust")
async def get_trust_matrix(request: Request):
    """Get the full trust matrix with current level and all action rules.

    With ``features.packs`` on, ``ventures`` adds each visible venture's
    effective decisions at the current level: per action, the ladder's
    decision, the effective one and the pack or firm default that tightened
    it, plus the defaults that were ignored because they would loosen it
    (spec 010: packs only tighten trust). With the flag off the response is
    unchanged.
    """
    config = getattr(request.app.state, "config", None) or {}
    from realize_core.governance.trust_ladder import get_trust_matrix

    matrix = get_trust_matrix(config)
    from realize_core.config import get_features

    if get_features(config).get("packs"):
        matrix["ventures"] = _venture_matrices(request, config)
    return matrix


def _venture_matrices(request: Request, config: dict) -> dict[str, dict]:
    """Each visible venture's effective trust decisions (``features.packs`` on)."""
    from pathlib import Path

    from realize_core.packs.loader import LOAD_ERRORS
    from realize_core.packs.trust import venture_trust_matrix

    from realize_api.dependencies import visible_systems

    kb_path = getattr(request.app.state, "kb_path", None)
    if kb_path is None:
        return {}
    out: dict[str, dict] = {}
    for key, system in sorted(visible_systems(request).items()):
        venture_dir = Path(kb_path) / str(system.get("system_dir") or f"systems/{key}")
        if not venture_dir.is_dir():
            continue
        try:
            out[key] = {"name": system.get("name", key), **venture_trust_matrix(config, venture_dir)}
        except LOAD_ERRORS as exc:
            logger.warning("Trust matrix for venture %s skipped (%s: %s)", key, type(exc).__name__, exc)
    return out


@router.put("/trust/level")
async def update_trust_level(body: TrustLevelUpdate, request: Request):
    """Update the system trust level (1-5)."""
    level = body.level
    if not (1 <= level <= 5):
        raise HTTPException(status_code=400, detail="Trust level must be between 1 and 5")

    config_path = os.getenv("REALIZE_CONFIG", "realize-os.yaml")

    from realize_core.governance.trust_ladder import set_trust_level

    success = set_trust_level(config_path, level)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update trust level")

    # Reload config
    from realize_core.config_runtime import reload_app_config

    reload_app_config(request.app.state)

    return {"status": "updated", "level": level}
