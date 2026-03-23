"""
Approval Gate System: configurable gates on consequential agent actions.

When an agent attempts a gated action (e.g., send_email, publish_content),
the gate intercepts the request, creates an approval_queue record, and
returns a "pending approval" response instead of executing.

Gate configuration lives in realize-os.yaml under governance.gates:
```yaml
governance:
  gates:
    send_email: true
    publish_content: true
    external_api: true
    create_event: false
    high_cost_llm: false
```
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# Default gate types and whether they're enabled
DEFAULT_GATES = {
    "send_email": True,
    "publish_content": True,
    "external_api": True,
    "create_event": False,
    "high_cost_llm": False,
}

# Map tool action names to gate types
ACTION_TO_GATE = {
    "send_email": "send_email",
    "send_gmail": "send_email",
    "create_draft": "send_email",
    "create_event": "create_event",
    "create_calendar_event": "create_event",
    "publish": "publish_content",
    "post_linkedin": "publish_content",
    "post_social": "publish_content",
    "web_action": "external_api",
    "http_request": "external_api",
}


def get_gate_config(features: dict = None) -> dict:
    """Get the current gate configuration."""
    if not features:
        return {}
    governance = features.get("governance", {})
    if isinstance(governance, dict):
        return governance.get("gates", DEFAULT_GATES)
    return DEFAULT_GATES


def is_gated(action_name: str, features: dict = None) -> bool:
    """Check if an action requires approval."""
    if not features or not features.get("approval_gates"):
        return False

    gate_type = ACTION_TO_GATE.get(action_name)
    if not gate_type:
        return False

    gates = get_gate_config(features)
    return gates.get(gate_type, DEFAULT_GATES.get(gate_type, False))


def create_approval_request(
    venture_key: str,
    agent_key: str,
    action_type: str,
    payload: dict = None,
    expires_minutes: int = 60,
    db_path=None,
) -> str:
    """
    Create an approval request in the queue.

    Returns the approval ID.
    """
    from realize_core.db.schema import get_connection

    approval_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=expires_minutes)

    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO approval_queue
               (id, venture_key, agent_key, action_type, payload, status, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (
                approval_id,
                venture_key,
                agent_key,
                action_type,
                json.dumps(payload or {}, default=str),
                now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                expires.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Log activity event
    try:
        from realize_core.activity.logger import log_event

        log_event(
            venture_key=venture_key,
            actor_type="system",
            actor_id="gate",
            action="approval_requested",
            entity_type="approval",
            entity_id=approval_id,
            details=json.dumps({"action_type": action_type, "agent": agent_key}),
        )
    except Exception:
        pass

    logger.info(f"Approval requested: {action_type} by {agent_key}@{venture_key} (id={approval_id})")
    return approval_id


def get_pending_approvals(venture_key: str = None, db_path=None) -> list[dict]:
    """Get all pending approvals, optionally filtered by venture."""
    from realize_core.db.schema import get_connection

    conn = get_connection(db_path)
    try:
        if venture_key:
            rows = conn.execute(
                "SELECT * FROM approval_queue WHERE status = 'pending' AND venture_key = ? ORDER BY created_at DESC",
                (venture_key,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM approval_queue WHERE status = 'pending' ORDER BY created_at DESC",
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def approve_request(approval_id: str, decision_note: str = None, db_path=None) -> dict | None:
    """Approve a pending request. Returns the approval record or None if not found."""
    from realize_core.db.schema import get_connection

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM approval_queue WHERE id = ? AND status = 'pending'",
            (approval_id,),
        ).fetchone()
        if not row:
            return None

        conn.execute(
            "UPDATE approval_queue SET status = 'approved', decision_note = ?, decided_at = ? WHERE id = ?",
            (decision_note, now, approval_id),
        )
        conn.commit()

        result = dict(row)
        result["status"] = "approved"
        result["decision_note"] = decision_note
        result["decided_at"] = now
    finally:
        conn.close()

    try:
        from realize_core.activity.logger import log_event

        log_event(
            venture_key=result["venture_key"],
            actor_type="user",
            actor_id="dashboard",
            action="approval_approved",
            entity_type="approval",
            entity_id=approval_id,
        )
    except Exception:
        pass

    return result


def reject_request(approval_id: str, decision_note: str = None, db_path=None) -> dict | None:
    """Reject a pending request. Returns the approval record or None if not found."""
    from realize_core.db.schema import get_connection

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM approval_queue WHERE id = ? AND status = 'pending'",
            (approval_id,),
        ).fetchone()
        if not row:
            return None

        conn.execute(
            "UPDATE approval_queue SET status = 'rejected', decision_note = ?, decided_at = ? WHERE id = ?",
            (decision_note, now, approval_id),
        )
        conn.commit()

        result = dict(row)
        result["status"] = "rejected"
        result["decision_note"] = decision_note
        result["decided_at"] = now
    finally:
        conn.close()

    try:
        from realize_core.activity.logger import log_event

        log_event(
            venture_key=result["venture_key"],
            actor_type="user",
            actor_id="dashboard",
            action="approval_rejected",
            entity_type="approval",
            entity_id=approval_id,
        )
    except Exception:
        pass

    return result
