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


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _decide(
    approval_id: str,
    status: str,
    decision_note: str | None,
    decided_by: str | None,
    channel: str | None,
    db_path=None,
) -> dict | None:
    """Move a pending, unexpired item to ``status`` in one compare-and-set step.

    The UPDATE itself requires ``status = 'pending'`` and an unexpired
    ``expires_at``, so of two concurrent decisions exactly one wins; the other
    gets None. Expired items can't be decided.
    """
    from realize_core.db.schema import get_connection

    now = _now()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """UPDATE approval_queue
               SET status = ?, decision_note = ?, decided_at = ?, updated_at = ?,
                   decided_by = ?, decision_channel = ?
               WHERE id = ? AND status = 'pending' AND (expires_at IS NULL OR expires_at > ?)""",
            (status, decision_note, now, now, decided_by, channel, approval_id, now),
        )
        conn.commit()
        if cur.rowcount != 1:
            return None
        row = conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
        result = dict(row) if row else None
    finally:
        conn.close()

    if result is not None:
        try:
            from realize_core.activity.logger import log_event

            log_event(
                venture_key=result["venture_key"],
                actor_type="user",
                actor_id=decided_by or channel or "unknown",
                action=f"approval_{status}",
                entity_type="approval",
                entity_id=approval_id,
                details=json.dumps({"channel": channel}),
            )
        except Exception:
            logger.debug("activity log failed for approval decision", exc_info=True)
    return result


def approve_request(
    approval_id: str,
    decision_note: str = None,
    db_path=None,
    *,
    decided_by: str | None = None,
    channel: str | None = None,
) -> dict | None:
    """Approve a pending, unexpired request. Returns the row, or None if it isn't pending or has expired."""
    return _decide(approval_id, "approved", decision_note, decided_by, channel, db_path)


def reject_request(
    approval_id: str,
    decision_note: str = None,
    db_path=None,
    *,
    decided_by: str | None = None,
    channel: str | None = None,
) -> dict | None:
    """Reject a pending, unexpired request. Returns the row, or None if it isn't pending or has expired."""
    return _decide(approval_id, "rejected", decision_note, decided_by, channel, db_path)


def answer_request(
    approval_id: str,
    answer: str,
    db_path=None,
    *,
    answered_by: str | None = None,
    channel: str | None = None,
) -> dict | None:
    """Record the answer to a skill's question (``skill_input``).

    An answer is input, not an approval: the row becomes ``answered``.
    """
    return _decide(approval_id, "answered", answer, answered_by, channel, db_path)


# ---------------------------------------------------------------------------
# Execution of approved actions (v5.7.0)
# ---------------------------------------------------------------------------


def _claim_for_execution(approval_id: str, db_path=None) -> dict | None:
    """Atomically claim an approved, unexpired, not-yet-dispatched tool action.

    Returns the row when this caller won the claim, else None, so a double
    click or a retry never dispatches the same action twice. The claim is
    committed before the tool runs: if the process dies mid-call the row stays
    ``execution_status = 'claimed'`` (unknown outcome) and is not retried.
    """
    from realize_core.db.schema import get_connection

    now = _now()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """UPDATE approval_queue SET executed_at = ?, updated_at = ?, execution_status = 'claimed'
               WHERE id = ? AND status = 'approved' AND executed_at IS NULL AND action_name IS NOT NULL
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (now, now, approval_id, now),
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

    now = _now()
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE approval_queue SET result_json = ?, error = ?, updated_at = ?, execution_status = ? WHERE id = ?",
            (json.dumps({"output": output}, default=str), error, now, "failed" if error else "succeeded", approval_id),
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
    """Dispatch an approved tool action at most once and record the outcome.

    The action runs through the tool registry without consulting the gate
    again (an operator approved this exact action and parameters). The
    guarantee is one dispatch attempt per approval, not exactly-once effects:
    if the process stops between the claim and storing the result, the row
    stays ``execution_status = 'claimed'`` and a person must check whether the
    action happened. It is never retried automatically. The result is stored
    on the approval row, logged as ``approval_executed``, and a fixed status
    line is posted into the originating conversation.

    Returns:
        ``{"executed": bool, "success": bool, "output": str, "error": str | None}``.
        ``executed`` is False when there was nothing to run (not a tool action,
        not approved, already dispatched, or expired).
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


def _skill_runtime(record: dict) -> dict | None:
    """kb_path / system config / shared config for resuming a skill in the item's venture."""
    from realize_core.governance.context import parse_session_ref

    parsed = parse_session_ref(record.get("session_ref"))
    system_key = parsed[0] if parsed else record.get("venture_key", "")
    from realize_core.engine import load_runtime

    runtime = load_runtime()
    return {
        "kb_path": runtime["kb_path"],
        "system_config": runtime["systems"].get(system_key, {}),
        "shared_config": runtime["shared_config"],
    }


async def _resume_skill_from_approval(record: dict, answer: str) -> str | None:
    """Resume the skill paused at the human step this approval item belongs to."""
    from realize_core.skills.executor import resume_pending_skill, skill_run_for_approval

    pending = skill_run_for_approval(record.get("id", ""))
    if not pending or pending.get("kind") != "human":
        return None  # already answered in chat, or no skill waits on this item
    output = await resume_pending_skill(
        pending.get("user_id", ""), answer, channel="dashboard", run_id=pending["id"], **_skill_runtime(record)
    )
    if output:
        report_to_conversation(record.get("session_ref"), output)
    return output


async def _resume_skill_after_tool(record: dict, execution: dict) -> str | None:
    """Continue the skill whose tool step this approved action was (F10)."""
    from realize_core.skills.executor import resume_after_held_tool, skill_run_for_approval

    pending = skill_run_for_approval(record.get("id", ""))
    if not pending or pending.get("kind") != "tool":
        return None
    output = await resume_after_held_tool(pending["id"], execution, channel="dashboard", **_skill_runtime(record))
    if output:
        report_to_conversation(record.get("session_ref"), output)
    return output


def _action_type(approval_id: str, db_path=None) -> str | None:
    from realize_core.db.schema import get_connection

    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT action_type FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
        return row["action_type"] if row else None
    finally:
        conn.close()


def _stop_paused_skill(record: dict) -> None:
    """Drop the paused skill waiting on this item: a rejected question or action stops the skill."""
    from realize_core.skills.executor import claim_skill_run, skill_run_for_approval

    pending = skill_run_for_approval(record.get("id", ""))
    if pending and claim_skill_run(pending["id"]):
        what = "question" if pending.get("kind") == "human" else "action"
        report_to_conversation(
            record.get("session_ref"), f"The skill was stopped: its {what} was rejected, so nothing after it ran."
        )


async def decide_approval(
    approval_id: str,
    approve: bool,
    decision_note: str | None = None,
    db_path=None,
    *,
    decided_by: str | None = None,
    channel: str | None = None,
) -> dict | None:
    """Decide an approval item and carry out what the decision implies.

    - Tool action, approved: dispatched once (:func:`execute_approved_action`).
    - Tool action, rejected: never runs; the conversation is told.
    - Skill question (``skill_input``): approving with an answer records it as
      ``answered`` (input, not an approval) and resumes the skill; rejecting
      stops the skill.

    Only one decision can win: the transition requires the item to be pending
    and unexpired. ``decided_by`` / ``channel`` are stored on the row.

    Returns ``{"approval": row, "execution": ..., "skill_output": ...}`` or
    None when the item doesn't exist, isn't pending or has expired.
    """
    action_type = _action_type(approval_id, db_path)
    is_question = action_type == "skill_input"
    if action_type == "agent_credential":
        # Never store or relay what was typed: a secret pasted here would land
        # in the DB and the conversation. Credentials go in Setup.
        decision_note = None
    if is_question and approve:
        record = answer_request(approval_id, decision_note or "yes", db_path, answered_by=decided_by, channel=channel)
    elif approve:
        record = approve_request(approval_id, decision_note, db_path, decided_by=decided_by, channel=channel)
    else:
        record = reject_request(approval_id, decision_note, db_path, decided_by=decided_by, channel=channel)
    if record is None:
        return None

    out: dict = {"approval": record, "execution": None, "skill_output": None}
    if is_question:
        if approve:
            out["skill_output"] = await _resume_skill_from_approval(record, decision_note or "yes")
        else:
            _stop_paused_skill(record)
    elif approve and record.get("action_name"):
        out["execution"] = await execute_approved_action(approval_id, db_path=db_path)
        out["skill_output"] = await _resume_skill_after_tool(record, out["execution"])
        await _notify_missions(approval_id, True, out["execution"])
    elif not approve and record.get("action_name"):
        report_to_conversation(
            record.get("session_ref"), f"`{record['action_name']}` was not approved, so it was not done."
        )
        _stop_paused_skill(record)
        await _notify_missions(approval_id, False, None)
    elif action_type in _AGENT_REQUEST_OUTCOMES:
        report_to_conversation(record.get("session_ref"), _agent_request_outcome(action_type, approve, decision_note))
    _record_decision(record, approve, action_type)
    return out


def _record_decision(record: dict, approve: bool, action_type: str | None) -> None:
    """Add the decision to the venture's decision log (STORY-44). Never raises."""
    try:
        from realize_core.governance.decision_log import record_approval_decision

        record_approval_decision(record, approve, action_type=action_type)
    except Exception:
        logger.warning("Decision log write failed for approval %s", record.get("id"), exc_info=True)


async def _notify_missions(approval_id: str, approved: bool, execution: dict | None) -> None:
    """Let a mission step that waits on this approval continue (F11). Never raises."""
    try:
        from realize_core.missions.engine import on_approval_decided

        await on_approval_decided(approval_id, approved, execution)
    except Exception:
        logger.warning("Mission update after approval %s failed", approval_id, exc_info=True)


_AGENT_REQUEST_OUTCOMES = {"agent_decision", "agent_input", "agent_credential"}


def _agent_request_outcome(action_type: str, approve: bool, note: str | None) -> str:
    """What the requesting conversation is told about an agent's request."""
    if action_type == "agent_credential":
        return (
            "The operator says the credential is set up; try again."
            if approve
            else "The operator declined to provide the credential."
        )
    verdict = "approved" if approve else "rejected"
    if action_type == "agent_input":
        verdict = "answered" if approve else "declined"
    return f"The operator {verdict} your request." + (f" Note: {note}" if note else "")
