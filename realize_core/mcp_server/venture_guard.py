"""
Venture scope for MCP tool calls (STORY-18).

The REST API applies venture scope per route; MCP tools call the core
directly, so the dispatcher checks here instead. For a caller limited to some
ventures (``users.yaml`` ``ventures`` or ``venture:<key>`` token scopes) the
rule is an allowlist — tools that span every venture are refused:

- tools named in :data:`NEEDS_VENTURE` must name a venture the caller may see;
- ``approve_request`` / ``reject_request`` must target an approval in one;
- ``list_systems`` / ``list_ventures`` are filtered to those ventures;
- ``realize_health`` is allowed; every other tool is refused.

Callers with no venture limit (owners, API-key integrations, dev mode) are
unaffected.
"""

from __future__ import annotations

from typing import Any

#: Arguments that name a venture.
VENTURE_ARGS = ("system_key", "venture_key", "venture")

#: Tools a venture-limited caller may use when they name an allowed venture.
NEEDS_VENTURE = frozenset(
    {
        "realize_chat",
        "get_system",
        "list_agents",
        "list_skills",
        "get_history",
        "clear_history",
        "get_session",
        "kb_search",
        "venture_kb_search",
        "list_approvals",
        "list_workflows",
        "run_workflow",
        "trigger_skill",
        "list_packs",
        "resolve_pack_item",
        "glossary_lookup",
        "log_decision",
    }
)
#: Tools that run a skill by name: the skill's own venture is checked too.
SKILL_TOOLS = frozenset({"run_workflow", "trigger_skill"})
#: Tools checked against the approval's own venture.
APPROVAL_TOOLS = frozenset({"approve_request", "reject_request"})
#: Tools whose output is filtered to the caller's ventures.
FILTERED_LISTS = {"list_systems": "systems", "list_ventures": "ventures"}
#: Tools with no venture data.
ALWAYS_ALLOWED = frozenset({"realize_health", "tender_register_method", "tender_register_submit", "request_audit_call"})


#: The RBAC permission each MCP tool needs — the same rules as the REST API
#: (chat runs agents and tools; decisions need approval rights).
TOOL_PERMISSIONS = {
    **dict.fromkeys(
        (
            "realize_health",
            "realize_status",
            "list_systems",
            "get_system",
            "list_agents",
            "list_skills",
            "get_history",
            "get_session",
            "kb_search",
            "venture_kb_search",
            "kb_get_document",
            "list_ventures",
            "list_workflows",
            "list_suggestions",
            "list_approvals",
            "list_packs",
            "resolve_pack_item",
            "glossary_lookup",
            "tender_register_method",
            "tender_register_submit",
            "request_audit_call",
        ),
        "system:read",
    ),
    **dict.fromkeys(
        ("realize_chat", "clear_history", "run_workflow", "trigger_skill", "log_decision"), "agents:execute"
    ),
    **dict.fromkeys(
        ("approve_request", "reject_request", "approve_suggestion", "dismiss_suggestion"), "pipeline:approve"
    ),
    **dict.fromkeys(
        ("run_evolution", "create_venture", "delete_venture", "update_setting", "reload_agents"), "system:manage"
    ),
}


def is_rbac_role(role: str | None) -> bool:
    """True for roles RBAC defines (owner, admin, operator, user, viewer, guest)."""
    from realize_core.security.rbac import get_rbac_manager

    return bool(role) and get_rbac_manager().get_role(role.lower()) is not None


def permission_refusal(name: str, role: str | None) -> str | None:
    """Why ``role`` may not call tool ``name`` under RBAC, or None when it may.

    Returns None for roles RBAC doesn't know (the MCP-only ``editor`` role),
    which keep the tool-family scope check. Unknown tools need ``system:manage``.
    """
    from realize_core.security.rbac import get_rbac_manager

    if not is_rbac_role(role):
        return None
    rbac = get_rbac_manager()
    permission = TOOL_PERMISSIONS.get(name, "system:manage")
    if rbac.check_access(role.lower(), permission).allowed:
        return None
    return f"Tool '{name}' needs '{permission}'; role '{role}' doesn't have it"


def caller_ventures(user: Any) -> frozenset[str] | None:
    """Ventures an MCP caller may use, or None for all."""
    from realize_core.security.venture_scope import allowed_ventures

    return allowed_ventures(getattr(user, "user_id", None), getattr(user, "scopes", None))


def _approval_venture(approval_id: str) -> str | None:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        row = conn.execute("SELECT venture_key FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
    finally:
        conn.close()
    return row["venture_key"] if row else None


def _skill_venture(skill_name: str, venture: str | None) -> str | None:
    """The venture that owns the skill a run for ``venture`` would use ('' for shared or global, None if none).

    The skill is looked up for the venture the call names: its own copy, else
    a shared or global one, never another venture's (two ventures can each
    have a skill with the same name). Uses the owner the skill was loaded
    under: skills from a venture's YAML don't carry ``system_key`` in their dict.
    """
    from realize_core.skills.detector import GLOBAL_SKILL_OWNERS, find_skill

    found = find_skill(skill_name, venture or None)
    if found is None:
        return None
    owner = found[0]
    return "" if owner in GLOBAL_SKILL_OWNERS else owner


def spans_every_venture(name: str, allowed: frozenset[str] | None) -> bool:
    """True when a caller limited to ``allowed`` is refused ``name`` whatever its arguments.

    Such tools span every venture (admin, evolution, cross-venture KB);
    ``tools/list`` leaves them out for venture-limited callers. Callers
    without a venture limit (``allowed`` None) are never refused here.
    """
    if allowed is None:
        return False
    return not (name in ALWAYS_ALLOWED or name in FILTERED_LISTS or name in NEEDS_VENTURE or name in APPROVAL_TOOLS)


def check_call(name: str, arguments: dict[str, Any], allowed: frozenset[str] | None) -> str | None:
    """Return why a call is refused, or None when it may run."""
    if allowed is None:
        return None
    named = [arguments.get(k) for k in VENTURE_ARGS if arguments.get(k) not in (None, "")]
    for venture in named:
        # Exact, plain-text match only: anything else is refused, never coerced.
        if not isinstance(venture, str) or venture not in allowed:
            return f"You don't have access to venture '{venture}'"
    if name in ALWAYS_ALLOWED or name in FILTERED_LISTS:
        return None
    if name in NEEDS_VENTURE:
        if not named:
            return f"Tool '{name}' needs one of your ventures as an argument"
        if name in SKILL_TOOLS:
            # The skill runs by name for the venture the call names (system_key): that
            # venture must have it, or it must be shared or global.
            run_for = arguments.get("system_key")
            skill_venture = _skill_venture(
                str(arguments.get("name", "")).strip(), run_for if isinstance(run_for, str) else None
            )
            if skill_venture is None or (skill_venture and skill_venture not in allowed):
                return "Workflow not found"
        return None
    if name in APPROVAL_TOOLS:
        venture = _approval_venture(str(arguments.get("approval_id", "")))
        return None if venture in allowed else "Approval not found"
    # Everything else spans every venture (see spans_every_venture).
    return f"Tool '{name}' spans every venture; ask an owner or admin"


def filter_result(name: str, result: Any, allowed: frozenset[str] | None) -> Any:
    """Drop ventures the caller may not see from listing results."""
    key = FILTERED_LISTS.get(name)
    if allowed is None or key is None or not isinstance(result, dict):
        return result
    items = result.get(key)
    if not isinstance(items, list):
        return result
    kept = [i for i in items if isinstance(i, dict) and i.get("key") in allowed]
    return {**result, key: kept}
