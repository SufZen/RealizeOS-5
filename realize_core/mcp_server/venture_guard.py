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
    }
)
#: Tools that run a skill by name: the skill's own venture is checked too.
SKILL_TOOLS = frozenset({"run_workflow", "trigger_skill"})
#: Tools checked against the approval's own venture.
APPROVAL_TOOLS = frozenset({"approve_request", "reject_request"})
#: Tools whose output is filtered to the caller's ventures.
FILTERED_LISTS = {"list_systems": "systems", "list_ventures": "ventures"}
#: Tools with no venture data.
ALWAYS_ALLOWED = frozenset({"realize_health"})


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
        ),
        "system:read",
    ),
    **dict.fromkeys(("realize_chat", "clear_history", "run_workflow", "trigger_skill"), "agents:execute"),
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


def _skill_venture(skill_name: str) -> str | None:
    """The venture that owns a skill ('' for global skills, None if unknown).

    Uses the owner the skill was loaded under: skills from a venture's YAML
    don't carry ``system_key`` in their dict.
    """
    from realize_core.skills.detector import GLOBAL_SKILL_OWNERS, find_skill

    found = find_skill(skill_name)
    if found is None:
        return None
    owner = found[0]
    return "" if owner in GLOBAL_SKILL_OWNERS else owner


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
            # The skill runs by name: it must be global or belong to an allowed venture.
            skill_venture = _skill_venture(str(arguments.get("name", "")).strip())
            if skill_venture is None or (skill_venture and skill_venture not in allowed):
                return "Workflow not found"
        return None
    if name in APPROVAL_TOOLS:
        venture = _approval_venture(str(arguments.get("approval_id", "")))
        return None if venture in allowed else "Approval not found"
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
