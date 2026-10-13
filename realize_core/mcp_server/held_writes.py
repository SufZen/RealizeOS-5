"""
Held MCP writes from outside agents (STORY-37).

When an agent principal calls a tool whose rule is ``hold``
(:mod:`realize_core.security.agent_access`), nothing runs. The call is
stored in the durable ``approval_queue`` as an ``mcp_write`` item:

- ``action_name`` is ``mcp:<tool>`` and ``params_json`` the call's declared
  arguments (nothing else), naming exactly one of the agent's ventures, with
  ``user_id`` pinned to the agent (it acts as itself);
- ``requested_by`` is the agent principal (``agent:<token id>``), so the
  dashboard and the trail show who asked;
- ``session_ref`` is the agent's own conversation in that venture, which is
  told the outcome.

The agent gets ``{"status": "pending_approval", "approval_id": ...}`` and
follows the item with ``list_approvals``.

A person approves or rejects it in the dashboard (or over REST/MCP as a
person). Approval goes through :func:`realize_core.governance.gates.decide_approval`
and :func:`~realize_core.governance.gates.execute_approved_action`, the same
machinery as held tool actions: the row is claimed in one compare-and-set
step before anything runs, so the write runs at most once, and a row left
``claimed`` after a restart has an unknown outcome and is never re-run.
Just before running, the agent's token is checked again: a token revoked or
expired in the meantime, a removed user or a lost venture means nothing runs.
It runs as the agent, with the agent's narrowed scope, never as the person
who approved it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from realize_core.governance.gates import MCP_WRITE_ACTION_TYPE

logger = logging.getLogger(__name__)

#: ``action_name`` prefix of a held MCP write.
ACTION_PREFIX = "mcp:"
#: How long a held write waits for a person before it expires.
HELD_WRITE_TTL_MINUTES = 24 * 60
#: Arguments that name the venture a held write belongs to.
_VENTURE_ARGS = ("system_key", "venture_key", "venture")
#: An agent can't flood the approval queue: past this many waiting writes it must wait.
MAX_PENDING_PER_AGENT = 25

#: The live ``app.state`` (systems, kb_path, shared_config) of the server that
#: built the MCP server; approved writes run against it.
_app_state: Any = None


def bind_app_state(app_state: Any) -> None:
    """Run approved writes against this app state (called when the MCP server is built)."""
    global _app_state
    _app_state = app_state


def _validator(name: str) -> Callable[[dict[str, Any]], dict[str, Any] | None] | None:
    from realize_core.mcp_server.tools.ops_tools import validate_run_args

    return {"run_workflow": validate_run_args, "trigger_skill": validate_run_args}.get(name)


def _named_ventures(arguments: dict[str, Any]) -> set[str] | None:
    """Every venture the arguments name, or None when one isn't plain text."""
    named = [arguments[k] for k in _VENTURE_ARGS if arguments.get(k) not in (None, "")]
    if not all(isinstance(v, str) for v in named):
        return None
    return set(named)


def _declared(tool: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Only the arguments the tool's input schema declares: nothing else is stored or run."""
    properties = (getattr(tool, "input_schema", None) or {}).get("properties") or {}
    return {key: value for key, value in arguments.items() if key in properties}


def hold_write(tool: Any, arguments: dict[str, Any], user: Any) -> dict[str, Any]:
    """Queue an agent's write for a person's approval instead of running it.

    The caller has already passed RBAC and the venture guard. The call must
    come from a live agent (token or stdio session) and name exactly one of its
    ventures; only the
    tool's declared arguments are kept. Invalid calls are refused here, so a
    person never approves a run that can't start.
    """
    from realize_core.governance.gates import create_approval_request
    from realize_core.mcp_server.venture_guard import caller_ventures
    from realize_core.security.agent_access import CODE_REFUSED
    from realize_core.security.agent_tokens import live_agent, principal_id_for

    name = tool.name
    principal = principal_id_for(getattr(user, "user_id", None), getattr(user, "scopes", None))
    agent = live_agent(principal, known_ventures=_known_ventures(principal))
    if principal is None or agent is None:
        return {"error": "Only a live agent token or stdio session can ask for a held write", "code": CODE_REFUSED}
    arguments = _declared(tool, arguments)
    ventures = _named_ventures(arguments)
    if not ventures or len(ventures) != 1:
        return {"error": f"Tool '{name}' needs exactly one of your ventures as system_key", "code": "MCP_VALIDATION"}
    venture = next(iter(ventures))
    session = caller_ventures(user)
    if venture not in agent.ventures or (session is not None and venture not in session):
        return {"error": f"You don't have access to venture '{venture}'", "code": "MCP_FORBIDDEN"}
    validator = _validator(name)
    invalid = validator(arguments) if validator else None
    if invalid:
        return invalid

    if _pending_count(principal) >= MAX_PENDING_PER_AGENT:
        return {
            "error": f"{MAX_PENDING_PER_AGENT} of your writes are already waiting for approval; wait for a decision",
            "code": "MCP_TOO_MANY_PENDING",
        }
    stored = {**arguments, "user_id": agent.user_id}
    agent_name = agent.name
    approval_id = create_approval_request(
        venture_key=venture,
        agent_key=agent_name,
        action_type=MCP_WRITE_ACTION_TYPE,
        payload={"tool": name, "agent": principal, "agent_name": agent_name},
        expires_minutes=HELD_WRITE_TTL_MINUTES,
        action_name=f"{ACTION_PREFIX}{name}",
        params=stored,
        requested_by=principal,
        session_ref=f"{venture}|{agent.user_id}",
    )
    _log_activity(venture, principal, "mcp_write_held", approval_id, {"tool": name})
    logger.info("Held MCP write %s from %s in %s (approval %s)", name, principal, venture, approval_id)
    return {
        "status": "pending_approval",
        "approval_id": approval_id,
        "tool": name,
        "venture_key": venture,
        "message": (
            "Held for a person to approve. Nothing has run yet. "
            "Follow it with list_approvals (venture_key and approval_id)."
        ),
    }


def _pending_count(principal: str) -> int:
    """How many of this agent's held writes are waiting for a person."""
    from realize_core.db.schema import get_connection

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT COUNT(*) FROM approval_queue
               WHERE requested_by = ? AND action_type = ? AND status = 'pending'
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (principal, MCP_WRITE_ACTION_TYPE, now),
        ).fetchone()
    finally:
        conn.close()
    return int(row[0]) if row else 0


def _log_activity(venture: str, actor: str, action: str, approval_id: str, details: dict[str, Any]) -> None:
    from realize_core.activity.logger import log_event  # never raises

    log_event(
        venture_key=venture,
        actor_type="agent",
        actor_id=actor,
        action=action,
        entity_type="approval",
        entity_id=approval_id,
        details=json.dumps(details),
    )


def _runtime_state() -> Any:
    """The app state approved writes run against: the live one, else loaded from config."""
    if _app_state is not None and getattr(_app_state, "systems", None) is not None:
        return _app_state
    from realize_core.engine import load_runtime

    runtime = load_runtime()
    return SimpleNamespace(
        config=runtime["config"],
        systems=runtime["systems"],
        kb_path=runtime["kb_path"],
        shared_config=runtime["shared_config"],
    )


def _known_ventures(principal: str | None) -> list[str]:
    """Configured venture keys, for a stdio session (an unrestricted user's agent may use any of them)."""
    from realize_core.security.agent_tokens import STDIO_PRINCIPAL_PREFIX

    if not (principal or "").startswith(STDIO_PRINCIPAL_PREFIX):
        return []
    systems = getattr(_runtime_state(), "systems", None)
    return list(systems) if isinstance(systems, dict) else []


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return repr(value)


async def run_approved_write(row: dict, params: dict[str, Any]) -> tuple[bool, str, str | None]:
    """Run a claimed, approved ``mcp_write`` item once, as the agent. Never raises.

    Called by :func:`realize_core.governance.gates.execute_approved_action`
    after it has claimed the row. Returns ``(success, output, error)``.
    """
    from realize_api.dependencies import CurrentUser

    from realize_core.mcp_server import venture_guard
    from realize_core.mcp_server.registry import get_registry
    from realize_core.security.agent_access import must_hold
    from realize_core.security.agent_tokens import live_agent

    action = str(row.get("action_name") or "")
    name = action[len(ACTION_PREFIX) :] if action.startswith(ACTION_PREFIX) else ""
    tool = get_registry().get(name)
    if not must_hold(name) or tool is None:
        return False, "", f"'{action}' is not a held MCP write; nothing was done"

    # The agent's own, current, narrowed identity — never the approver's.
    requested_by = row.get("requested_by")
    principal = live_agent(requested_by, known_ventures=_known_ventures(requested_by))
    if principal is None:
        return (
            False,
            "",
            "The agent's token was revoked or expired, or its user removed, before this ran; nothing was done",
        )
    venture = row.get("venture_key") or ""
    if venture not in principal.ventures:
        return False, "", f"The agent no longer has access to venture '{venture}'; nothing was done"
    # Run exactly what was approved: the declared arguments, all in the approval's venture.
    arguments = _declared(tool, params)
    if _named_ventures(arguments) != {venture}:
        return False, "", f"The stored call doesn't name venture '{venture}' alone; nothing was done"
    refused = venture_guard.permission_refusal(name, principal.role) or venture_guard.check_call(
        name, arguments, principal.ventures
    )
    if refused:
        return False, "", f"{refused}; nothing was done"

    user = CurrentUser(user_id=principal.user_id, role=principal.role, scopes=principal.scopes)
    arguments["user_id"] = principal.user_id
    try:
        result = await tool.handler(arguments, _runtime_state(), user)
    except Exception as exc:  # any tool failure is recorded on the item, never re-run
        logger.exception("Held MCP write %s (%s) failed", row.get("id"), name)
        _audit_execution(principal.user_id, name, row, ok=False)
        return False, "", f"{name} failed: {str(exc)[:300]}"

    if isinstance(result, dict) and result.get("error"):
        _audit_execution(principal.user_id, name, row, ok=False)
        return False, "", str(result["error"])[:500]
    _audit_execution(principal.user_id, name, row, ok=True)
    if isinstance(result, dict) and isinstance(result.get("output"), str):
        return True, result["output"], None
    return True, _to_text(result), None


def _audit_execution(user_id: str, name: str, row: dict, *, ok: bool) -> None:
    try:
        from realize_core.security.audit import get_audit_logger

        get_audit_logger().log(
            user_id=user_id,
            action=f"mcp.{name}",
            outcome="success" if ok else "error",
            channel="mcp",
            system_key=row.get("venture_key") or "",
            resource_type="mcp_tool",
            resource_id=name,
            metadata={"approval_id": row.get("id"), "approved_by": row.get("decided_by"), "held": True},
        )
    except (OSError, ValueError, TypeError, RuntimeError, ImportError):
        logger.warning("Audit log write failed for held MCP write %s", row.get("id"), exc_info=True)


# ---------------------------------------------------------------------------
# What an agent sees when it follows an item
# ---------------------------------------------------------------------------

_SUMMARY_FIELDS = (
    "id",
    "venture_key",
    "agent_key",
    "action_type",
    "action_name",
    "status",
    "requested_by",
    "created_at",
    "decided_at",
    "decided_by",
    "expires_at",
    "executed_at",
    "execution_status",
)


def describe(row: dict) -> tuple[str, str]:
    """``(outcome, note)``: a truthful status for an approval item, also after a restart."""
    status = row.get("status")
    if status == "pending":
        expires_at = row.get("expires_at")
        # approval_queue stamps sort as text (same format as gates.create_approval_request).
        if expires_at and expires_at <= datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"):
            return "expired", "No one decided in time, so nothing was done."
        return "pending_approval", "Waiting for a person to approve or reject it. Nothing has run."
    if status == "rejected":
        return "rejected", "A person rejected it, so nothing was done."
    if status == "expired":
        return "expired", "No one decided in time, so nothing was done."
    if status == "answered":
        return "answered", "A person answered it."
    if status != "approved":
        return str(status or "unknown"), ""
    execution = row.get("execution_status")
    if execution == "succeeded":
        return "succeeded", "Approved and done."
    if execution == "failed":
        return "failed", "Approved, but it failed or was stopped before running. It is not retried."
    if execution == "claimed":
        return (
            "unknown_outcome",
            "Approved and started, but no result is recorded yet. If the server restarted while it ran, "
            "the outcome is unknown: it is never re-run automatically, and a person has to check.",
        )
    if row.get("action_name"):
        return "approved_not_started", "Approved, but it has not started. It will not start on its own later."
    return "approved", "Approved."


def agent_result(name: str, result: Any, user: Any) -> Any:
    """What an agent gets back from a tool: approval items come back as status summaries."""
    if name != "list_approvals" or not isinstance(result, dict) or not isinstance(result.get("approvals"), list):
        return result
    from realize_core.security.agent_tokens import principal_id_for

    viewer = principal_id_for(getattr(user, "user_id", None), getattr(user, "scopes", None)) or ""
    return {**result, "approvals": [agent_view(row, viewer) for row in result["approvals"] if isinstance(row, dict)]}


def agent_view(row: dict, viewer: str) -> dict:
    """An approval item as an outside agent sees it: status, not other people's contents.

    The output (or error) of the agent's own held write is included.
    """
    view = {key: row.get(key) for key in _SUMMARY_FIELDS}
    view["outcome"], view["outcome_note"] = describe(row)
    own = bool(viewer) and row.get("requested_by") == viewer and row.get("action_type") == MCP_WRITE_ACTION_TYPE
    if own and row.get("execution_status") in ("succeeded", "failed"):
        try:
            stored = json.loads(row.get("result_json") or "{}")
        except (TypeError, ValueError):
            stored = {}
        view["result"] = stored.get("output") if isinstance(stored, dict) else None
        view["error"] = row.get("error")
    return view
