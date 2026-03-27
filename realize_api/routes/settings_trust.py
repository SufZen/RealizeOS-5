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
    """Get the full trust matrix with current level and all action rules."""
    config = getattr(request.app.state, "config", {})
    from realize_core.governance.trust_ladder import get_trust_matrix

    return get_trust_matrix(config)


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
    from realize_core.config import build_systems_dict, load_config

    new_config = load_config()
    request.app.state.config = new_config
    request.app.state.systems = build_systems_dict(new_config)

    return {"status": "updated", "level": level}
