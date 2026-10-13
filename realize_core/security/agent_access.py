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

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
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
    # Chat runs with acting_for_outside_agent(): write tools are always held by the
    # ToolGate, and trigger phrases don't auto-run skills.
    "realize_chat": ALLOW,
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
#: The only REST writes an agent may make, by method and the routed endpoint
#: (``module.function``): chatting, and clearing its own conversation.
#: Everything else is refused, including POST routes that read (search,
#: export). Matching the endpoint the router chose, never the URL, means
#: trailing slashes, ``//``, ``%2F``, ``..``, query strings and look-alike
#: prefixes can't change a rule, whatever the framework's path layout.
REST_AGENT_WRITES = frozenset(
    {
        ("POST", "realize_api.routes.chat.chat"),
        ("POST", "realize_api.routes.chat.chat_stream"),
        ("DELETE", "realize_api.routes.chat.clear_conversations"),
    }
)
#: REST decisions on held actions and proposals, by routed endpoint.
REST_DECISION_ENDPOINTS = frozenset(
    {
        "realize_api.routes.approvals.approve",
        "realize_api.routes.approvals.reject",
        "realize_api.routes.dreams.approve_dream",
        "realize_api.routes.dreams.reject_dream",
        "realize_api.routes.evolution.approve_suggestion",
        "realize_api.routes.evolution.dismiss_suggestion",
    }
)

#: The outside agent a piece of work is being done for (its ``requested_by``
#: id), while it runs. See :func:`acting_for_outside_agent`.
_OUTSIDE_AGENT: ContextVar[str | None] = ContextVar("realize_outside_agent", default=None)


@contextmanager
def acting_for_outside_agent(principal: str | None) -> Iterator[None]:
    """Mark everything inside as done for an outside agent.

    While it is active, the ``ToolGate`` holds every write tool for a person
    even when the trust ladder would run it automatically, the tool registry
    refuses writes when no gate is installed, and chat doesn't auto-run
    skills from trigger phrases or answer a paused skill's question. Set by
    the MCP dispatcher around an agent's tool call, by the REST chat routes
    for an agent caller, around an approved held write of an agent, and when
    a paused skill an agent started is resumed.
    """
    token = _OUTSIDE_AGENT.set(principal or "agent")
    try:
        yield
    finally:
        _OUTSIDE_AGENT.reset(token)


def outside_agent_active() -> bool:
    """True while work is being done for an outside agent."""
    return _OUTSIDE_AGENT.get() is not None


def current_outside_agent() -> str | None:
    """The outside agent's principal id (``agent:...``) work is being done for now, or None.

    None also when the work is marked as an agent's but its principal is
    unknown. Approval rows created meanwhile name this principal as
    ``requested_by``, so they show as the agent's.
    """
    principal = _OUTSIDE_AGENT.get()
    return principal if isinstance(principal, str) and principal.startswith("agent:") else None


def endpoint_name(endpoint: Any) -> str | None:
    """``module.function`` of a routed endpoint, or None."""
    module = getattr(endpoint, "__module__", None)
    name = getattr(endpoint, "__qualname__", None)
    return f"{module}.{name}" if module and name else None


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


def rest_rule(method: str, endpoint: str | None) -> str:
    """The rule for a REST request (``hold`` never applies: REST can't hold).

    Args:
        method: The HTTP method.
        endpoint: The routed endpoint as ``module.function``
            (:func:`endpoint_name` of ``request.scope["endpoint"]``), never the
            raw URL. None (no route matched) is refused.
    """
    if not isinstance(endpoint, str) or not endpoint:
        return REFUSE
    method = (method or "").upper()
    if method in _READ_METHODS:
        return ALLOW  # venture scope still applies
    if (method, endpoint) in REST_AGENT_WRITES:
        return ALLOW
    if endpoint in REST_DECISION_ENDPOINTS:
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


def rest_refusal(method: str, endpoint: str | None) -> str | None:
    """Why an agent may not make this REST request, or None when it may (see :func:`rest_rule`)."""
    rule = rest_rule(method, endpoint)
    if rule == PEOPLE_DECIDE:
        return PEOPLE_DECIDE_MESSAGE
    if rule == REFUSE:
        return REST_WRITE_MESSAGE
    return None


def must_hold(name: str) -> bool:
    """True when an agent's call to MCP tool ``name`` waits for a person's approval."""
    return tool_rule(name) == HOLD
