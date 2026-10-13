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

import asyncio
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

#: ``action_type`` of a write an outside agent asked for over MCP (STORY-37). The
#: row's ``action_name`` is ``mcp:<tool>`` and ``params_json`` holds the call's
#: arguments; approving it runs that MCP tool once, as the agent.
MCP_WRITE_ACTION_TYPE = "mcp_write"

#: ``action_type`` of a request to raise a shared pack's verification (spec 010 §5).
PACK_VERIFY_ACTION_TYPE = "pack_verify"

#: ``action_type`` of a decision made elsewhere that an agent proposes for the
#: decision log (``decision_log.DECISION_LOG_ACTION``, STORY-44).
DECISION_PROPOSAL_ACTION_TYPE = "decision_log"

#: Requests whose outcome changes something every venture shares. Only a
#: global maintainer may approve or reject them, whatever the row's venture
#: (audit N01): a pack's verification level shows on every venture's answers.
GLOBAL_ACTION_TYPES = frozenset({PACK_VERIFY_ACTION_TYPE})

#: Roles that may decide a global request. Owner only: the docs and spec 010
#: §9.4 make raising a shared pack's verification the owner's decision, and
#: ``admin`` is the role without the security and user-management rights; a
#: trust claim shown on every venture's answers is closer to those than to
#: settings.
GLOBAL_MAINTAINER_ROLES = frozenset({"owner"})


class ApprovalForbiddenError(PermissionError):
    """The decider may not decide this approval; nothing was changed."""


@dataclass(frozen=True)
class Decider:
    """Who is deciding an approval, with the authority the decision is checked against.

    Attributes:
        user_id: The authenticated principal, or None with auth off (dev mode).
        role: The principal's role (``owner``, ``admin``, ``operator`` ...).
        allowed_ventures: Ventures the principal is limited to; None means
            every venture.
        is_agent: An outside agent (agent token or stdio session, STORY-37).
        channel: Where the decision came from (dashboard, api, mcp ...).
    """

    user_id: str | None
    role: str | None
    allowed_ventures: frozenset[str] | None
    is_agent: bool = False
    channel: str | None = None

    @property
    def is_global_maintainer(self) -> bool:
        """A person with the owner role and access to every venture."""
        return (
            not self.is_agent and (self.role or "").lower() in GLOBAL_MAINTAINER_ROLES and self.allowed_ventures is None
        )


def authorize_decision(action_type: str | None, decider: Decider | None) -> None:
    """Refuse a decision the decider may not make. Called before the item changes.

    - An outside agent never decides (people decide, STORY-37).
    - A global request (:data:`GLOBAL_ACTION_TYPES`) needs a global
      maintainer; without a decider it is refused (fail closed).

    Raises:
        ApprovalForbiddenError: With a message that can be shown to the caller.
    """
    if decider is not None and decider.is_agent:
        raise ApprovalForbiddenError("People decide: an outside agent can't approve or reject")
    if action_type in GLOBAL_ACTION_TYPES and not (decider is not None and decider.is_global_maintainer):
        raise ApprovalForbiddenError(
            "A pack's verification is shared by every venture: only an owner with access to every "
            "venture can approve or reject it"
        )


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
    """Get the approvals still waiting for a decision (not expired), optionally for one venture."""
    from realize_core.db.schema import get_connection
    from realize_core.governance.approval_status import now_stamp, status_clause

    clause, params = status_clause("pending", now_stamp())
    if venture_key:
        clause += " AND venture_key = ?"
        params.append(venture_key)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            f"SELECT * FROM approval_queue WHERE {clause} ORDER BY created_at DESC",
            params,
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
    *,
    global_authorized: bool = False,
    log_intent: bool = False,
) -> dict | None:
    """Move a pending, unexpired item to ``status`` in one compare-and-set step.

    The UPDATE itself requires ``status = 'pending'`` and an unexpired
    ``expires_at``, so of two concurrent decisions exactly one wins; the other
    gets None. Expired items can't be decided. A global request
    (:data:`GLOBAL_ACTION_TYPES`) only moves when ``global_authorized`` says
    the caller checked the decider (:func:`decide_approval` does), so a direct
    call can't decide one by mistake.

    With ``log_intent`` (:func:`decide_approval`), the intent to add the
    decision to the decision log is stored in the same transaction, so a crash
    right after the decision can't lose the entry (review G-4).
    """
    from realize_core.db.schema import get_connection

    now = _now()
    global_types = sorted(GLOBAL_ACTION_TYPES)
    placeholders = ",".join("?" for _ in global_types)
    conn = get_connection(db_path)
    try:
        if log_intent:
            from realize_core.governance.decision_log import ensure_intent_table

            ensure_intent_table(conn)
        cur = conn.execute(
            f"""UPDATE approval_queue
               SET status = ?, decision_note = ?, decided_at = ?, updated_at = ?,
                   decided_by = ?, decision_channel = ?
               WHERE id = ? AND status = 'pending' AND (expires_at IS NULL OR expires_at > ?)
                 AND (? OR COALESCE(action_type, '') NOT IN ({placeholders}))""",
            (status, decision_note, now, now, decided_by, channel, approval_id, now, global_authorized, *global_types),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return None
        row = conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
        result = dict(row) if row else None
        if log_intent and result is not None:
            from realize_core.governance.decision_log import queue_with_decision

            try:
                queue_with_decision(conn, result, status == "approved", result.get("action_type"))
            except sqlite3.Error:
                # The decision stands; log_decision queues the intent again after this.
                logger.warning("Could not queue the decision-log write for approval %s", approval_id, exc_info=True)
        conn.commit()
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
    global_authorized: bool = False,
    log_intent: bool = False,
) -> dict | None:
    """Approve a pending, unexpired request. Returns the row, or None if it isn't pending or has expired.

    A global request (``pack_verify``) is approved only through
    :func:`decide_approval`, which checks the decider first. ``log_intent``
    stores the decision-log intent with the decision (:func:`decide_approval` does).
    """
    return _decide(
        approval_id,
        "approved",
        decision_note,
        decided_by,
        channel,
        db_path,
        global_authorized=global_authorized,
        log_intent=log_intent,
    )


def reject_request(
    approval_id: str,
    decision_note: str = None,
    db_path=None,
    *,
    decided_by: str | None = None,
    channel: str | None = None,
    global_authorized: bool = False,
    log_intent: bool = False,
) -> dict | None:
    """Reject a pending, unexpired request. Returns the row, or None if it isn't pending or has expired.

    A global request (``pack_verify``) is rejected only through
    :func:`decide_approval`, which checks the decider first. ``log_intent``
    stores the decision-log intent with the decision (:func:`decide_approval` does).
    """
    return _decide(
        approval_id,
        "rejected",
        decision_note,
        decided_by,
        channel,
        db_path,
        global_authorized=global_authorized,
        log_intent=log_intent,
    )


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


def _claim_for_execution(approval_id: str, db_path=None, *, action_type: str | None = None) -> dict | None:
    """Atomically claim an approved, not-yet-dispatched action.

    Returns the row when this caller won the claim, else None, so a double
    click or a retry never dispatches the same action twice. The claim is
    committed before the action runs: if the process dies mid-call the row
    stays ``execution_status = 'claimed'`` (unknown outcome) and is not retried.

    Expiry is not checked again: the decision already required an unexpired
    item, so a person approved it in time. Checking it here made an approval
    given just before expiry never run (review G-2).

    Args:
        approval_id: The approval.
        db_path: Operational DB override.
        action_type: Claim an item of this type that has no tool to run (a
            pack verification). By default only tool actions are claimed.
    """
    from realize_core.db.schema import get_connection

    now = _now()
    if action_type is None:
        which, params = "action_name IS NOT NULL", (now, now, approval_id)
    else:
        which, params = "action_type = ?", (now, now, approval_id, action_type)
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            f"""UPDATE approval_queue SET executed_at = ?, updated_at = ?, execution_status = 'claimed'
               WHERE id = ? AND status = 'approved' AND executed_at IS NULL AND {which}""",
            params,
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


def requester_refusal(row: dict) -> str | None:
    """Why an approved item an outside agent asked for must not run now, or None.

    None when the item was not asked for by an outside agent
    (``requested_by`` isn't an ``agent:`` principal). Otherwise the agent is
    checked again now (:func:`realize_core.mcp_server.held_writes.live_requester`).
    """
    from realize_core.security.agent_tokens import is_agent_principal

    requested_by = row.get("requested_by")
    if not is_agent_principal(requested_by):
        return None
    from realize_core.mcp_server.held_writes import live_requester

    _principal, refusal = live_requester(requested_by, row.get("venture_key") or "")
    return refusal


def _record_refused_execution(approval_id: str, action_type: str, refusal: str, db_path=None) -> dict:
    """Claim an approved item that must not run and record why (a failed execution, nothing run)."""
    row = _claim_for_execution(approval_id, db_path, action_type=action_type)
    if row is None:
        return {"executed": False, "success": False, "output": "", "error": None}
    _store_execution_result(approval_id, "", refusal, db_path)
    try:
        from realize_core.activity.logger import log_event

        log_event(
            venture_key=row["venture_key"],
            actor_type="system",
            actor_id="gate",
            action="approval_execution_failed",
            entity_type="approval",
            entity_id=approval_id,
            details=json.dumps({"action": action_type, "error": refusal}),
        )
    except Exception:
        logger.debug("activity log failed for a refused approval", exc_info=True)
    return {"executed": True, "success": False, "output": "", "error": refusal}


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

    An item an outside agent asked for (``requested_by`` is an agent
    principal: a write held from its chat or its runs, its held MCP write)
    runs only while the agent is still live: a token revoked or expired, agent
    tokens turned off, a removed user or a lost venture records a failed
    execution with the reason, and nothing runs (S3).

    Returns:
        ``{"executed": bool, "success": bool, "output": str, "error": str | None}``.
        ``executed`` is False when there was nothing to run (not a tool action,
        not approved, or already dispatched).
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
    refusal = requester_refusal(row)
    if refusal:
        result_ok, output, error = False, "", refusal
    elif not isinstance(params, dict):
        result_ok, output, error = False, "", "Stored parameters are unreadable"
    elif row.get("action_type") == MCP_WRITE_ACTION_TYPE:
        # An outside agent's held MCP write: same claim, same single dispatch.
        from realize_core.mcp_server.held_writes import run_approved_write

        result_ok, output, error = await run_approved_write(row, params)
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
    decider: Decider | None = None,
) -> dict | None:
    """Decide an approval item and carry out what the decision implies.

    - Tool action, approved: dispatched once (:func:`execute_approved_action`).
      An outside agent's held MCP write (``mcp_write``) is dispatched the same way.
    - Tool action, rejected: never runs; the conversation is told.
    - Skill question (``skill_input``): approving with an answer records it as
      ``answered`` (input, not an approval) and resumes the skill; rejecting
      stops the skill.
    - Pack verification (``pack_verify``), approved: recorded once
      (:func:`_apply_pack_verification`), with the same outcome fields as a
      tool action.

    Authority is checked here, before the item changes, for every caller
    (REST, MCP and anything else): an outside agent never decides, and a
    global request (``pack_verify``) needs ``decider`` to be a global
    maintainer (:func:`authorize_decision`, audit N01). A refused attempt
    leaves the item pending.

    Only one decision can win: the transition requires the item to be pending
    and unexpired. ``decided_by`` / ``channel`` are stored on the row; they
    default to the decider's. Once approved, the action runs even if the item
    expires meanwhile: the person decided in time.

    The decision-log intent is stored with the decision; the entry itself is
    written after the action has run, in a worker thread, so a slow write
    never delays the action (review G-2).

    Returns ``{"approval": row, "execution": ..., "skill_output": ...,
    "decision_log": {"logged", "pending", "error", "decision_id"}}`` or None
    when the item doesn't exist, isn't pending or has expired. After an
    execution, ``approval`` is the row as stored, outcome fields included.

    Raises:
        ApprovalForbiddenError: The decider may not decide this item.
    """
    if decider is not None:
        decided_by = decided_by if decided_by is not None else decider.user_id
        channel = channel if channel is not None else decider.channel
    action_type = _action_type(approval_id, db_path)
    if action_type is None:
        return None
    authorize_decision(action_type, decider)
    global_authorized = action_type in GLOBAL_ACTION_TYPES  # checked just above
    is_question = action_type == "skill_input"
    if action_type == "agent_credential":
        # Never store or relay what was typed: a secret pasted here would land
        # in the DB and the conversation. Credentials go in Setup.
        decision_note = None
    # An outside agent's decision proposal is recorded only while the agent is live (S3).
    proposal_refusal = None
    if approve and action_type == DECISION_PROPOSAL_ACTION_TYPE:
        proposal_refusal = requester_refusal(_get_row(approval_id, db_path) or {})
    if is_question and approve:
        record = answer_request(approval_id, decision_note or "yes", db_path, answered_by=decided_by, channel=channel)
    elif approve:
        record = approve_request(
            approval_id,
            decision_note,
            db_path,
            decided_by=decided_by,
            channel=channel,
            global_authorized=global_authorized,
            log_intent=proposal_refusal is None,
        )
    else:
        record = reject_request(
            approval_id,
            decision_note,
            db_path,
            decided_by=decided_by,
            channel=channel,
            global_authorized=global_authorized,
            log_intent=True,
        )
    if record is None:
        return None

    out: dict = {"approval": record, "execution": None, "skill_output": None, "decision_log": None}
    if proposal_refusal:
        # Approved, but the agent that proposed it is gone: nothing is recorded.
        out["execution"] = _record_refused_execution(
            approval_id, DECISION_PROPOSAL_ACTION_TYPE, proposal_refusal, db_path
        )
        out["approval"] = _get_row(approval_id, db_path) or record
        out["decision_log"] = {"logged": False, "pending": False, "error": proposal_refusal, "decision_id": None}
        return out
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
    elif approve and action_type == PACK_VERIFY_ACTION_TYPE:
        out["execution"] = await _apply_pack_verification(approval_id, db_path)
    if out["execution"] and out["execution"].get("executed"):
        out["approval"] = _get_row(approval_id, db_path) or record
    # The decision log is written once what the decision sets off has run, and off the
    # event loop: a slow write (it also retries other pending writes) must not delay the
    # approved action or block other requests. The intent was stored with the decision
    # (log_intent), so a failure or crash before this line can't lose it (N05, review G-2).
    out["decision_log"] = await asyncio.to_thread(_record_decision, record, approve, action_type, db_path)
    return out


def _get_row(approval_id: str, db_path=None) -> dict | None:
    from realize_core.db.schema import get_connection

    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


async def _apply_pack_verification(approval_id: str, db_path=None) -> dict:
    """Record an approved pack verification once, and store the outcome on the approval (audit N04).

    Same claim, outcome fields and activity events as a tool action
    (:func:`execute_approved_action`): the row is claimed first, then
    ``result_json`` (``{"output": ...}``), ``error`` and ``execution_status``
    (``succeeded`` / ``failed``) are stored. The verification itself is one
    atomic write to the verification state under ``DATA_PATH``; pack files are
    never touched, so a read-only application folder is fine.

    Returns:
        ``{"executed": bool, "success": bool, "output": str, "error": str | None}``.
        ``executed`` is False when the item was already applied or claimed.
    """
    from realize_core.governance.decision_log import _params
    from realize_core.packs.verify import PackVerificationError, apply_verification, describe_result

    row = _claim_for_execution(approval_id, db_path, action_type=PACK_VERIFY_ACTION_TYPE)
    if row is None:
        return {"executed": False, "success": False, "output": "", "error": None}
    try:
        changed = await asyncio.to_thread(
            apply_verification, _params(row), row.get("decided_by") or "unknown", approval_id=approval_id
        )
        ok, output, error = True, describe_result(changed), None
    except (PackVerificationError, OSError) as exc:  # VerificationStateError is an OSError
        logger.warning("Pack verification %s not applied: %s", approval_id, exc)
        ok, output, error = False, "", f"Verification not applied: {exc}"
    _store_execution_result(approval_id, output, error, db_path)
    try:
        from realize_core.activity.logger import log_event

        log_event(
            venture_key=row["venture_key"],
            actor_type="system",
            actor_id="gate",
            action="approval_executed" if ok else "approval_execution_failed",
            entity_type="approval",
            entity_id=approval_id,
            details=json.dumps({"action": PACK_VERIFY_ACTION_TYPE, "error": error}),
        )
    except Exception:
        logger.debug("activity log failed for pack verification", exc_info=True)
    return {"executed": True, "success": ok, "output": output, "error": error}


def _record_decision(record: dict, approve: bool, action_type: str | None, db_path=None) -> dict:
    """Add the decision to the venture's decision log (STORY-44). Never raises.

    The write is durable (N05): a failure stays queued and is retried. Returns
    ``{"logged", "pending", "error", "decision_id"}`` for the decision result.
    """
    try:
        from realize_core.governance.decision_log import log_decision

        return log_decision(record, approve, action_type=action_type, db_path=db_path)
    except Exception as exc:
        logger.warning("Decision log write failed for approval %s", record.get("id"), exc_info=True)
        return {"logged": False, "pending": False, "error": str(exc) or type(exc).__name__, "decision_id": None}


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
