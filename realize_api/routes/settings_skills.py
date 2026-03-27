"""
Skill Library and Installation API.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)


class InstallSkillRequest(BaseModel):
    skill_id: str = Field(..., description="ID of the skill to install")
    venture_key: str = Field(..., description="Venture to install the skill into")


@router.get("/skills/library")
async def get_skill_library():
    """Get all available skill templates from the library."""
    from realize_core.skills.library import get_categories, get_library

    return {"skills": get_library(), "categories": get_categories()}


@router.get("/skills/library/{skill_id}")
async def get_skill_detail(skill_id: str):
    """Get a specific skill template with full YAML content."""
    from realize_core.skills.library import get_skill_template

    template = get_skill_template(skill_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    return template


@router.post("/skills/install")
async def install_skill(body: InstallSkillRequest, request: Request):
    """Install a skill template to a venture."""
    skill_id = body.skill_id
    venture_key = body.venture_key

    systems = getattr(request.app.state, "systems", {})
    kb_path = getattr(request.app.state, "kb_path", Path("."))

    if venture_key not in systems:
        raise HTTPException(status_code=404, detail=f"Venture '{venture_key}' not found")

    from realize_core.skills.library import install_skill as _install

    result = _install(skill_id, kb_path, systems[venture_key])

    if not result.get("installed"):
        raise HTTPException(status_code=409, detail=result.get("error", "Install failed"))

    return result
