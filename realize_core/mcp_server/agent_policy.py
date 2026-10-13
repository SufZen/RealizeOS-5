"""
What an outside agent may do over MCP (STORY-37).

An *agent principal* is a caller authenticated with a venture-scoped agent
token (:mod:`realize_core.security.agent_tokens`). People (dashboard users,
the API key, OAuth connectors, JWTs) are not affected by anything here.

Every MCP tool has one rule for agents:

- ``allow`` — reads, and calls that are self-contained or already governed
  (chat runs tools through the ``ToolGate``; ``log_decision`` only proposes).
- ``hold`` — a write that acts on the business. Nothing runs: the call goes
  into the approval queue and runs once, as the agent, after a person
  approves it (:mod:`realize_core.mcp_server.held_writes`).
- ``people_decide`` — approving, rejecting or dismissing. People decide; an
  agent never approves a held write, its own or anyone's.
- ``refuse`` — changes that span every venture or remove a client's brain.
  A venture-scoped agent may not even ask for them: holding them in one
  venture's queue would let a person limited to that venture approve a
  change to all of them.

A tool with no rule here is refused, so a new tool needs a decision before
outside agents can call it.

The dispatcher (:func:`realize_core.mcp_server.server._dispatch`) applies the
rule after the usual RBAC and venture checks.
"""

from __future__ import annotations

from typing import Any

ALLOW = "allow"
HOLD = "hold"
PEOPLE_DECIDE = "people_decide"
REFUSE = "refuse"

#: MCP error code: an outside agent may not approve, reject or dismiss.
CODE_PEOPLE_DECIDE = "MCP_AGENT_CANNOT_DECIDE"
#: MCP error code: an outside agent may not call this tool.
CODE_REFUSED = "MCP_AGENT_REFUSED"

#: The rule for every MCP tool, for agent principals.
AGENT_TOOL_POLICY: dict[str, str] = {
    # Reads (venture scope still applies; tools that span every venture are
    # refused by the venture guard first).
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
            "list_packs",
            "resolve_pack_item",
            "glossary_lookup",
            "list_workflows",
            "list_suggestions",
            "list_approvals",
        ),
        ALLOW,
    ),
    # Self-contained or already governed.
    "realize_chat": ALLOW,  # tools run through the ToolGate, as this agent
    "clear_history": ALLOW,  # the agent's own conversation only
    "log_decision": ALLOW,  # a proposal: a person confirms it in the approval queue
    "tender_register_method": ALLOW,
    "tender_register_submit": ALLOW,
    "request_audit_call": ALLOW,
    # Writes that act on the business: held for a person.
    "run_workflow": HOLD,
    "trigger_skill": HOLD,
    # People decide.
    "approve_request": PEOPLE_DECIDE,
    "reject_request": PEOPLE_DECIDE,
    "approve_suggestion": PEOPLE_DECIDE,
    "dismiss_suggestion": PEOPLE_DECIDE,
    # Span every venture, or remove a client's brain.
    "run_evolution": REFUSE,
    "create_venture": REFUSE,
    "delete_venture": REFUSE,
    "update_setting": REFUSE,
    "reload_agents": REFUSE,
}


def is_agent(user: Any) -> bool:
    """True when the MCP caller is an outside agent (agent token)."""
    from realize_core.security.agent_tokens import has_agent_scope, is_agent_principal

    return is_agent_principal(getattr(user, "user_id", None)) or has_agent_scope(getattr(user, "scopes", None))


def rule_for(name: str) -> str:
    """The rule for tool ``name`` (``refuse`` when it has none)."""
    return AGENT_TOOL_POLICY.get(name, REFUSE)


def refusal(name: str) -> tuple[str, str] | None:
    """``(code, message)`` when an agent may not call ``name`` at all, else None."""
    rule = rule_for(name)
    if rule == PEOPLE_DECIDE:
        return (
            CODE_PEOPLE_DECIDE,
            f"People decide: an outside agent can't call '{name}'. A person approves or rejects in the dashboard.",
        )
    if rule == REFUSE:
        return (
            CODE_REFUSED,
            f"Tool '{name}' isn't available to an outside agent; an owner does this in the dashboard or CLI.",
        )
    return None


def must_hold(name: str) -> bool:
    """True when an agent's call to ``name`` waits for a person's approval."""
    return rule_for(name) == HOLD


def filter_result(name: str, result: Any, user: Any) -> Any:
    """Trim what an agent sees: approval items come back as status summaries.

    Parameters and results of other people's items stay in the dashboard; the
    agent gets the result of its own held writes.
    """
    if name != "list_approvals" or not isinstance(result, dict) or not isinstance(result.get("approvals"), list):
        return result
    from realize_core.mcp_server.held_writes import agent_view

    viewer = getattr(user, "user_id", "")
    return {**result, "approvals": [agent_view(row, viewer) for row in result["approvals"] if isinstance(row, dict)]}
