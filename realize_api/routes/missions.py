"""Mission Engine API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from realize_core.missions.engine import MissionEngine
from realize_core.missions.state import Mission
from realize_core.runtimes.registry import RuntimeRegistry

router = APIRouter()


class CreateMissionBody(BaseModel):
    """Request body for creating a mission."""

    title: str
    goal: str
    venture: str = ""
    owner: str = "dashboard"
    budget_eur: float | None = None
    deadline: datetime | None = None
    requires_approval_for: list[str] = Field(default_factory=list)
    steps: list[dict] = Field(default_factory=list)


def _get_mission_engine(request: Request) -> MissionEngine:
    """Get or initialize the app-level MissionEngine."""
    engine = getattr(request.app.state, "mission_engine", None)
    if engine is None:
        registry = getattr(request.app.state, "runtime_registry", None) or RuntimeRegistry()
        engine = MissionEngine(
            registry=registry,
            synapse=getattr(request.app.state, "synapse", None),
        )
        request.app.state.mission_engine = engine
    return engine


def _mission_to_dict(mission: Mission) -> dict:
    """Serialize Mission with step duration included for dashboard consumers."""
    data = mission.to_dict()
    data["plan"] = [
        {
            **step.to_dict(),
            "duration_sec": step.duration_sec,
        }
        for step in mission.plan
    ]
    return data


@router.get("/missions")
async def list_missions(request: Request, venture: str = "", state: str = ""):
    """List missions with optional venture/state filters."""
    engine = _get_mission_engine(request)
    missions = [_mission_to_dict(mission) for mission in engine.list_missions(venture=venture, state=state)]
    return {"missions": missions, "count": len(missions)}


@router.post("/missions", status_code=201)
async def create_mission(body: CreateMissionBody, request: Request):
    """Create a mission, optionally with an initial plan."""
    engine = _get_mission_engine(request)
    mission = engine.create_mission(
        title=body.title,
        goal=body.goal,
        venture=body.venture,
        owner=body.owner,
        budget_eur=body.budget_eur,
        deadline=body.deadline,
        requires_approval_for=body.requires_approval_for,
    )
    if body.steps:
        mission = engine.plan_mission(mission.mission_id, body.steps)
    return {"status": "created", "mission": _mission_to_dict(mission)}


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str, request: Request):
    """Get a single mission."""
    mission = _get_mission_engine(request).get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not found")
    return {"mission": _mission_to_dict(mission)}
