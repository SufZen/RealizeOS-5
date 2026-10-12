"""
Workflows API routes — skill and workflow CRUD.

Endpoints:
- GET    /api/workflows                   — list all workflows/skills
- GET    /api/workflows/{skill_name}      — get workflow/skill details
- POST   /api/workflows                   — create a new workflow/skill
- PUT    /api/workflows/{skill_name}      — update a workflow/skill
- DELETE /api/workflows/{skill_name}      — delete a workflow/skill
- POST   /api/workflows/{skill_name}/test — dry-run a workflow with test input
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from realize_api.dependencies import get_allowed_ventures, visible_to

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class CreateWorkflowBody(BaseModel):
    """Body for creating a new workflow/skill.

    Unknown fields are refused and a workflow needs at least one step
    (Codex audit F06): an editor-shaped body (``content``, ``format``,
    ``venture_key``) used to be accepted and stored as an empty workflow.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    system_key: str = ""
    triggers: list[str] = Field(default_factory=list)
    steps: list[dict] = Field(min_length=1)
    version: int = 2


class UpdateWorkflowBody(BaseModel):
    """Body for updating a workflow/skill (unknown fields refused; steps, if given, not empty)."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    triggers: list[str] | None = None
    steps: list[dict] | None = Field(default=None, min_length=1)
    enabled: bool | None = None


class TestWorkflowBody(BaseModel):
    """Body for testing a workflow with sample input."""

    input_text: str
    system_key: str = "test"
    user_id: str = "test-user"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/workflows")
async def list_workflows(
    request: Request,
    system_key: str | None = None,
):
    """
    List all registered workflows and skills.

    Query params:
    - system_key: filter by system (optional)
    """
    all_skills: list[dict] = []
    global_owners: frozenset[str] = frozenset()
    try:
        from realize_core.skills.detector import GLOBAL_SKILL_OWNERS, get_all_skills

        all_skills, global_owners = get_all_skills(), GLOBAL_SKILL_OWNERS
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Failed to load skills: %s", exc)

    # system_key is each skill's owner (the venture it was loaded under).
    all_skills = [s for s in all_skills if s["system_key"] in global_owners or visible_to(request, s["system_key"])]

    # Filter by system_key if provided
    if system_key:
        all_skills = [
            s
            for s in all_skills
            if s.get("system_key", "") == system_key or not s.get("system_key")  # global skills match any
        ]

    return {
        "workflows": [
            {
                "name": s.get("name", ""),
                "description": s.get("description", ""),
                "triggers": s.get("triggers", []),
                "version": s.get("_version", 1),
                "system_key": s.get("system_key", ""),
                "enabled": s.get("enabled", True),
                "steps_count": len(s.get("steps", [])),
            }
            for s in all_skills
        ],
        "total": len(all_skills),
    }


@router.get("/workflows/{skill_name}")
async def get_workflow(skill_name: str, request: Request):
    """Get detailed info about a specific workflow/skill."""
    try:
        from realize_core.skills.detector import GLOBAL_SKILL_OWNERS, find_skill

        found = find_skill(skill_name)
    except ImportError:
        raise HTTPException(status_code=501, detail="Skills module not available")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Same rule as the list: global skills, or skills owned by a venture the caller may see.
    owner, skill = found if found else ("", None)
    if not skill or not (owner in GLOBAL_SKILL_OWNERS or visible_to(request, owner)):
        raise HTTPException(status_code=404, detail=f"Workflow '{skill_name}' not found")

    return {
        "name": skill.get("name", ""),
        "description": skill.get("description", ""),
        "triggers": skill.get("triggers", []),
        "version": skill.get("_version", 1),
        "system_key": skill.get("system_key", owner),
        "enabled": skill.get("enabled", True),
        "steps": skill.get("steps", []),
        "output_template": skill.get("output_template", ""),
    }


@router.post("/workflows", status_code=201)
async def create_workflow(body: CreateWorkflowBody, request: Request):
    """Create a new workflow/skill definition."""
    # A venture-limited caller creates skills in their ventures, never global ones.
    if get_allowed_ventures(request) is not None and not visible_to(request, body.system_key):
        raise HTTPException(status_code=403, detail="Create the workflow in one of your ventures")
    try:
        from realize_core.skills.detector import get_skill_by_name, register_skill
    except ImportError:
        raise HTTPException(status_code=501, detail="Skills module not available")

    # Check for duplicates
    existing = get_skill_by_name(body.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Workflow '{body.name}' already exists",
        )

    skill_data = {
        "name": body.name,
        "description": body.description,
        "system_key": body.system_key,
        "triggers": body.triggers,
        "steps": body.steps,
        "_version": body.version,
        "enabled": True,
    }

    register_skill(skill_data)
    logger.info("Created workflow '%s' via API", body.name)

    return {
        "name": body.name,
        "status": "created",
    }


@router.put("/workflows/{skill_name}")
async def update_workflow(skill_name: str, body: UpdateWorkflowBody, request: Request):
    """Update an existing workflow/skill."""
    try:
        from realize_core.skills.detector import get_skill_by_name, update_skill
    except ImportError:
        raise HTTPException(status_code=501, detail="Skills module not available")

    existing = get_skill_by_name(skill_name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Workflow '{skill_name}' not found")

    updates = body.model_dump(exclude_unset=True)
    update_skill(skill_name, updates)

    logger.info("Updated workflow '%s' via API", skill_name)
    return {"name": skill_name, "status": "updated", "changes": list(updates.keys())}


@router.delete("/workflows/{skill_name}")
async def delete_workflow(skill_name: str, request: Request):
    """Delete a workflow/skill."""
    try:
        from realize_core.skills.detector import get_skill_by_name, unregister_skill
    except ImportError:
        raise HTTPException(status_code=501, detail="Skills module not available")

    existing = get_skill_by_name(skill_name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Workflow '{skill_name}' not found")

    unregister_skill(skill_name)
    logger.info("Deleted workflow '%s' via API", skill_name)
    return {"name": skill_name, "status": "deleted"}


@router.post("/workflows/{skill_name}/test")
async def test_workflow(skill_name: str, body: TestWorkflowBody, request: Request):
    """
    Dry-run a workflow with test input.

    Returns the skill detection result and (if triggered) the output.
    """
    try:
        from realize_core.skills.detector import detect_skill
    except ImportError:
        raise HTTPException(status_code=501, detail="Skills module not available")

    skill = detect_skill(body.input_text, body.system_key)

    if not skill:
        return {
            "triggered": False,
            "message": f"Input did not trigger any skill for system '{body.system_key}'",
        }

    if skill.get("name") != skill_name:
        return {
            "triggered": False,
            "message": f"Input triggered '{skill.get('name')}' instead of '{skill_name}'",
            "triggered_skill": skill.get("name"),
        }

    return {
        "triggered": True,
        "skill_name": skill.get("name"),
        "version": skill.get("_version", 1),
        "message": "Skill would be triggered by this input",
    }
