"""
Approval Queue API routes — list, approve, reject pending approvals.

Endpoints:
- GET /api/approvals — list pending approvals (filterable by venture, status)
- POST /api/approvals/{id}/approve — approve with optional decision note
- POST /api/approvals/{id}/reject — reject with optional decision note
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from realize_api.dependencies import get_allowed_ventures, visible_to

router = APIRouter()
logger = logging.getLogger(__name__)


class DecisionBody(BaseModel):
    decision_note: str | None = None


@router.get("/approvals")
async def list_approvals(
    request: Request,
    venture_key: str = None,
    status: str = "pending",
):
    """List approvals, defaulting to pending (only the caller's ventures)."""
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        clauses = []
        params = []

        if status:
            clauses.append("status = ?")
            params.append(status)
        if venture_key:
            clauses.append("venture_key = ?")
            params.append(venture_key)
        allowed = get_allowed_ventures(request)
        if allowed is not None:
            keys = sorted(allowed) or [""]
            clauses.append(f"venture_key IN ({','.join('?' for _ in keys)})")
            params.extend(keys)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM approval_queue {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    finally:
        conn.close()
    approvals = [dict(r) for r in rows]
    from realize_core.security.agent_access import is_agent_subject

    viewer = getattr(request.state, "user_id", None)
    if is_agent_subject(request.state):
        # An outside agent sees status, not other people's parameters or results (STORY-37).
        from realize_core.mcp_server.held_writes import agent_view

        approvals = [agent_view(row, viewer) for row in approvals]
    return {"approvals": approvals}


def _decider(request: Request) -> tuple[str | None, str]:
    """Who is deciding, and through which channel (stored on the approval)."""
    state = request.state
    channel = "dashboard" if getattr(state, "auth_source", None) == "session" else "api"
    return getattr(state, "user_id", None), channel


def _require_visible(request: Request, approval_id: str) -> None:
    """404 unless the approval exists in a venture the caller may see."""
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        row = conn.execute("SELECT venture_key FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
    finally:
        conn.close()
    if row is None or not visible_to(request, row["venture_key"]):
        raise HTTPException(status_code=404, detail="Approval not found or not pending")


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, request: Request, body: DecisionBody = None):
    """Approve a pending request — a held tool action is dispatched now (once)."""
    from realize_core.governance.gates import decide_approval

    _require_visible(request, approval_id)

    note = body.decision_note if body else None
    decided_by, channel = _decider(request)
    result = await decide_approval(
        approval_id, approve=True, decision_note=note, decided_by=decided_by, channel=channel
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found or not pending")

    return _flatten(result)


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: str, request: Request, body: DecisionBody = None):
    """Reject a pending request."""
    from realize_core.governance.gates import decide_approval

    _require_visible(request, approval_id)

    note = body.decision_note if body else None
    decided_by, channel = _decider(request)
    result = await decide_approval(
        approval_id, approve=False, decision_note=note, decided_by=decided_by, channel=channel
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found or not pending")

    return _flatten(result)


def _flatten(result: dict) -> dict:
    """Keep the historical response shape (the approval row) and add outcomes."""
    return {
        **result["approval"],
        "execution": result["execution"],
        "skill_output": result["skill_output"],
        "decision_log": result.get("decision_log"),
    }
