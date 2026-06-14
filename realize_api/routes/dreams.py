"""Dream Inbox API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from realize_core.dreaming.curator import CuratorCycle
from realize_core.dreaming.inbox import DreamInbox
from realize_core.dreaming.policy import TrustPolicy
from realize_core.governance.policy_overview import effective_policy

router = APIRouter()


class RejectDreamBody(BaseModel):
    """Request body for rejecting a dream proposal."""

    reason: str = ""


def _get_dream_inbox(request: Request) -> DreamInbox:
    """Get or initialize the persisted Dream Inbox."""
    inbox = getattr(request.app.state, "dream_inbox", None)
    if inbox is not None:
        return inbox

    kb_path = Path(getattr(request.app.state, "kb_path", None) or ".")
    policy = TrustPolicy.load(kb_path / "shared" / "trust-policy.yaml")
    inbox = DreamInbox(
        inbox_path=kb_path / ".synapse" / "dream-inbox.jsonl",
        policy=policy,
        event_log=getattr(request.app.state, "event_log", None),
    )
    request.app.state.dream_inbox = inbox
    return inbox


@router.get("/dreams")
async def list_dreams(
    request: Request,
    status: str = "",
    cycle_type: str = "",
    limit: int = 100,
):
    """List Dream Inbox proposals."""
    inbox = _get_dream_inbox(request)
    proposals = [proposal.to_dict() for proposal in inbox.history(limit=limit)]
    if status:
        proposals = [proposal for proposal in proposals if proposal["status"] == status]
    if cycle_type:
        proposals = [proposal for proposal in proposals if proposal["cycle_type"] == cycle_type]
    return {
        "proposals": proposals,
        "count": len(proposals),
        "stats": inbox.stats(),
    }


@router.get("/policy")
async def get_effective_policy(request: Request, venture: str = ""):
    """Read-only combined view of both trust surfaces (knowledge + tools).

    See ADR 0002. Returns the Dreaming (knowledge) policy and the Governance
    (tools) decisions in one snapshot. Never mutates state.
    """
    config = getattr(request.app.state, "config", None) or {}
    kb_path = getattr(request.app.state, "kb_path", None)
    return effective_policy(config, kb_path=kb_path, venture=venture or None)


@router.post("/dreams/run")
async def run_dream_cycle(request: Request, venture: str = ""):
    """Run a curator dream cycle and submit proposals to the inbox."""
    synapse = getattr(request.app.state, "synapse", None)
    if synapse is None:
        raise HTTPException(status_code=503, detail="Synapse index is not initialized")

    inbox = _get_dream_inbox(request)
    policy = getattr(inbox, "_policy", TrustPolicy())
    proposals = CuratorCycle(synapse=synapse, policy=policy).run(venture=venture)
    proposal_ids = inbox.submit_batch(proposals)
    return {
        "status": "submitted",
        "submitted": len(proposal_ids),
        "proposal_ids": proposal_ids,
        "stats": inbox.stats(),
    }


@router.post("/dreams/{proposal_id}/approve")
async def approve_dream(proposal_id: str, request: Request):
    """Approve a pending dream proposal."""
    inbox = _get_dream_inbox(request)
    if not inbox.approve(proposal_id, reviewed_by="dashboard"):
        raise HTTPException(status_code=404, detail=f"Pending proposal '{proposal_id}' not found")
    proposal = inbox.get(proposal_id)
    return {"status": "approved", "proposal": proposal.to_dict() if proposal else None}


@router.post("/dreams/{proposal_id}/reject")
async def reject_dream(proposal_id: str, body: RejectDreamBody, request: Request):
    """Reject a pending dream proposal."""
    inbox = _get_dream_inbox(request)
    if not inbox.reject(proposal_id, reason=body.reason, reviewed_by="dashboard"):
        raise HTTPException(status_code=404, detail=f"Pending proposal '{proposal_id}' not found")
    proposal = inbox.get(proposal_id)
    return {"status": "rejected", "proposal": proposal.to_dict() if proposal else None}
