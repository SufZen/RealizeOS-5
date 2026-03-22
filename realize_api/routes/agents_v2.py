"""
Agents V2 API routes — CRUD for V2 composable agents + pipeline management.

Endpoints:
- GET    /api/agents                      — list all agents across systems
- GET    /api/agents/{agent_key}          — get agent details (V1 or V2)
- POST   /api/agents                      — create/register a V2 agent
- PUT    /api/agents/{agent_key}          — update a V2 agent definition
- DELETE /api/agents/{agent_key}          — unregister an agent
- POST   /api/agents/reload              — hot-reload agents from directories
- GET    /api/agents/personas             — list available persona bundles
- POST   /api/pipelines/execute           — execute a pipeline
- GET    /api/pipelines/{pipeline_id}     — get pipeline execution state
"""
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from realize_core.agents.base import HandoffType, PipelineStage
from realize_core.agents.personas import list_personas, persona_keys
from realize_core.agents.registry import AgentRegistry
from realize_core.agents.schema import V1AgentDef, V2AgentDef

router = APIRouter()
logger = logging.getLogger(__name__)

# Module-level registry instance (initialized on first request or reload)
_registry: AgentRegistry | None = None

# In-memory pipeline state store (keyed by pipeline_id)
_pipeline_states: dict = {}


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_registry(request: Request) -> AgentRegistry:
    """Get or initialize the agent registry from app state."""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
        # Load agents from all system directories
        systems = getattr(request.app.state, "systems", {})
        kb_path = getattr(request.app.state, "kb_path", None)
        if kb_path and systems:
            for sys_key, sys_conf in systems.items():
                agents_dir = kb_path / sys_conf.get("agents_dir", f"systems/{sys_key}/A-agents")
                if agents_dir.is_dir():
                    _registry.load_from_directory(agents_dir)
    return _registry


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
            {"name": g.name, "description": g.description, "enforcement": g.enforcement}
            for g in agent.guardrails
        ],
        "success_metrics": agent.success_metrics,
        "file_path": agent.file_path,
    }


# ---------------------------------------------------------------------------
# Agent CRUD endpoints
# ---------------------------------------------------------------------------

@router.get("/agents")
async def list_agents(
    request: Request,
    version: str | None = None,
    persona: str | None = None,
):
    """
    List all loaded agents.

    Query params:
    - version: filter by "1" or "2"
    - persona: filter by persona key (V2 only)
    """
    registry = _get_registry(request)

    if version == "1":
        agents = registry.v1_agents()
    elif version == "2":
        agents = registry.v2_agents()
    else:
        agents = registry.all()

    if persona:
        agents = [
            a for a in agents
            if isinstance(a, V2AgentDef) and a.persona == persona
        ]

    return {
        "agents": [_agent_to_dict(a) for a in agents],
        "total": len(agents),
    }


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
async def get_agent(agent_key: str, request: Request):
    """Get detailed info for a specific agent."""
    registry = _get_registry(request)
    agent = registry.get(agent_key)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")
    return _agent_to_dict(agent)


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
async def update_agent(agent_key: str, body: UpdateAgentBody, request: Request):
    """Update an existing V2 agent definition."""
    registry = _get_registry(request)
    existing = registry.get(agent_key)

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
async def delete_agent(agent_key: str, request: Request):
    """Unregister an agent from the registry."""
    registry = _get_registry(request)

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
        stages.append(PipelineStage(
            name=s["name"],
            agent_key=s["agent_key"],
            handoff_type=ht,
        ))

    if not stages:
        raise HTTPException(status_code=400, detail="Pipeline must have at least one stage")

    # Simple echo executor for now — real LLM executor wired at integration gate
    async def _api_stage_executor(stage, input_text, context):
        return f"[{stage.agent_key}] Processed: {input_text[:200]}"

    state = await execute_pipeline(
        pipeline_id=pipeline_id,
        stages=stages,
        initial_input=body.input_text,
        stage_executor=_api_stage_executor,
        max_retries=body.max_retries,
    )

    _pipeline_states[pipeline_id] = state

    return {
        "pipeline_id": pipeline_id,
        "status": state.status.value,
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
