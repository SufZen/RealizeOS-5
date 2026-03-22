"""
Tests for the agent handoff system — 7 handoff types.
"""
import pytest
from realize_core.agents.base import HandoffData, HandoffType
from realize_core.agents.handoff import (
    HandoffResult,
    handle_escalation,
    handle_incident,
    handle_phase_gate,
    handle_qa_fail,
    handle_qa_pass,
    handle_sprint,
    handle_standard,
    process_handoff,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_handoff(
    handoff_type: HandoffType = HandoffType.STANDARD,
    source: str = "writer",
    target: str = "reviewer",
    retry_count: int = 0,
    max_retries: int = 3,
    context: dict | None = None,
) -> HandoffData:
    return HandoffData(
        source_agent=source,
        target_agent=target,
        handoff_type=handoff_type,
        payload={"output": "test content"},
        context=context or {},
        retry_count=retry_count,
        max_retries=max_retries,
    )


# ---------------------------------------------------------------------------
# Standard handoff
# ---------------------------------------------------------------------------

class TestStandardHandoff:
    def test_action_is_continue(self):
        result = handle_standard(_make_handoff())
        assert result.action == "continue"

    def test_preserves_handoff(self):
        handoff = _make_handoff()
        result = handle_standard(handoff)
        assert result.handoff is handoff


# ---------------------------------------------------------------------------
# QA Pass
# ---------------------------------------------------------------------------

class TestQAPass:
    def test_action_is_continue(self):
        result = handle_qa_pass(_make_handoff(HandoffType.QA_PASS))
        assert result.action == "continue"


# ---------------------------------------------------------------------------
# QA Fail
# ---------------------------------------------------------------------------

class TestQAFail:
    def test_retry_when_budget_remains(self):
        handoff = _make_handoff(HandoffType.QA_FAIL, retry_count=0)
        result = handle_qa_fail(handoff)
        assert result.action == "retry"
        assert result.handoff.retry_count == 1

    def test_escalate_when_exhausted(self):
        handoff = _make_handoff(HandoffType.QA_FAIL, retry_count=3, max_retries=3)
        result = handle_qa_fail(handoff)
        assert result.action == "escalate"
        assert result.handoff.handoff_type == HandoffType.ESCALATION

    def test_retry_increments_count(self):
        handoff = _make_handoff(HandoffType.QA_FAIL, retry_count=1)
        result = handle_qa_fail(handoff)
        assert result.handoff.retry_count == 2

    def test_escalation_context_set(self):
        handoff = _make_handoff(HandoffType.QA_FAIL, retry_count=3, max_retries=3)
        result = handle_qa_fail(handoff)
        assert "escalation_reason" in result.handoff.context


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

class TestEscalation:
    def test_action_is_halt(self):
        handoff = _make_handoff(
            HandoffType.ESCALATION,
            context={"escalation_reason": "max_retries_exhausted"},
        )
        result = handle_escalation(handoff)
        assert result.action == "halt"


# ---------------------------------------------------------------------------
# Phase Gate
# ---------------------------------------------------------------------------

class TestPhaseGate:
    def test_action_is_await_approval(self):
        result = handle_phase_gate(_make_handoff(HandoffType.PHASE_GATE))
        assert result.action == "await_approval"


# ---------------------------------------------------------------------------
# Sprint
# ---------------------------------------------------------------------------

class TestSprint:
    def test_action_is_checkpoint(self):
        result = handle_sprint(_make_handoff(HandoffType.SPRINT))
        assert result.action == "checkpoint"


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------

class TestIncident:
    def test_action_is_halt(self):
        handoff = _make_handoff(
            HandoffType.INCIDENT,
            context={"error": "Connection timeout"},
        )
        result = handle_incident(handoff)
        assert result.action == "halt"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class TestProcessHandoff:
    def test_dispatches_all_types(self):
        """Every HandoffType should be handled without raising."""
        for ht in HandoffType:
            handoff = _make_handoff(ht)
            result = process_handoff(handoff)
            assert isinstance(result, HandoffResult)

    def test_unknown_type_raises(self):
        """A handoff with an invalid type should raise ValueError."""
        handoff = _make_handoff()
        # Monkey-patch an invalid type for test
        object.__setattr__(handoff, "handoff_type", "invalid_type")
        with pytest.raises(ValueError, match="Unknown handoff type"):
            process_handoff(handoff)


# ---------------------------------------------------------------------------
# Dev-QA retry escalation sequence
# ---------------------------------------------------------------------------

class TestDevQARetrySequence:
    """Simulate a full Dev-QA retry → escalation sequence."""

    def test_three_retries_then_escalation(self):
        handoff = _make_handoff(HandoffType.QA_FAIL, retry_count=0, max_retries=3)

        # Retry 1
        result = handle_qa_fail(handoff)
        assert result.action == "retry"
        assert result.handoff.retry_count == 1

        # Retry 2
        result = handle_qa_fail(result.handoff)
        assert result.action == "retry"
        assert result.handoff.retry_count == 2

        # Retry 3
        result = handle_qa_fail(result.handoff)
        assert result.action == "retry"
        assert result.handoff.retry_count == 3

        # Attempt 4 → escalation
        result = handle_qa_fail(result.handoff)
        assert result.action == "escalate"
        assert result.handoff.handoff_type == HandoffType.ESCALATION
