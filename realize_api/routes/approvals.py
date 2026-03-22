"""
Approval Queue API routes — list, approve, reject pending approvals.

Endpoints:
- GET /api/approvals — list pending approvals (filterable by venture, status)
- POST /api/approvals/{id}/approve — approve with optional decision note
- POST /api/approvals/{id}/reject — reject with optional decision note
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class DecisionBody(BaseModel):
    decision_note: str | None = None


@router.get("/approvals")
async def list_approvals(
    venture_key: str = None,
    status: str = "pending",
):
    """List approvals, defaulting to pending."""
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

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM approval_queue {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
        return {"approvals": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, body: DecisionBody = None):
    """Approve a pending request."""
    from realize_core.governance.gates import approve_request

    note = body.decision_note if body else None
    result = approve_request(approval_id, decision_note=note)

    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found or not pending")

    return result


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: str, body: DecisionBody = None):
    """Reject a pending request."""
    from realize_core.governance.gates import reject_request

    note = body.decision_note if body else None
    result = reject_request(approval_id, decision_note=note)

    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found or not pending")

    return result
