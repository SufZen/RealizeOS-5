"""
Agents V2 API routes — CRUD for V2 composable agents + pipeline management.

Endpoints:
- GET    /api/agents                      — list all agents across systems (``?venture=`` for one venture's team)
- GET    /api/agents/{agent_key}          — get agent details (V1 or V2)
- POST   /api/agents                      — create/register a V2 agent
- PUT    /api/agents/{agent_key}          — update a V2 agent definition
- DELETE /api/agents/{agent_key}          — unregister an agent
- POST   /api/agents/reload              — hot-reload agents from directories
- GET    /api/agents/personas             — list available persona bundles
- POST   /api/pipelines/execute           — execute a pipeline
- GET    /api/pipelines/{pipeline_id}     — get pipeline execution state

With ``features.packs`` on, a venture's effective team includes the agents of
its profession and market packs (and the firm's overrides). They are listed
with where they came from (``layer``, ``pack``, ``verification``) and are
read-only here: a pack is shared by every venture that links it, so changing
one means overriding it in the venture (its own ``A-agents/`` file wins).
"""

import logging
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from realize_core.agents.base import HandoffType, PipelineStage
from realize_core.agents.personas import list_personas, persona_keys
from realize_core.agents.registry import AgentRegistry
from realize_core.agents.schema import V1AgentDef, V2AgentDef

from realize_api.dependencies import get_allowed_ventures, visible_systems

#: Layer of an agent defined in a venture's own ``A-agents/`` folder.
VENTURE_LAYER = "venture"
#: Layer of an agent registered through the API, with no file behind it.
API_LAYER = "api"

router = APIRouter()
logger = logging.getLogger(__name__)


# In-memory pipeline state store (keyed by pipeline_id)
_MAX_PIPELINE_STATES = 1000
_pipeline_states: OrderedDict = OrderedDict()


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class CreateAgentBody(BaseModel):
    """Body for creating a new V2 agent."""

    name: str
    key: str
    description: str = ""
    scope: str = ""
    persona: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    critical_rules: list[str] = Field(default_factory=list)
    communication_style: str = "professional"


class UpdateAgentBody(BaseModel):
    """Body for updating an existing V2 agent."""

    name: str | None = None
    description: str | None = None
    scope: str | None = None
    persona: str | None = None
    inputs: list[str] | None = None
    outputs: list[str] | None = None
    tools: list[str] | None = None
    critical_rules: list[str] | None = None
    communication_style: str | None = None


class PipelineExecuteBody(BaseModel):
    """Body for executing a pipeline."""

    pipeline_id: str | None = None
    stages: list[dict] = Field(
        ...,
        description="List of {name, agent_key, handoff_type?} stage configs",
    )
    input_text: str
    max_retries: int = 3


class PipelineDefinitionBody(BaseModel):
    """Dashboard pipeline builder save/test payload."""

    id: str = ""
    name: str
    description: str = ""
    steps: list[dict] = Field(default_factory=list)
    version: int = 1
    venture_key: str = ""


_pipeline_definitions: OrderedDict[str, dict] = OrderedDict()
_MAX_PIPELINE_DEFINITIONS = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_registry(request: Request) -> AgentRegistry:
    """Get or initialize the agent registry from app state."""
    registry = getattr(request.app.state, "agent_registry", None)
    if registry is None:
        registry = AgentRegistry()
        # Load agents from all system directories
        systems = getattr(request.app.state, "systems", {})
        kb_path = getattr(request.app.state, "kb_path", None)
        if kb_path and systems:
            for sys_key, sys_conf in systems.items():
                agents_dir = kb_path / sys_conf.get("agents_dir", f"systems/{sys_key}/A-agents")
                if agents_dir.is_dir():
                    registry.load_from_directory(agents_dir)
        request.app.state.agent_registry = registry
    return registry


def _visible_agents(request: Request, agents: list) -> list:
    """Agents whose definition file lives in a venture the caller may see.

    The registry merges every venture's agents; a caller limited to some
    ventures sees only theirs (agents without a file are hidden from them).
    """
    if get_allowed_ventures(request) is None:
        return agents
    kb_path = getattr(request.app.state, "kb_path", None)
    if kb_path is None:
        return []
    dirs = [
        (Path(kb_path) / conf.get("agents_dir", f"systems/{key}/A-agents")).resolve()
        for key, conf in visible_systems(request).items()
    ]

    def inside(agent) -> bool:
        if not agent.file_path:
            return False
        path = Path(agent.file_path).resolve()
        return any(path.is_relative_to(d) for d in dirs)

    return [a for a in agents if inside(a)]


def _packs_on(request: Request) -> bool:
    """``features.packs`` in the running config."""
    from realize_core.config import get_features

    return bool(get_features(getattr(request.app.state, "config", None) or {}).get("packs"))


def _venture_dirs(request: Request) -> dict[str, Path]:
    """Each visible venture's ``A-agents/`` folder, resolved."""
    kb_path = getattr(request.app.state, "kb_path", None)
    if kb_path is None:
        return {}
    return {
        key: (Path(kb_path) / conf.get("agents_dir", f"systems/{key}/A-agents")).resolve()
        for key, conf in visible_systems(request).items()
    }


def _venture_of(agent: V1AgentDef | V2AgentDef, dirs: dict[str, Path]) -> str | None:
    """The venture whose ``A-agents/`` folder holds the agent's file, or None."""
    if not agent.file_path:
        return None
    path = Path(agent.file_path).resolve()
    for key, directory in dirs.items():
        if path.is_relative_to(directory):
            return key
    return None


def _local_dict(agent: V1AgentDef | V2AgentDef, dirs: dict[str, Path]) -> dict:
    """A venture's own (or API-registered) agent, with its layer (``features.packs`` on)."""
    venture = _venture_of(agent, dirs)
    return {
        **_agent_to_dict(agent),
        "venture_key": venture,
        "layer": VENTURE_LAYER if venture else API_LAYER,
        "read_only": False,
    }


def _pack_dict(entry) -> dict:
    """A pack agent of a venture: its definition, provenance and how to override it."""
    return {
        **_agent_to_dict(entry.definition),
        "venture_key": entry.venture_key,
        **entry.provenance,
        "read_only": True,
        "override_path": entry.override_path,
    }


def _pack_agents(request: Request, venture: str | None = None) -> list:
    """The pack agents of the visible ventures (or of ``venture``), with ``features.packs`` on."""
    if not _packs_on(request):
        return []
    from realize_core.packs.agents import venture_pack_agents

    kb_path = getattr(request.app.state, "kb_path", None)
    if kb_path is None:
        return []
    systems = visible_systems(request)
    keys = [venture] if venture else sorted(systems)
    return [entry for key in keys if key in systems for entry in venture_pack_agents(key, systems[key], kb_path)]


def _visible_venture(request: Request, venture: str | None) -> str | None:
    """``venture`` when the caller may see it; 404 otherwise. None stays None."""
    if venture is None:
        return None
    if venture not in visible_systems(request):
        raise HTTPException(status_code=404, detail=f"Venture '{venture}' not found")
    return venture


def _pack_agent(request: Request, agent_key: str, venture: str | None):
    """The pack agent ``agent_key`` the caller is addressing, or None.

    With ``venture``: that venture's pack agent of that key. Without: a pack
    agent of that key in a visible venture, unless one of the caller's
    ventures has its own agent with that key (the registry's entry is meant).
    """
    entries = [e for e in _pack_agents(request, venture) if e.key == agent_key]
    if not entries:
        return None
    if venture is None:
        registry = _get_registry(request)
        local = registry.get(agent_key)
        if local is not None and _visible_agents(request, [local]):
            return None
    return entries[0]


def _require_in_venture(request: Request, agent, agent_key: str, venture: str | None) -> None:
    """404 when ``venture`` is named and the registry's agent isn't that venture's own."""
    if venture is not None and (agent is None or _venture_of(agent, _venture_dirs(request)) != venture):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")


def _read_only_error(entry) -> HTTPException:
    """409 for a change to a pack agent: say where the venture's own copy goes."""
    origin = entry.provenance.get("layer", "pack")
    pack = entry.provenance.get("pack")
    source = "the firm's overrides" if origin == "firm" else f"the {origin} pack {pack}"
    return HTTPException(
        status_code=409,
        detail={
            "error": "pack_agent_read_only",
            "message": (
                f"Agent '{entry.key}' comes from {source} and is read-only here; packs are shared by every "
                f"venture that links them. To change it for '{entry.venture_key}', override it in your venture: "
                f"add {entry.override_path}. The venture's own file wins over the pack's."
            ),
            "agent_key": entry.key,
            "venture_key": entry.venture_key,
            **entry.provenance,
            "override_path": entry.override_path,
        },
    )


def _agent_to_dict(agent: V1AgentDef | V2AgentDef) -> dict:
    """Serialize an agent definition to a JSON-safe dict."""
    if isinstance(agent, V1AgentDef):
        return {
            "key": agent.key,
            "name": agent.name,
            "version": agent.version,
            "file_path": agent.file_path,
            "role": agent.role,
            "personality": agent.personality,
            "capabilities": agent.capabilities,
            "operating_rules": agent.operating_rules,
        }
    # V2
    return {
        "key": agent.key,
        "name": agent.name,
        "version": agent.version,
        "description": agent.description,
        "scope": agent.scope,
        "persona": agent.persona,
        "inputs": agent.inputs,
        "outputs": agent.outputs,
        "tools": agent.tools,
        "critical_rules": agent.critical_rules,
        "communication_style": agent.communication_style,
        "has_pipeline": agent.has_pipeline,
        "pipeline_stages": [
            {
                "name": s.name,
                "agent_key": s.agent_key,
                "handoff_type": s.handoff_type.value,
            }
            for s in agent.pipeline_stages
        ],
        "guardrails": [
            {"name": g.name, "description": g.description, "enforcement": g.enforcement} for g in agent.guardrails
        ],
        "success_metrics": agent.success_metrics,
        "file_path": agent.file_path,
    }


# ---------------------------------------------------------------------------
# Agent CRUD endpoints
# ---------------------------------------------------------------------------


def _keep(agent: V1AgentDef | V2AgentDef, version: str | None, persona: str | None) -> bool:
    """The ``version`` and ``persona`` filters of the agent list."""
    if version == "1" and not isinstance(agent, V1AgentDef):
        return False
    if version == "2" and not isinstance(agent, V2AgentDef):
        return False
    return not persona or (isinstance(agent, V2AgentDef) and agent.persona == persona)


@router.get("/agents")
async def list_agents(
    request: Request,
    version: str | None = None,
    persona: str | None = None,
    venture: str | None = None,
):
    """
    List all loaded agents.

    Query params:
    - version: filter by "1" or "2"
    - persona: filter by persona key (V2 only)
    - venture: only that venture's agents (its effective team with ``features.packs`` on)

    With ``features.packs`` on, each agent also says where it came from:
    ``venture_key``, ``layer`` (``venture`` for the venture's own file,
    ``firm``, ``market`` or ``profession`` for a pack's, ``api`` for one
    registered through this API), ``pack`` and ``verification`` for pack
    agents, and ``read_only`` (true for pack agents, with the
    ``override_path`` where the venture's own copy would go).
    """
    venture = _visible_venture(request, venture)
    registry = _get_registry(request)

    if version == "1":
        agents = registry.v1_agents()
    elif version == "2":
        agents = registry.v2_agents()
    else:
        agents = registry.all()

    if persona:
        agents = [a for a in agents if isinstance(a, V2AgentDef) and a.persona == persona]
    agents = _visible_agents(request, agents)
    if venture is not None:
        dirs = _venture_dirs(request)
        agents = [a for a in agents if _venture_of(a, {venture: dirs[venture]}) == venture] if venture in dirs else []

    if not _packs_on(request):
        return {
            "agents": [_agent_to_dict(a) for a in agents],
            "total": len(agents),
        }

    dirs = _venture_dirs(request)
    out = [_local_dict(a, dirs) for a in agents]
    out += [_pack_dict(e) for e in _pack_agents(request, venture) if _keep(e.definition, version, persona)]
    return {"agents": out, "total": len(out)}


@router.get("/agents/personas")
async def get_personas():
    """List all available persona bundles."""
    personas = list_personas()
    return {
        "personas": [
            {
                "key": p.key,
                "display_name": p.display_name,
                "description": p.description,
                "communication_style": p.communication_style,
                "default_tools": list(p.default_tools),
            }
            for p in personas
        ],
    }


@router.get("/agents/{agent_key}")
async def get_agent(agent_key: str, request: Request, venture: str | None = None):
    """Get detailed info for a specific agent.

    ``venture`` names the venture whose agent is meant. With
    ``features.packs`` on, a pack agent is found too, with its provenance.
    """
    venture = _visible_venture(request, venture)
    entry = _pack_agent(request, agent_key, venture)
    if entry is not None:
        return _pack_dict(entry)
    registry = _get_registry(request)
    agent = registry.get(agent_key)
    if not agent or not _visible_agents(request, [agent]):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")
    dirs = _venture_dirs(request)
    if venture is not None and _venture_of(agent, dirs) != venture:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")
    return _local_dict(agent, dirs) if _packs_on(request) else _agent_to_dict(agent)


@router.post("/agents", status_code=201)
async def create_agent(body: CreateAgentBody, request: Request):
    """Create and register a new V2 agent."""
    registry = _get_registry(request)

    if body.key in registry:
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{body.key}' already exists",
        )

    if body.persona and body.persona not in persona_keys():
        raise HTTPException(
            status_code=400,
            detail=f"Unknown persona '{body.persona}'. Available: {persona_keys()}",
        )

    agent = V2AgentDef(
        name=body.name,
        key=body.key,
        description=body.description,
        scope=body.scope,
        persona=body.persona,
        inputs=body.inputs,
        outputs=body.outputs,
        tools=body.tools,
        critical_rules=body.critical_rules,
        communication_style=body.communication_style,
    )
    registry.register(agent)

    logger.info("Created V2 agent '%s' via API", body.key)
    return _agent_to_dict(agent)


@router.put("/agents/{agent_key}")
async def update_agent(agent_key: str, body: UpdateAgentBody, request: Request, venture: str | None = None):
    """Update an existing V2 agent definition.

    A pack agent (``features.packs``) is read-only: 409 with the path where
    the venture's own copy would go. Nothing is written into the pack.
    """
    venture = _visible_venture(request, venture)
    entry = _pack_agent(request, agent_key, venture)
    if entry is not None:
        raise _read_only_error(entry)
    registry = _get_registry(request)
    existing = registry.get(agent_key)
    _require_in_venture(request, existing, agent_key, venture)

    if not existing:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    if not isinstance(existing, V2AgentDef):
        raise HTTPException(
            status_code=400,
            detail="Cannot update V1 agents via API. Convert to V2 YAML first.",
        )

    # Build updated data from existing + patches
    update_data = existing.model_dump()
    for field_name, value in body.model_dump(exclude_unset=True).items():
        update_data[field_name] = value

    updated = V2AgentDef(**update_data)
    registry.register(updated)

    logger.info("Updated V2 agent '%s' via API", agent_key)
    return _agent_to_dict(updated)


@router.delete("/agents/{agent_key}")
async def delete_agent(agent_key: str, request: Request, venture: str | None = None):
    """Unregister an agent from the registry. A pack agent is read-only (409)."""
    venture = _visible_venture(request, venture)
    entry = _pack_agent(request, agent_key, venture)
    if entry is not None:
        raise _read_only_error(entry)
    registry = _get_registry(request)
    _require_in_venture(request, registry.get(agent_key), agent_key, venture)

    if not registry.unregister(agent_key):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    logger.info("Deleted agent '%s' via API", agent_key)
    return {"status": "deleted", "key": agent_key}


@router.post("/agents/reload")
async def reload_agents(request: Request):
    """Hot-reload all agents from source directories."""
    registry = _get_registry(request)
    total = registry.reload()
    return {
        "status": "reloaded",
        "total_agents": total,
        "source_dirs": [str(d) for d in registry.source_dirs],
    }


# ---------------------------------------------------------------------------
# Pipeline management endpoints
# ---------------------------------------------------------------------------


#: What every pipeline run says about itself: nothing in it was executed.
SIMULATED_NOTE = (
    "Simulated run: no agent, tool, approval or condition actually ran. "
    "Pipeline execution isn't wired up; use a skill (Workflows) for real runs."
)


def _pipeline_definition_to_dict(pipeline_id: str, data: dict) -> dict:
    """Return a stable JSON shape for saved dashboard pipelines."""
    return {
        "id": pipeline_id,
        "name": data.get("name", pipeline_id),
        "description": data.get("description", ""),
        "steps": data.get("steps", []),
        "version": data.get("version", 1),
        "venture_key": data.get("venture_key", ""),
        "updated_at": data.get("updated_at"),
    }


def _pipeline_steps_to_stages(steps: list[dict]) -> list[dict]:
    """Convert dashboard builder steps into executable pipeline stages."""
    stages = []
    for index, step in enumerate(steps, start=1):
        step_type = step.get("type", "agent")
        agent_key = step.get("agent") or "orchestrator"
        if step_type == "tool":
            agent_key = step.get("tool") or "tool"
        elif step_type == "human":
            agent_key = "human"
        elif step_type == "condition":
            agent_key = "condition"
        stages.append(
            {
                "name": step.get("label") or step.get("id") or f"step-{index}",
                "agent_key": agent_key,
                "handoff_type": "standard",
            }
        )
    return stages


@router.get("/pipelines")
async def list_pipeline_definitions(venture_key: str = ""):
    """List dashboard-saved pipeline definitions."""
    pipelines = [
        _pipeline_definition_to_dict(pipeline_id, data)
        for pipeline_id, data in _pipeline_definitions.items()
        if not venture_key or data.get("venture_key") == venture_key
    ]
    return {"pipelines": pipelines, "count": len(pipelines)}


@router.post("/pipelines", status_code=201)
async def save_pipeline_definition(body: PipelineDefinitionBody):
    """Save a dashboard pipeline definition for later reuse."""
    pipeline_id = body.id.strip() or f"pipeline-{uuid.uuid4().hex[:12]}"
    data = body.model_dump()
    data["id"] = pipeline_id
    data["updated_at"] = datetime.now().isoformat()

    _pipeline_definitions[pipeline_id] = data
    _pipeline_definitions.move_to_end(pipeline_id)
    if len(_pipeline_definitions) > _MAX_PIPELINE_DEFINITIONS:
        _pipeline_definitions.popitem(last=False)

    return {"status": "saved", "pipeline": _pipeline_definition_to_dict(pipeline_id, data)}


@router.post("/pipelines/test")
async def test_pipeline_definition(body: PipelineDefinitionBody, request: Request):
    """Run a lightweight dashboard pipeline smoke test."""
    stages = _pipeline_steps_to_stages(body.steps)
    if not stages:
        raise HTTPException(status_code=400, detail="Pipeline must have at least one step")

    exec_body = PipelineExecuteBody(
        pipeline_id=body.id or f"test-{uuid.uuid4().hex[:12]}",
        stages=stages,
        input_text=f"Test run for {body.name}",
    )
    result = await execute_pipeline_endpoint(exec_body, request)
    return {"result": SIMULATED_NOTE, **result}


@router.post("/pipelines/execute", status_code=202)
async def execute_pipeline_endpoint(body: PipelineExecuteBody, request: Request):
    """
    Execute a multi-agent pipeline.

    Returns immediately with a pipeline_id. Use GET /pipelines/{id} to poll.
    """
    from realize_core.agents.pipeline import execute_pipeline

    pipeline_id = body.pipeline_id or str(uuid.uuid4())

    # Build PipelineStage objects
    stages = []
    for s in body.stages:
        ht = HandoffType(s.get("handoff_type", "standard"))
        stages.append(
            PipelineStage(
                name=s["name"],
                agent_key=s["agent_key"],
                handoff_type=ht,
            )
        )

    if not stages:
        raise HTTPException(status_code=400, detail="Pipeline must have at least one stage")

    # Pipelines are a frozen surface (ADR 0004) with no real executor: stages
    # are echoed, never run. Every response says so (Codex audit F07).
    async def _api_stage_executor(stage, input_text, context):
        return f"[simulated: {stage.agent_key} did not run]"

    state = await execute_pipeline(
        pipeline_id=pipeline_id,
        stages=stages,
        initial_input=body.input_text,
        stage_executor=_api_stage_executor,
        max_retries=body.max_retries,
    )

    _pipeline_states[pipeline_id] = state
    if len(_pipeline_states) > _MAX_PIPELINE_STATES:
        _pipeline_states.popitem(last=False)

    return {
        "pipeline_id": pipeline_id,
        "status": state.status.value,
        "simulated": True,
        "message": SIMULATED_NOTE,
        "stages_completed": len(state.results),
        "total_stages": len(stages),
    }


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline_state(pipeline_id: str):
    """Get the state of a pipeline execution."""
    state = _pipeline_states.get(pipeline_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")

    return {
        "pipeline_id": state.pipeline_id,
        "simulated": True,
        "status": state.status.value,
        "current_stage_index": state.current_stage_index,
        "total_stages": len(state.stages),
        "duration_ms": state.total_duration_ms,
        "error": state.error,
        "results": [
            {
                "stage_name": r.stage_name,
                "agent_key": r.agent_key,
                "verdict": r.verdict.value,
                "duration_ms": r.duration_ms,
                "retry_count": r.retry_count,
                "output_preview": r.output[:200] if r.output else None,
                "error": r.error,
            }
            for r in state.results
        ],
    }
