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

    # Filter by system_key if provided (shared and global skills match any venture)
    if system_key:
        all_skills = [
            s for s in all_skills if s.get("system_key", "") == system_key or s.get("system_key", "") in global_owners
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


def _visible_skill(request: Request, skill_name: str, system_key: str | None) -> tuple[str, dict] | None:
    """The skill ``skill_name`` the caller may see, looked up for a venture.

    With ``system_key``: that venture's own skill, else a shared or global one
    (never another venture's), and only when the caller may see that venture.
    Without one: the first venture the caller may see that has the skill
    (each venture has its own copy, for example of a pack skill), else a
    shared or global skill.
    """
    from realize_core.skills.detector import GLOBAL_SKILL_OWNERS, find_shared_skill, find_skill, ventures_with_skill

    if system_key:
        if system_key not in GLOBAL_SKILL_OWNERS and not visible_to(request, system_key):
            return None
        return find_skill(skill_name, system_key)
    visible = [v for v in ventures_with_skill(skill_name) if visible_to(request, v)]
    return find_skill(skill_name, visible[0]) if visible else find_shared_skill(skill_name)


def _skill_to_change(skill_name: str, system_key: str | None) -> tuple[str, dict]:
    """The skill an edit or delete addresses: ``system_key``'s, else a shared or global one.

    Without ``system_key`` a venture's skill is never picked: each venture has
    its own copy (for example of a pack skill), so the caller names the venture.

    Raises:
        HTTPException: 404 when there is none; 409 when only ventures have a
            skill with that name and ``system_key`` doesn't say which.
    """
    from realize_core.skills.detector import find_skill, ventures_with_skill

    found = find_skill(skill_name, system_key or None)
    if not found and not system_key and ventures_with_skill(skill_name):
        raise HTTPException(
            status_code=409, detail=f"Workflow '{skill_name}' belongs to a venture; add ?system_key=<venture>"
        )
    if not found:
        raise HTTPException(status_code=404, detail=f"Workflow '{skill_name}' not found")
    return found


@router.get("/workflows/{skill_name}")
async def get_workflow(skill_name: str, request: Request, system_key: str | None = None):
    """Get detailed info about a specific workflow/skill.

    Query params:
    - system_key: the venture whose skill to show (two ventures can each have
      a skill with the same name). Default: the first venture the caller may
      see that has it, else a shared or global skill.
    """
    try:
        found = _visible_skill(request, skill_name, system_key)
    except ImportError:
        raise HTTPException(status_code=501, detail="Skills module not available")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    owner, skill = found if found else ("", None)
    if not skill:
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
        from realize_core.skills.detector import find_shared_skill, find_skill, register_skill, ventures_with_skill
    except ImportError:
        raise HTTPException(status_code=501, detail="Skills module not available")

    # Check for duplicates: in the venture (its own or a shared skill), or anywhere for a global one.
    if body.system_key:
        existing = find_skill(body.name, body.system_key)
    else:
        existing = ventures_with_skill(body.name) or find_shared_skill(body.name)
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
async def update_workflow(skill_name: str, body: UpdateWorkflowBody, request: Request, system_key: str | None = None):
    """Update an existing workflow/skill.

    Query params:
    - system_key: the venture whose skill to change; needed when several
      ventures have a skill with this name (409 otherwise).
    """
    try:
        from realize_core.skills.detector import update_skill
    except ImportError:
        raise HTTPException(status_code=501, detail="Skills module not available")

    owner, _skill = _skill_to_change(skill_name, system_key)
    updates = body.model_dump(exclude_unset=True)
    update_skill(skill_name, updates, system_key=owner)

    logger.info("Updated workflow '%s' (%s) via API", skill_name, owner)
    return {"name": skill_name, "status": "updated", "changes": list(updates.keys())}


@router.delete("/workflows/{skill_name}")
async def delete_workflow(skill_name: str, request: Request, system_key: str | None = None):
    """Delete a workflow/skill.

    Query params:
    - system_key: the venture whose skill to delete; needed when several
      ventures have a skill with this name (409 otherwise).
    """
    try:
        from realize_core.skills.detector import unregister_skill
    except ImportError:
        raise HTTPException(status_code=501, detail="Skills module not available")

    owner, _skill = _skill_to_change(skill_name, system_key)
    unregister_skill(skill_name, system_key=owner)
    logger.info("Deleted workflow '%s' (%s) via API", skill_name, owner)
    return {"name": skill_name, "status": "deleted"}


class RunWorkflowBody(BaseModel):
    """Run a venture's workflow (skill) with an input message."""

    model_config = ConfigDict(extra="forbid")

    system_key: str = Field(min_length=1, description="The venture whose copy of the workflow runs.")
    input_text: str = Field(min_length=1)


_RUN_ERROR_STATUS = {"MCP_VALIDATION": 422, "MCP_FORBIDDEN": 403, "MCP_NOT_FOUND": 404, "MCP_INTERNAL": 500}


@router.post("/workflows/{skill_name}/run")
async def run_workflow(skill_name: str, body: RunWorkflowBody, request: Request):
    """Run a workflow for one venture, the REST twin of the MCP ``run_workflow`` tool.

    The venture's own copy runs (else a shared or global one, never another
    venture's). Its tool steps go through the governance gate like any run.
    Outside agents can't call this over REST; they run workflows over MCP,
    where a person approves first.
    """
    from realize_core.mcp_server.tools.ops_tools import _run_skill

    from realize_api.dependencies import get_current_user

    user = await get_current_user(request)
    args = {"name": skill_name, "input_text": body.input_text, "system_key": body.system_key}
    result = await _run_skill(args, request.app.state, user, channel="api")
    if isinstance(result, dict) and result.get("code"):
        status = _RUN_ERROR_STATUS.get(result["code"], 400)
        if "not found" in str(result.get("error", "")).lower():
            status = 404
        raise HTTPException(status_code=status, detail=result.get("error") or "Workflow run failed")
    return result


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
