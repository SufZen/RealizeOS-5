"""
Tool Gate — the single enforcement point that turns the dormant governance
ladder into a real, intercepting gate on tool execution.

This module is intentionally *decoupled* from the ToolRegistry: the registry
holds an optional reference to a ``ToolGate`` and, when present, consults it
immediately before dispatching a tool action. When no gate is injected
(the default), tool execution behaves exactly as before.

Decision logic reuses the EXISTING governance vocabulary — it does NOT invent
a new one:

- ``realize_core.governance.trust_ladder.check_trust`` resolves a tool action
  (e.g. ``gmail_send``) through ``ACTION_MAP`` to a governance action
  (``send_email``) and returns BLOCK / APPROVE / AUTO for the current trust
  level.

The gate maps those decisions onto:

- AUTO    → ``GateOutcome.ALLOW``           (proceed, no record)
- APPROVE → ``GateOutcome.NEEDS_APPROVAL``  (create approval, hold the action)
- BLOCK   → ``GateOutcome.BLOCK``           (refuse, optionally record)

On NEEDS_APPROVAL / BLOCK the gate records an approval request so an operator
can see and resolve it. It writes to two places, both best-effort:

1. The injected in-memory :class:`ApprovalStore` (always; hermetic, what tests
   assert against).
2. The DB-backed ``approval_queue`` via
   :func:`realize_core.governance.gates.create_approval_request` (best-effort)
   so the existing API/dashboard at ``GET /api/approvals`` surfaces it.

The gate NEVER raises: any internal error fails *open* (returns ALLOW) and is
logged, so a gate bug can never brick tool execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from realize_core.governance.trust_ladder import TrustDecision, check_trust
from realize_core.tools.approval import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalStore,
)

logger = logging.getLogger(__name__)


class GateOutcome(Enum):
    """What the gate decided to do with a tool action."""

    ALLOW = "allow"
    NEEDS_APPROVAL = "needs_approval"
    BLOCK = "block"


@dataclass(frozen=True)
class GateDecision:
    """Result of a gate evaluation for a single tool action."""

    outcome: GateOutcome
    action_name: str
    request_id: str | None = None
    reason: str = ""

    @property
    def allowed(self) -> bool:
        """True when the tool should be executed as normal."""
        return self.outcome is GateOutcome.ALLOW


class ToolGate:
    """
    Governance gate consulted by the ToolRegistry before tool dispatch.

    Construct with the system ``config`` (so the trust ladder can read
    ``config['trust']``) and an :class:`ApprovalStore` to record held actions.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        approval_store: ApprovalStore | None = None,
        *,
        channel: str = "dashboard",
        agent_key: str = "tool_gate",
        system_key: str = "default",
    ):
        self._config = config or {}
        self._store = approval_store or ApprovalStore()
        self._channel = channel
        self._agent_key = agent_key
        self._system_key = system_key

    def update_config(self, config: dict[str, Any] | None) -> None:
        """Use a reloaded config (trust level, rules) from the next decision on."""
        self._config = config or {}

    @property
    def store(self) -> ApprovalStore:
        """The approval store the gate records held actions into."""
        return self._store

    def decide(
        self,
        action_name: str,
        params: dict[str, Any] | None = None,
        *,
        is_destructive: bool | None = None,
    ) -> GateDecision:
        """
        Decide whether ``action_name`` may execute under current governance.

        ``is_destructive`` comes from the tool's schema; it decides how an
        action without an explicit trust rule is treated (writes need approval).

        Never raises. On any internal error, fails open (ALLOW) and logs.
        """
        params = params or {}
        try:
            decision = check_trust(action_name, self._config, channel=self._channel, is_destructive=is_destructive)
            if decision is TrustDecision.AUTO and is_destructive is not False:
                from realize_core.security.agent_access import outside_agent_active

                if outside_agent_active():
                    # An outside agent never gets the trust ladder's automatic writes
                    # (STORY-37): a person approves every write it sets off.
                    decision = TrustDecision.APPROVE

            if decision is TrustDecision.AUTO:
                return GateDecision(GateOutcome.ALLOW, action_name)

            if decision is TrustDecision.APPROVE:
                request_id = self._record(action_name, params, status="approve")
                if request_id is None:
                    # No durable approval row: never report an approval nobody can act on.
                    return GateDecision(
                        GateOutcome.BLOCK, action_name, reason="approval could not be recorded (blocked)"
                    )
                return GateDecision(
                    GateOutcome.NEEDS_APPROVAL,
                    action_name,
                    request_id=request_id,
                    reason="requires operator approval",
                )

            # TrustDecision.BLOCK
            request_id = self._record(action_name, params, status="block")
            return GateDecision(
                GateOutcome.BLOCK,
                action_name,
                request_id=request_id,
                reason="blocked by trust policy",
            )
        except Exception as exc:
            # Fail closed for anything that may write; reads keep working.
            if is_destructive is False:
                logger.error("ToolGate.decide failed for read '%s' — allowing: %s", action_name, exc, exc_info=True)
                return GateDecision(GateOutcome.ALLOW, action_name, reason="gate error (read allowed)")
            logger.error("ToolGate.decide failed for '%s' — blocking: %s", action_name, exc, exc_info=True)
            return GateDecision(GateOutcome.BLOCK, action_name, reason="gate error (blocked)")

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _record(self, action_name: str, params: dict[str, Any], status: str) -> str | None:
        """
        Record a held/blocked action as an approval request.

        ``approval_queue`` (what the dashboard shows and what approving acts on)
        is authoritative: the row stores the full parameters and the origin of
        the call (venture, agent, user, from the current tool-call context) so
        an approval can execute the action and report back. The returned id is
        that row's id. The in-memory ApprovalStore gets a copy under the same id.
        Returns None when the durable row could not be written. Never raises.
        """
        from realize_core.governance.context import current_tool_context

        origin = current_tool_context()
        system_key = origin.system_key or self._system_key
        agent_key = origin.agent_key or self._agent_key

        request = ApprovalRequest(
            action=ApprovalAction.REQUEST_DECISION,
            description=f"Tool action '{action_name}' {status} by governance gate",
            agent_key=agent_key,
            system_key=system_key,
            metadata={
                "tool_action": action_name,
                "gate_status": status,
                "params": _safe_params(params),
            },
        )
        try:
            from realize_core.governance.gates import create_approval_request

            request.id = create_approval_request(
                venture_key=system_key,
                agent_key=agent_key,
                action_type=action_name,
                payload={"gate_status": status, "params": _safe_params(params)},
                action_name=action_name if status == "approve" else None,
                params=params if status == "approve" else None,
                requested_by=origin.user_id or None,
                session_ref=origin.session_ref or None,
            )
        except Exception as exc:
            logger.error("approval_queue write failed for '%s': %s", action_name, exc)
            return None

        self._store.create(request)
        return request.id


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    """Best-effort, log-safe snapshot of params (string-truncated values)."""
    safe: dict[str, Any] = {}
    for key, value in params.items():
        try:
            text = str(value)
        except Exception:
            text = "<unrepr>"
        safe[str(key)] = text[:500]
    return safe
