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
    *,
    action_name: str | None = None,
    params: dict | None = None,
    requested_by: str | None = None,
    session_ref: str | None = None,
) -> str:
    """
    Create an approval request in the queue.

    ``payload`` is the display snapshot. For a held tool action, also pass
    ``action_name`` and the full ``params`` so the action can be executed
    once approved (:func:`execute_approved_action`), plus ``requested_by``
    and ``session_ref`` (``<venture>|<user>``) to report the outcome back.

    Returns the approval ID.
    """
    from realize_core.db.schema import get_connection

    approval_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=expires_minutes)

    conn = get_connection(db_path)
    try:
        stamp = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn.execute(
            """INSERT INTO approval_queue
               (id, venture_key, agent_key, action_type, payload, status, created_at, expires_at,
                action_name, params_json, requested_by, session_ref, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
            (
                approval_id,
                venture_key,
                agent_key,
                action_type,
                json.dumps(payload or {}, default=str),
                stamp,
                expires.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                action_name,
                json.dumps(params, default=str) if params is not None else None,
                requested_by,
                session_ref,
                stamp,
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
            "UPDATE approval_queue SET status = 'approved', decision_note = ?, decided_at = ?, updated_at = ? "
            "WHERE id = ?",
            (decision_note, now, now, approval_id),
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
            "UPDATE approval_queue SET status = 'rejected', decision_note = ?, decided_at = ?, updated_at = ? "
            "WHERE id = ?",
            (decision_note, now, now, approval_id),
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


# ---------------------------------------------------------------------------
# Execution of approved actions (v5.7.0)
# ---------------------------------------------------------------------------


def _claim_for_execution(approval_id: str, db_path=None) -> dict | None:
    """Atomically mark an approved, not-yet-executed tool action as executing.

    Returns the row when this caller won the claim, else None, so a double
    click or a retry can never run the same action twice.
    """
    from realize_core.db.schema import get_connection

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """UPDATE approval_queue SET executed_at = ?, updated_at = ?
               WHERE id = ? AND status = 'approved' AND executed_at IS NULL AND action_name IS NOT NULL""",
            (now, now, approval_id),
        )
        conn.commit()
        if cur.rowcount != 1:
            return None
        row = conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _store_execution_result(approval_id: str, output: str, error: str | None, db_path=None) -> None:
    from realize_core.db.schema import get_connection

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE approval_queue SET result_json = ?, error = ?, updated_at = ? WHERE id = ?",
            (json.dumps({"output": output}, default=str), error, now, approval_id),
        )
        conn.commit()
    finally:
        conn.close()


def report_to_conversation(session_ref: str | None, text: str) -> None:
    """Post a message into the conversation an approval was requested from."""
    from realize_core.governance.context import parse_session_ref

    parsed = parse_session_ref(session_ref)
    if not parsed:
        return
    try:
        from realize_core.memory.conversation import add_message

        add_message(parsed[0], parsed[1], "assistant", text)
    except Exception:
        logger.warning("Could not post approval outcome to conversation %s", session_ref, exc_info=True)


async def execute_approved_action(approval_id: str, db_path=None) -> dict:
    """Run an approved tool action exactly once and record the outcome.

    The action runs through the tool registry without consulting the gate
    again (an operator approved this exact action and parameters). The result
    is stored on the approval row, logged as ``approval_executed``, and posted
    into the originating conversation.

    Returns:
        ``{"executed": bool, "success": bool, "output": str, "error": str | None}``.
        ``executed`` is False when there was nothing to run (not a tool action,
        not approved, or already executed).
    """
    row = _claim_for_execution(approval_id, db_path)
    if row is None:
        return {"executed": False, "success": False, "output": "", "error": None}

    from realize_core.tools.tool_registry import get_tool_registry

    action = row["action_name"]
    try:
        params = json.loads(row.get("params_json") or "{}")
    except json.JSONDecodeError:
        params = None
    if not isinstance(params, dict):
        result_ok, output, error = False, "", "Stored parameters are unreadable"
    else:
        result = await get_tool_registry().execute_approved(action, params)
        result_ok, output, error = result.success, result.output or "", result.error

    _store_execution_result(approval_id, output, error, db_path)
    try:
        from realize_core.activity.logger import log_event

        log_event(
            venture_key=row["venture_key"],
            actor_type="system",
            actor_id="gate",
            action="approval_executed" if result_ok else "approval_execution_failed",
            entity_type="approval",
            entity_id=approval_id,
            details=json.dumps({"action": action, "error": error}),
        )
    except Exception:
        logger.debug("activity log failed for approval execution", exc_info=True)

    # Only a fixed status line goes into the conversation. Tool output and
    # errors can carry third-party text (email bodies, web pages, sheet cells);
    # stored as an assistant turn, injected instructions would persist into
    # later model calls. The full result stays on the approval row.
    if result_ok:
        report_to_conversation(
            row.get("session_ref"),
            f"Approved and done: `{action}` (approval {approval_id}). Details are on the approval.",
        )
    else:
        report_to_conversation(
            row.get("session_ref"),
            f"`{action}` was approved but failed (approval {approval_id}). See the approval for details.",
        )
    logger.info("Approved action %s (%s) executed: success=%s", approval_id, action, result_ok)
    return {"executed": True, "success": result_ok, "output": output, "error": error}


async def _resume_skill_from_approval(record: dict, answer: str) -> str | None:
    """Resume the skill paused at the human step this approval item belongs to."""
    from realize_core.governance.context import parse_session_ref
    from realize_core.skills.executor import peek_skill_resume_context, resume_pending_skill

    parsed = parse_session_ref(record.get("session_ref"))
    if not parsed:
        return None
    system_key, user_id = parsed
    pending = peek_skill_resume_context(user_id)
    if not pending or pending.get("approval_id") != record.get("id"):
        return None  # already answered in chat, or the server restarted

    from realize_core.engine import load_runtime

    runtime = load_runtime()
    output = await resume_pending_skill(
        user_id,
        answer,
        kb_path=runtime["kb_path"],
        system_config=runtime["systems"].get(system_key, {}),
        shared_config=runtime["shared_config"],
        channel="dashboard",
    )
    if output:
        report_to_conversation(record.get("session_ref"), output)
    return output


async def decide_approval(
    approval_id: str, approve: bool, decision_note: str | None = None, db_path=None
) -> dict | None:
    """Approve or reject an approval item and carry out what the decision implies.

    - Approved tool action: executed once (:func:`execute_approved_action`).
    - Skill question (``skill_input``): the paused skill resumes with the
      decision note, or "yes"/"no".

    Returns ``{"approval": row, "execution": ..., "skill_output": ...}`` or
    None when the item doesn't exist or isn't pending.
    """
    record = (
        approve_request(approval_id, decision_note=decision_note, db_path=db_path)
        if approve
        else reject_request(approval_id, decision_note=decision_note, db_path=db_path)
    )
    if record is None:
        return None

    out: dict = {"approval": record, "execution": None, "skill_output": None}
    if approve and record.get("action_name"):
        out["execution"] = await execute_approved_action(approval_id, db_path=db_path)
    elif not approve and record.get("action_name"):
        report_to_conversation(
            record.get("session_ref"), f"`{record['action_name']}` was not approved, so it was not done."
        )
    if record.get("action_type") == "skill_input":
        answer = decision_note or ("yes" if approve else "no")
        out["skill_output"] = await _resume_skill_from_approval(record, answer)
    return out
