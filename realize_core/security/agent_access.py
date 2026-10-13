"""
What an outside agent may do, on every surface (STORY-37).

One predicate and one rule set, used by both the REST guard
(:func:`realize_api.dependencies.enforce_access`) and the MCP dispatcher
(:func:`realize_core.mcp_server.server._dispatch`), so the two can't drift.

**Who is an outside agent.** A caller authenticated with a venture-scoped
agent token (:mod:`realize_core.security.agent_tokens`): its user id is
``agent:<token id>`` and its scopes carry ``agent:<token id>``. Only the auth
middleware sets these, after verifying the token against its stored hash.
A local stdio session (``realize-os mcp stdio``) is one too: its client is
always an AI agent, and the stdio entry point marks it with the
``agent:stdio`` scope server-side. A JWT, an ``X-User-ID`` header or a
``users.yaml`` entry can't claim a marker (they are refused or ignored), so
:func:`is_agent` can trust it. People (dashboard sessions, the API key,
OAuth connectors, JWTs) are never agents.

**Rules.** Every action gets one of four rules:

- ``allow`` — reads within the agent's ventures, and calls that are
  self-contained or already governed (chat runs tools through the
  ``ToolGate``; ``log_decision`` only proposes).
- ``hold`` — a write that acts on the business. Over MCP it is queued for a
  person (:mod:`realize_core.mcp_server.held_writes`). REST has no hold path,
  so over REST every such write is refused and the agent is pointed to MCP.
- ``people_decide`` — approving, rejecting or dismissing, on any surface.
  People decide; an agent never approves a held write, its own or anyone's.
- ``refuse`` — anything else, including changes that span every venture or
  remove a client's brain, and any tool or route nobody has ruled on.

Deny by default: an MCP tool missing from :data:`MCP_TOOL_RULES` (a new
tool, or a name that differs in case or spacing) is refused.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

ALLOW = "allow"
HOLD = "hold"
PEOPLE_DECIDE = "people_decide"
REFUSE = "refuse"

#: Error code when an agent tries to approve, reject or dismiss.
CODE_PEOPLE_DECIDE = "MCP_AGENT_CANNOT_DECIDE"
#: Error code when an agent may not call a tool or make a change.
CODE_REFUSED = "MCP_AGENT_REFUSED"

PEOPLE_DECIDE_MESSAGE = "People decide: an outside agent can't approve, reject or dismiss"
REST_WRITE_MESSAGE = "An outside agent makes changes through MCP, where a person approves them first"

#: The rule for every MCP tool, for outside agents.
MCP_TOOL_RULES: dict[str, str] = {
    # Reads (the venture guard still refuses tools that span every venture).
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

#: Methods that only read. Every other method (POST, PUT, PATCH, DELETE, and
#: any method nobody listed) is a write.
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
#: The only REST writes an agent may make, by method and routed path template:
#: chatting, and clearing its own conversation. Everything else is refused,
#: including POST routes that read (search, export, reindex).
REST_AGENT_WRITES = frozenset(
    {
        ("POST", "/api/chat"),
        ("POST", "/api/chat/stream"),
        ("DELETE", "/api/conversations/{system_key}/{user_id}"),
    }
)
#: REST decisions on held actions and proposals, by routed path template.
REST_DECISION_ROUTES = frozenset(
    {
        "/api/approvals/{approval_id}/approve",
        "/api/approvals/{approval_id}/reject",
        "/api/dreams/{proposal_id}/approve",
        "/api/dreams/{proposal_id}/reject",
        "/api/evolution/suggestions/{suggestion_id}/approve",
        "/api/evolution/suggestions/{suggestion_id}/dismiss",
    }
)


def is_agent(user_id: str | None, scopes: Iterable[str] | None = None) -> bool:
    """True when the caller is an outside agent (verified agent token)."""
    from realize_core.security.agent_tokens import has_agent_scope, is_agent_principal

    return is_agent_principal(user_id) or has_agent_scope(scopes)


def is_agent_subject(subject: Any) -> bool:
    """:func:`is_agent` for anything with ``user_id`` and ``scopes`` (request state, CurrentUser)."""
    return is_agent(getattr(subject, "user_id", None), getattr(subject, "scopes", None))


def tool_rule(name: str) -> str:
    """The rule for MCP tool ``name``; ``refuse`` for any name without one."""
    return MCP_TOOL_RULES.get(name, REFUSE) if isinstance(name, str) else REFUSE


def rest_rule(method: str, route_path: str | None) -> str:
    """The rule for a REST request (``hold`` never applies: REST can't hold).

    Args:
        method: The HTTP method.
        route_path: The routed path *template* (``request.scope["route"].path``,
            e.g. ``/api/approvals/{approval_id}/approve``), never the raw URL,
            so trailing slashes, ``//``, ``%2F``, ``..`` and query strings can't
            change the rule. None (no route matched) is refused.
    """
    if not isinstance(route_path, str) or not route_path:
        return REFUSE
    method = (method or "").upper()
    if method in _READ_METHODS:
        return ALLOW  # venture scope still applies
    if (method, route_path) in REST_AGENT_WRITES:
        return ALLOW
    if route_path in REST_DECISION_ROUTES:
        return PEOPLE_DECIDE
    return REFUSE


def tool_refusal(name: str) -> tuple[str, str] | None:
    """``(code, message)`` when an agent may not call MCP tool ``name`` at all, else None."""
    rule = tool_rule(name)
    if rule == PEOPLE_DECIDE:
        return CODE_PEOPLE_DECIDE, f"{PEOPLE_DECIDE_MESSAGE} ('{name}'). A person decides in the dashboard."
    if rule == REFUSE:
        return CODE_REFUSED, f"Tool '{name}' isn't available to an outside agent; an owner does this."
    return None


def rest_refusal(method: str, route_path: str | None) -> str | None:
    """Why an agent may not make this REST request, or None when it may (see :func:`rest_rule`)."""
    rule = rest_rule(method, route_path)
    if rule == PEOPLE_DECIDE:
        return PEOPLE_DECIDE_MESSAGE
    if rule == REFUSE:
        return REST_WRITE_MESSAGE
    return None


def must_hold(name: str) -> bool:
    """True when an agent's call to MCP tool ``name`` waits for a person's approval."""
    return tool_rule(name) == HOLD
