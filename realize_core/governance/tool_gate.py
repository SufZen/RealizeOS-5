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

    @property
    def store(self) -> ApprovalStore:
        """The approval store the gate records held actions into."""
        return self._store

    def decide(self, action_name: str, params: dict[str, Any] | None = None) -> GateDecision:
        """
        Decide whether ``action_name`` may execute under current governance.

        Never raises. On any internal error, fails open (ALLOW) and logs.
        """
        params = params or {}
        try:
            decision = check_trust(action_name, self._config, channel=self._channel)

            if decision is TrustDecision.AUTO:
                return GateDecision(GateOutcome.ALLOW, action_name)

            if decision is TrustDecision.APPROVE:
                request_id = self._record(action_name, params, status="approve")
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
        except Exception as exc:  # fail-open: a gate bug must not brick tools
            logger.error(
                "ToolGate.decide failed for action '%s' — failing open (ALLOW): %s",
                action_name,
                exc,
                exc_info=True,
            )
            return GateDecision(GateOutcome.ALLOW, action_name, reason="gate error (fail-open)")

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _record(self, action_name: str, params: dict[str, Any], status: str) -> str:
        """
        Record a held/blocked action as an approval request.

        Writes to the injected in-memory ApprovalStore (authoritative for the
        returned id), and best-effort to the DB-backed ``approval_queue`` so the
        existing dashboard surfaces it. Never raises.
        """
        request = ApprovalRequest(
            action=ApprovalAction.REQUEST_DECISION,
            description=f"Tool action '{action_name}' {status} by governance gate",
            agent_key=self._agent_key,
            system_key=self._system_key,
            metadata={
                "tool_action": action_name,
                "gate_status": status,
                "params": _safe_params(params),
            },
        )
        self._store.create(request)

        # Best-effort mirror into the DB-backed approval_queue the dashboard reads.
        try:
            from realize_core.governance.gates import create_approval_request

            create_approval_request(
                venture_key=self._system_key,
                agent_key=self._agent_key,
                action_type=action_name,
                payload={"gate_status": status, "params": _safe_params(params)},
            )
        except Exception as exc:
            logger.debug("approval_queue mirror skipped for '%s': %s", action_name, exc)

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
