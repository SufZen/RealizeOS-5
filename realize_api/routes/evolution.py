"""
Evolution API routes — surface the self-evolution system in the dashboard.

Endpoints:
- GET /api/evolution/suggestions — list pending evolution proposals
- POST /api/evolution/suggestions/{id}/approve — approve and apply a suggestion
- POST /api/evolution/suggestions/{id}/dismiss — dismiss a suggestion
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# Shared engine instance (lazy-initialized)
_engine = None


def _get_engine():
    """Get or create the evolution engine singleton."""
    global _engine
    if _engine is None:
        from realize_core.evolution.engine import EvolutionEngine
        _engine = EvolutionEngine(auto_approve_low_risk=False)
    return _engine


class DismissBody(BaseModel):
    reason: str | None = None


@router.get("/evolution/suggestions")
async def list_suggestions(status: str = None):
    """List evolution proposals, optionally filtered by status."""
    engine = _get_engine()
    proposals = []

    for p in engine._proposals.values():
        if status and p.status.value != status:
            continue
        proposals.append({
            "id": p.id,
            "type": p.evolution_type.value,
            "title": p.title,
            "description": p.description,
            "risk_level": p.risk_level.value,
            "status": p.status.value,
            "priority": p.priority,
            "source": p.source,
            "changes": p.changes,
            "created_at": p.created_at,
        })

    # Sort by priority (highest first), then by creation time
    proposals.sort(key=lambda x: (-x["priority"], -x["created_at"]))

    return {
        "suggestions": proposals,
        "total": len(proposals),
        "pending": sum(1 for p in proposals if p["status"] == "pending"),
    }


@router.post("/evolution/suggestions/{suggestion_id}/approve")
async def approve_suggestion(suggestion_id: str):
    """Approve and apply an evolution suggestion."""
    engine = _get_engine()

    if not engine.approve(suggestion_id):
        # May already be approved or not found
        proposal = engine._proposals.get(suggestion_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        if proposal.status.value != "pending":
            raise HTTPException(status_code=400, detail=f"Suggestion is already {proposal.status.value}")

    # Apply the approved suggestion
    if not engine.apply(suggestion_id):
        raise HTTPException(status_code=500, detail="Failed to apply suggestion (rate limit or error)")

    proposal = engine._proposals[suggestion_id]

    # Log activity
    try:
        from realize_core.activity.logger import log_event
        log_event(
            venture_key="_system",
            actor_type="user",
            actor_id="dashboard",
            action="evolution_approved",
            entity_type="evolution",
            entity_id=suggestion_id,
            details=f'{{"title": "{proposal.title}", "type": "{proposal.evolution_type.value}"}}',
        )
    except Exception:
        pass

    return {
        "id": suggestion_id,
        "status": "applied",
        "title": proposal.title,
    }


@router.post("/evolution/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: str, body: DismissBody = None):
    """Dismiss (reject) an evolution suggestion."""
    engine = _get_engine()

    reason = body.reason if body else ""
    if not engine.reject(suggestion_id, reason=reason or ""):
        proposal = engine._proposals.get(suggestion_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        if proposal.status.value != "pending":
            raise HTTPException(status_code=400, detail=f"Suggestion is already {proposal.status.value}")

    try:
        from realize_core.activity.logger import log_event
        log_event(
            venture_key="_system",
            actor_type="user",
            actor_id="dashboard",
            action="evolution_dismissed",
            entity_type="evolution",
            entity_id=suggestion_id,
        )
    except Exception:
        pass

    return {"id": suggestion_id, "status": "rejected"}
