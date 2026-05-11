"""Operational tools — gated by ``mcp.expose_ops``.

Surface the operational layer of RealizeOS to external agents:
workflow CRUD/run, skill trigger, evolution gap analysis, approval
queue. Wraps existing handlers in
:mod:`realize_api.routes.workflows`,
:mod:`realize_api.routes.evolution`, and
:mod:`realize_api.routes.approvals`. No duplicated business logic.

Scope policy (per architecture doc):

* read tools (``list_*``, ``get_*``)               → ``read``
* state-changing tools (``run_*``, ``trigger_*``,  → ``editor``
  ``approve_*``, ``dismiss_*``, ``reject_*``)
"""

from __future__ import annotations

import logging
from typing import Any

from realize_api.dependencies import CurrentUser

from realize_core.mcp_server.registry import MCPTool, ToolRegistry

logger = logging.getLogger(__name__)

#: Cap workflow / skill input length (mirrors chat MAX_MESSAGE_LENGTH).
MAX_INPUT_CHARS = 4096


# ---------------------------------------------------------------------------
# list_workflows / list_skills
# ---------------------------------------------------------------------------

LIST_WORKFLOWS_SCHEMA = {
    "type": "object",
    "properties": {
        "system_key": {
            "type": ["string", "null"],
            "description": "Optional system filter. Omit for all systems.",
        },
    },
    "additionalProperties": False,
}


async def list_workflows(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """List registered workflows / skills — mirrors ``GET /api/workflows``."""
    try:
        from realize_core.skills.detector import get_all_skills

        skills = get_all_skills()
    except Exception as exc:
        logger.warning("list_workflows failed: %s", exc)
        return {"workflows": [], "total": 0, "error": str(exc)[:200], "code": "MCP_INTERNAL"}

    system_key = args.get("system_key") or None
    if system_key:
        skills = [s for s in skills if (s.get("system_key", "") or "") in (system_key, "")]

    return {
        "workflows": [
            {
                "name": s.get("name", ""),
                "description": s.get("description", ""),
                "triggers": s.get("triggers", []),
                "version": s.get("_version", 1),
                "system_key": s.get("system_key", ""),
                "enabled": s.get("enabled", True),
                "steps_count": len(s.get("steps", [])),
            }
            for s in skills
        ],
        "total": len(skills),
    }


# ---------------------------------------------------------------------------
# run_workflow / trigger_skill — both invoke a named skill against an input
# ---------------------------------------------------------------------------

RUN_WORKFLOW_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Workflow / skill name."},
        "input_text": {
            "type": "string",
            "description": "Input message the skill will execute against.",
            "maxLength": MAX_INPUT_CHARS,
        },
        "system_key": {
            "type": "string",
            "description": "Target system key. Defaults to the skill's home system.",
        },
        "user_id": {
            "type": "string",
            "description": "Caller id for memory + audit. Defaults to MCP user id.",
        },
    },
    "required": ["name", "input_text"],
    "additionalProperties": False,
}


async def _run_skill(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    name = (args.get("name") or "").strip()
    input_text = (args.get("input_text") or "").strip()
    if not name:
        return {"error": "Workflow name is required", "code": "MCP_VALIDATION"}
    if not input_text:
        return {"error": "input_text is required", "code": "MCP_VALIDATION"}
    if len(input_text) > MAX_INPUT_CHARS:
        return {
            "error": f"input_text too long ({len(input_text)} chars, max {MAX_INPUT_CHARS}).",
            "code": "MCP_VALIDATION",
        }

    try:
        from realize_core.skills.detector import get_skill_by_name
        from realize_core.skills.executor import execute_skill
    except ImportError as exc:
        return {"error": f"Skills module unavailable: {exc}", "code": "MCP_INTERNAL"}

    skill = get_skill_by_name(name)
    if not skill:
        return {"error": f"Workflow '{name}' not found", "code": "MCP_NOT_FOUND"}

    system_key = (args.get("system_key") or skill.get("system_key") or "").strip() or "default"
    user_id = (args.get("user_id") or user.user_id or "mcp-user").strip()

    systems = getattr(app_state, "systems", {}) or {}
    system_config = systems.get(system_key)
    shared_config = getattr(app_state, "shared_config", None)
    kb_path = getattr(app_state, "kb_path", None)

    try:
        output = await execute_skill(
            skill=skill,
            user_message=input_text,
            system_key=system_key,
            user_id=user_id,
            kb_path=kb_path,
            system_config=system_config,
            shared_config=shared_config,
            channel="mcp",
        )
    except Exception as exc:
        logger.exception("run_workflow %r failed", name)
        return {"error": f"Workflow execution failed: {exc}", "code": "MCP_INTERNAL"}

    return {
        "name": name,
        "system_key": system_key,
        "user_id": user_id,
        "output": output,
    }


async def run_workflow(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Execute a workflow / skill by name with an input message."""
    return await _run_skill(args, app_state, user)


async def trigger_skill(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Alias for ``run_workflow`` — matches existing public realizeos_* naming."""
    return await _run_skill(args, app_state, user)


# ---------------------------------------------------------------------------
# run_evolution + suggestions
# ---------------------------------------------------------------------------

RUN_EVOLUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "days": {
            "type": "integer",
            "minimum": 1,
            "maximum": 90,
            "default": 7,
            "description": "Look-back window for gap analysis.",
        }
    },
    "additionalProperties": False,
}


async def run_evolution(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Trigger an evolution gap-analysis pass — same as the autopilot cycle."""
    days = int(args.get("days") or 7)
    if days < 1 or days > 90:
        return {"error": "days must be between 1 and 90", "code": "MCP_VALIDATION"}

    try:
        from realize_core.evolution.gap_detector import run_gap_analysis
    except ImportError as exc:
        return {"error": f"Evolution module unavailable: {exc}", "code": "MCP_INTERNAL"}

    try:
        suggestions = await run_gap_analysis(days=days)
    except Exception as exc:
        logger.exception("run_evolution failed")
        return {"error": f"Gap analysis failed: {exc}", "code": "MCP_INTERNAL"}

    return {"days": days, "count": len(suggestions), "suggestions": suggestions}


LIST_SUGGESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": ["string", "null"],
            "description": "Optional status filter (pending | approved | applied | rejected).",
        },
    },
    "additionalProperties": False,
}


async def list_suggestions(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """List evolution proposals — mirrors ``GET /api/evolution/suggestions``."""
    try:
        from realize_api.routes.evolution import _get_engine
    except ImportError as exc:
        return {"error": f"Evolution module unavailable: {exc}", "code": "MCP_INTERNAL"}

    engine = _get_engine()
    status = (args.get("status") or "").strip() or None

    proposals: list[dict[str, Any]] = []
    for p in engine._proposals.values():
        if status and p.status.value != status:
            continue
        proposals.append(
            {
                "id": p.id,
                "type": p.evolution_type.value,
                "title": p.title,
                "description": p.description,
                "risk_level": p.risk_level.value,
                "status": p.status.value,
                "priority": p.priority,
                "source": p.source,
                "created_at": p.created_at,
            }
        )

    proposals.sort(key=lambda x: (-x["priority"], -x["created_at"]))
    return {
        "suggestions": proposals,
        "total": len(proposals),
        "pending": sum(1 for p in proposals if p["status"] == "pending"),
    }


APPROVE_SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {"suggestion_id": {"type": "string"}},
    "required": ["suggestion_id"],
    "additionalProperties": False,
}


async def approve_suggestion(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Approve and apply an evolution suggestion."""
    try:
        from realize_api.routes.evolution import _get_engine
    except ImportError as exc:
        return {"error": f"Evolution module unavailable: {exc}", "code": "MCP_INTERNAL"}

    engine = _get_engine()
    suggestion_id = (args.get("suggestion_id") or "").strip()
    if not suggestion_id:
        return {"error": "suggestion_id is required", "code": "MCP_VALIDATION"}

    proposal = engine._proposals.get(suggestion_id)
    if not proposal:
        return {"error": "Suggestion not found", "code": "MCP_NOT_FOUND"}

    if proposal.status.value != "pending" and not engine.approve(suggestion_id):
        return {
            "error": f"Suggestion is already {proposal.status.value}",
            "code": "MCP_CONFLICT",
        }

    # First-call approve path: engine.approve returns False only when
    # it was already non-pending; otherwise toggle to approved and apply.
    if proposal.status.value == "pending":
        engine.approve(suggestion_id)
    if not engine.apply(suggestion_id):
        return {
            "error": "Failed to apply suggestion (rate limit or error)",
            "code": "MCP_INTERNAL",
        }

    return {"id": suggestion_id, "status": "applied", "title": proposal.title}


DISMISS_SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestion_id": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["suggestion_id"],
    "additionalProperties": False,
}


async def dismiss_suggestion(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Dismiss (reject) an evolution suggestion."""
    try:
        from realize_api.routes.evolution import _get_engine
    except ImportError as exc:
        return {"error": f"Evolution module unavailable: {exc}", "code": "MCP_INTERNAL"}

    engine = _get_engine()
    suggestion_id = (args.get("suggestion_id") or "").strip()
    if not suggestion_id:
        return {"error": "suggestion_id is required", "code": "MCP_VALIDATION"}

    proposal = engine._proposals.get(suggestion_id)
    if not proposal:
        return {"error": "Suggestion not found", "code": "MCP_NOT_FOUND"}

    if not engine.reject(suggestion_id, reason=(args.get("reason") or "")):
        return {
            "error": f"Suggestion is already {proposal.status.value}",
            "code": "MCP_CONFLICT",
        }

    return {"id": suggestion_id, "status": "rejected"}


# ---------------------------------------------------------------------------
# Approval queue
# ---------------------------------------------------------------------------

LIST_APPROVALS_SCHEMA = {
    "type": "object",
    "properties": {
        "venture_key": {"type": ["string", "null"]},
        "status": {"type": "string", "default": "pending"},
    },
    "additionalProperties": False,
}


async def list_approvals(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """List approval queue rows — mirrors ``GET /api/approvals``."""
    try:
        from realize_core.db.schema import get_connection
    except ImportError as exc:
        return {"error": f"DB module unavailable: {exc}", "code": "MCP_INTERNAL"}

    status = (args.get("status") or "pending").strip()
    venture_key = (args.get("venture_key") or "").strip() or None

    conn = get_connection()
    try:
        clauses, params = [], []
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
    except Exception as exc:
        logger.warning("list_approvals failed: %s", exc)
        return {"approvals": [], "error": str(exc)[:200], "code": "MCP_INTERNAL"}
    finally:
        try:
            conn.close()
        except Exception:
            pass


APPROVE_REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "approval_id": {"type": "string"},
        "decision_note": {"type": "string"},
    },
    "required": ["approval_id"],
    "additionalProperties": False,
}


async def approve_request(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Approve a pending request in the approval queue."""
    try:
        from realize_core.governance.gates import approve_request as _approve
    except ImportError as exc:
        return {"error": f"Governance module unavailable: {exc}", "code": "MCP_INTERNAL"}

    approval_id = (args.get("approval_id") or "").strip()
    if not approval_id:
        return {"error": "approval_id is required", "code": "MCP_VALIDATION"}
    result = _approve(approval_id, decision_note=args.get("decision_note") or None)
    if result is None:
        return {"error": "Approval not found or not pending", "code": "MCP_NOT_FOUND"}
    return result


async def reject_request(args: dict[str, Any], app_state: Any, user: CurrentUser) -> Any:
    """Reject a pending request in the approval queue."""
    try:
        from realize_core.governance.gates import reject_request as _reject
    except ImportError as exc:
        return {"error": f"Governance module unavailable: {exc}", "code": "MCP_INTERNAL"}

    approval_id = (args.get("approval_id") or "").strip()
    if not approval_id:
        return {"error": "approval_id is required", "code": "MCP_VALIDATION"}
    result = _reject(approval_id, decision_note=args.get("decision_note") or None)
    if result is None:
        return {"error": "Approval not found or not pending", "code": "MCP_NOT_FOUND"}
    return result


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="list_workflows",
        family="ops",
        description="List registered workflows / skills, optionally filtered by system.",
        input_schema=LIST_WORKFLOWS_SCHEMA,
        scope="read",
        handler=list_workflows,
    ),
    MCPTool(
        name="run_workflow",
        family="ops",
        description="Execute a workflow / skill by name against an input message.",
        input_schema=RUN_WORKFLOW_SCHEMA,
        scope="editor",
        handler=run_workflow,
    ),
    MCPTool(
        name="trigger_skill",
        family="ops",
        description="Alias for run_workflow — matches public realizeos_* naming.",
        input_schema=RUN_WORKFLOW_SCHEMA,
        scope="editor",
        handler=trigger_skill,
    ),
    MCPTool(
        name="run_evolution",
        family="ops",
        description="Trigger an evolution gap-analysis pass over recent interactions.",
        input_schema=RUN_EVOLUTION_SCHEMA,
        scope="editor",
        handler=run_evolution,
    ),
    MCPTool(
        name="list_suggestions",
        family="ops",
        description="List evolution proposals (optionally filtered by status).",
        input_schema=LIST_SUGGESTIONS_SCHEMA,
        scope="read",
        handler=list_suggestions,
    ),
    MCPTool(
        name="approve_suggestion",
        family="ops",
        description="Approve and apply an evolution suggestion.",
        input_schema=APPROVE_SUGGESTION_SCHEMA,
        scope="editor",
        handler=approve_suggestion,
    ),
    MCPTool(
        name="dismiss_suggestion",
        family="ops",
        description="Dismiss (reject) an evolution suggestion.",
        input_schema=DISMISS_SUGGESTION_SCHEMA,
        scope="editor",
        handler=dismiss_suggestion,
    ),
    MCPTool(
        name="list_approvals",
        family="ops",
        description="List human-approval-queue rows (default: pending).",
        input_schema=LIST_APPROVALS_SCHEMA,
        scope="read",
        handler=list_approvals,
    ),
    MCPTool(
        name="approve_request",
        family="ops",
        description="Approve a pending request in the approval queue.",
        input_schema=APPROVE_REQUEST_SCHEMA,
        scope="editor",
        handler=approve_request,
    ),
    MCPTool(
        name="reject_request",
        family="ops",
        description="Reject a pending request in the approval queue.",
        input_schema=APPROVE_REQUEST_SCHEMA,
        scope="editor",
        handler=reject_request,
    ),
)


def register(registry: ToolRegistry) -> None:
    """Register every ops tool with the shared registry."""
    for tool in _TOOLS:
        registry.register(tool)
