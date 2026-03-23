"""
Handoff handlers — structured inter-agent communication.

Implements the 7 handoff types defined in HandoffType:
1. standard   — Normal sequential handoff
2. qa_pass    — QA approved the output
3. qa_fail    — QA rejected → retry or escalation
4. escalation — Auto-escalation after max retries
5. phase_gate — Human approval required
6. sprint     — Sprint boundary checkpoint
7. incident   — Error-triggered handoff to incident handler

Each handler is a pure function that transforms a HandoffData payload,
applying type-specific logic (retry counting, escalation triggers, etc.).
"""

from __future__ import annotations

import logging

from realize_core.agents.base import HandoffData, HandoffType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handoff result
# ---------------------------------------------------------------------------


class HandoffResult:
    """
    Result of processing a handoff.

    Attributes:
        handoff: The (potentially modified) handoff payload.
        action: What the pipeline should do next — one of:
            ``"continue"``, ``"retry"``, ``"escalate"``,
            ``"await_approval"``, ``"checkpoint"``, ``"halt"``.
        message: Human-readable description of what happened.
    """

    __slots__ = ("handoff", "action", "message")

    def __init__(
        self,
        handoff: HandoffData,
        action: str,
        message: str = "",
    ) -> None:
        self.handoff = handoff
        self.action = action
        self.message = message

    def __repr__(self) -> str:
        return (
            f"HandoffResult(action={self.action!r}, "
            f"type={self.handoff.handoff_type.value}, "
            f"src={self.handoff.source_agent}, "
            f"dst={self.handoff.target_agent})"
        )


# ---------------------------------------------------------------------------
# Per-type handlers
# ---------------------------------------------------------------------------


def handle_standard(handoff: HandoffData) -> HandoffResult:
    """Standard sequential handoff — just pass through."""
    logger.debug(
        "Standard handoff: %s → %s",
        handoff.source_agent,
        handoff.target_agent,
    )
    return HandoffResult(
        handoff=handoff,
        action="continue",
        message=f"Handing off from {handoff.source_agent} to {handoff.target_agent}",
    )


def handle_qa_pass(handoff: HandoffData) -> HandoffResult:
    """QA approved — continue to next stage."""
    logger.info(
        "QA PASS: %s approved output from %s",
        handoff.source_agent,
        handoff.target_agent,
    )
    return HandoffResult(
        handoff=handoff,
        action="continue",
        message=f"QA passed by {handoff.source_agent}",
    )


def handle_qa_fail(handoff: HandoffData) -> HandoffResult:
    """
    QA rejected — retry or escalate.

    If retries remain, returns action ``"retry"`` with incremented count.
    If exhausted, returns action ``"escalate"``.
    """
    if handoff.is_retry_exhausted:
        logger.warning(
            "QA FAIL: retries exhausted (%d/%d) — escalating",
            handoff.retry_count,
            handoff.max_retries,
        )
        escalated = HandoffData(
            source_agent=handoff.source_agent,
            target_agent=handoff.target_agent,
            handoff_type=HandoffType.ESCALATION,
            payload=handoff.payload,
            artifacts=handoff.artifacts,
            context={**handoff.context, "escalation_reason": "max_retries_exhausted"},
            retry_count=handoff.retry_count,
            max_retries=handoff.max_retries,
        )
        return HandoffResult(
            handoff=escalated,
            action="escalate",
            message=(f"QA failed after {handoff.retry_count} retries — escalating from {handoff.source_agent}"),
        )

    retried = handoff.with_retry()
    logger.info(
        "QA FAIL: retry %d/%d for %s",
        retried.retry_count,
        retried.max_retries,
        retried.target_agent,
    )
    return HandoffResult(
        handoff=retried,
        action="retry",
        message=(f"QA failed — retrying ({retried.retry_count}/{retried.max_retries})"),
    )


def handle_escalation(handoff: HandoffData) -> HandoffResult:
    """Escalation handoff — flag for human or supervisor attention."""
    logger.warning(
        "ESCALATION: %s → %s (reason: %s)",
        handoff.source_agent,
        handoff.target_agent,
        handoff.context.get("escalation_reason", "unknown"),
    )
    return HandoffResult(
        handoff=handoff,
        action="halt",
        message=(f"Escalated from {handoff.source_agent}: {handoff.context.get('escalation_reason', 'unknown')}"),
    )


def handle_phase_gate(handoff: HandoffData) -> HandoffResult:
    """Phase gate — pause pipeline until human approval."""
    logger.info(
        "PHASE GATE: awaiting approval for %s → %s",
        handoff.source_agent,
        handoff.target_agent,
    )
    return HandoffResult(
        handoff=handoff,
        action="await_approval",
        message=(f"Phase gate: awaiting human approval before {handoff.target_agent} can proceed"),
    )


def handle_sprint(handoff: HandoffData) -> HandoffResult:
    """Sprint boundary — checkpoint state and report."""
    logger.info(
        "SPRINT BOUNDARY: checkpoint after %s",
        handoff.source_agent,
    )
    return HandoffResult(
        handoff=handoff,
        action="checkpoint",
        message=f"Sprint checkpoint after {handoff.source_agent}",
    )


def handle_incident(handoff: HandoffData) -> HandoffResult:
    """Incident handoff — error-triggered, halt pipeline."""
    logger.error(
        "INCIDENT: error in %s, handing to %s",
        handoff.source_agent,
        handoff.target_agent,
    )
    return HandoffResult(
        handoff=handoff,
        action="halt",
        message=(f"Incident triggered by {handoff.source_agent}: {handoff.context.get('error', 'unknown error')}"),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_HANDLERS = {
    HandoffType.STANDARD: handle_standard,
    HandoffType.QA_PASS: handle_qa_pass,
    HandoffType.QA_FAIL: handle_qa_fail,
    HandoffType.ESCALATION: handle_escalation,
    HandoffType.PHASE_GATE: handle_phase_gate,
    HandoffType.SPRINT: handle_sprint,
    HandoffType.INCIDENT: handle_incident,
}


def process_handoff(handoff: HandoffData) -> HandoffResult:
    """
    Route a handoff to the appropriate handler based on its type.

    Args:
        handoff: The handoff payload to process.

    Returns:
        A HandoffResult describing the action the pipeline should take.

    Raises:
        ValueError: If the handoff type is not recognised.
    """
    handler = _HANDLERS.get(handoff.handoff_type)
    if handler is None:
        raise ValueError(f"Unknown handoff type: {handoff.handoff_type}")
    return handler(handoff)
