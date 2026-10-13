"""
Approval Queue API routes — list, approve, reject pending approvals.

Endpoints:
- GET /api/approvals — list pending approvals (filterable by venture, status)
- POST /api/approvals/{id}/approve — approve with optional decision note
- POST /api/approvals/{id}/reject — reject with optional decision note

``status`` is the item's effective status: a pending item past ``expires_at``
is listed as ``expired`` (no one can decide it any more), and ``?status=pending``
returns only items that can still be decided. A decision on an item that exists
but can't be decided any more (expired, or someone else decided first) gets
``409`` with ``reason`` and the item's current state; a missing or invisible
item stays ``404``.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
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
    """List approvals, defaulting to pending (only the caller's ventures).

    ``pending`` means still decidable; ``expired`` includes pending items whose
    time ran out. Every row reports its effective ``status`` and ``expired``.
    """
    from realize_core.db.schema import get_connection
    from realize_core.governance.approval_status import now_stamp, status_clause, with_effective_status

    now = now_stamp()
    conn = get_connection()
    try:
        clauses: list[str] = []
        params: list[str] = []

        if status:
            clause, clause_params = status_clause(status, now)
            clauses.append(clause)
            params.extend(clause_params)
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
    approvals = [with_effective_status(dict(r), now) for r in rows]
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


_NOT_FOUND = "Approval not found or not pending"


def _visible_row(request: Request, approval_id: str) -> dict:
    """The approval row, or 404 unless it exists in a venture the caller may see."""
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
    finally:
        conn.close()
    if row is None or not visible_to(request, row["venture_key"]):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return dict(row)


def _require_visible(request: Request, approval_id: str) -> None:
    """404 unless the approval exists in a venture the caller may see."""
    _visible_row(request, approval_id)


def _refused(request: Request, approval_id: str) -> JSONResponse:
    """Explain a decision that didn't apply: 409 with the item's current state.

    The item exists and the caller may see it, but it expired or someone else
    decided it first. A missing item (or one that is no longer visible) is 404.
    """
    from realize_core.governance.approval_status import decision_refusal, decision_summary, now_stamp

    row = _visible_row(request, approval_id)
    now = now_stamp()
    reason, message = decision_refusal(row, now)
    logger.info("Decision on approval %s refused: %s", approval_id, reason)
    return JSONResponse(
        status_code=409,
        content={"detail": message, "reason": reason, "approval": decision_summary(row, now)},
    )


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
        return _refused(request, approval_id)

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
        return _refused(request, approval_id)

    return _flatten(result)


def _flatten(result: dict) -> dict:
    """Keep the historical response shape (the approval row) and add outcomes."""
    return {**result["approval"], "execution": result["execution"], "skill_output": result["skill_output"]}
