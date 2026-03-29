"""
Tests for the pipeline executor — sequential execution, Dev-QA retry, escalation.
"""

import pytest
from realize_core.agents.base import HandoffType, PipelineStage
from realize_core.agents.handoff import _audit_log
from realize_core.agents.pipeline import (
    PipelineStatus,
    execute_pipeline,
)


@pytest.fixture(autouse=True)
def clear_audit_log():
    """Clear global audit log before each test to prevent circular handoff false positives."""
    _audit_log.clear()
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stage(
    name: str,
    agent_key: str,
    handoff_type: HandoffType = HandoffType.STANDARD,
) -> PipelineStage:
    return PipelineStage(
        name=name,
        agent_key=agent_key,
        handoff_type=handoff_type,
    )


async def _echo_executor(stage: PipelineStage, input_text: str, context: dict) -> str:
    """Simple executor that echoes input with stage name prefix."""
    return f"[{stage.name}] {input_text}"


async def _qa_pass_executor(stage: PipelineStage, input_text: str, context: dict) -> str:
    """Executor that always passes QA."""
    if "qa" in stage.name.lower():
        return "PASS — looks good!"
    return f"[{stage.name}] {input_text}"


async def _qa_fail_executor(stage: PipelineStage, input_text: str, context: dict) -> str:
    """Executor that always fails QA."""
    if "qa" in stage.name.lower():
        return "FAIL — needs revision."
    return f"[{stage.name}] {input_text}"


async def _error_executor(stage: PipelineStage, input_text: str, context: dict) -> str:
    """Executor that raises on a specific stage."""
    if stage.agent_key == "broken":
        raise RuntimeError("Agent crashed!")
    return f"[{stage.name}] {input_text}"


# ---------------------------------------------------------------------------
# Basic pipeline execution
# ---------------------------------------------------------------------------


class TestBasicPipeline:
    """Test standard sequential pipeline execution."""

    @pytest.mark.asyncio
    async def test_single_stage(self):
        stages = [_make_stage("draft", "writer")]
        state = await execute_pipeline(
            "p-1",
            stages,
            "Write a blog post",
            _echo_executor,
        )
        assert state.status == PipelineStatus.COMPLETED
        assert len(state.results) == 1
        assert "[draft]" in state.results[0].output

    @pytest.mark.asyncio
    async def test_multi_stage(self):
        stages = [
            _make_stage("plan", "orchestrator"),
            _make_stage("draft", "writer"),
            _make_stage("review", "reviewer"),
        ]
        state = await execute_pipeline(
            "p-2",
            stages,
            "Create a proposal",
            _echo_executor,
        )
        assert state.status == PipelineStatus.COMPLETED
        assert len(state.results) == 3

    @pytest.mark.asyncio
    async def test_output_flows_through_stages(self):
        stages = [
            _make_stage("step1", "a"),
            _make_stage("step2", "b"),
        ]
        state = await execute_pipeline(
            "p-3",
            stages,
            "input",
            _echo_executor,
        )
        # Step 2 should receive step 1's output
        assert "[step1]" in state.results[1].output

    @pytest.mark.asyncio
    async def test_pipeline_id_preserved(self):
        stages = [_make_stage("x", "y")]
        state = await execute_pipeline("my-pipeline", stages, "go", _echo_executor)
        assert state.pipeline_id == "my-pipeline"

    @pytest.mark.asyncio
    async def test_timing_tracked(self):
        stages = [_make_stage("s", "a")]
        state = await execute_pipeline("p-t", stages, "go", _echo_executor)
        assert state.total_duration_ms > 0
        assert state.results[0].duration_ms > 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestPipelineErrors:
    @pytest.mark.asyncio
    async def test_stage_error_halts_pipeline(self):
        stages = [
            _make_stage("good", "writer"),
            _make_stage("bad", "broken"),
            _make_stage("never", "reviewer"),
        ]
        state = await execute_pipeline(
            "p-err",
            stages,
            "go",
            _error_executor,
        )
        assert state.status == PipelineStatus.FAILED
        assert "crashed" in state.error.lower()
        assert len(state.results) == 2  # good + bad (with error)

    @pytest.mark.asyncio
    async def test_error_result_recorded(self):
        stages = [_make_stage("fail", "broken")]
        state = await execute_pipeline("p-e2", stages, "go", _error_executor)
        assert state.results[0].error is not None


# ---------------------------------------------------------------------------
# QA Pass pipeline
# ---------------------------------------------------------------------------


class TestQAPassPipeline:
    @pytest.mark.asyncio
    async def test_qa_pass_continues(self):
        stages = [
            _make_stage("draft", "writer"),
            _make_stage("qa", "reviewer", HandoffType.QA_PASS),
        ]
        state = await execute_pipeline(
            "p-qa",
            stages,
            "Write something",
            _qa_pass_executor,
        )
        assert state.status == PipelineStatus.COMPLETED
        assert len(state.results) == 2


# ---------------------------------------------------------------------------
# QA Fail → Retry → Escalation
# ---------------------------------------------------------------------------


class TestQARetryEscalation:
    @pytest.mark.asyncio
    async def test_qa_fail_triggers_retries(self):
        """QA fail with retries remaining should retry."""
        fail_count = 0

        async def counting_executor(stage, input_text, context):
            nonlocal fail_count
            if "qa" in stage.name.lower():
                fail_count += 1
                if fail_count <= 2:
                    return "FAIL — try again"
                return "PASS — ok now"
            return f"[{stage.name}] {input_text}"

        stages = [
            _make_stage("draft", "writer"),
            _make_stage("qa", "reviewer", HandoffType.QA_PASS),
        ]
        state = await execute_pipeline(
            "p-retry",
            stages,
            "input",
            counting_executor,
            max_retries=3,
        )
        # Should eventually pass after retries
        assert state.status == PipelineStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_max_retries_escalates(self):
        """QA fail that never passes should escalate after max retries."""
        stages = [
            _make_stage("draft", "writer"),
            _make_stage("qa", "reviewer", HandoffType.QA_PASS),
        ]
        state = await execute_pipeline(
            "p-esc",
            stages,
            "input",
            _qa_fail_executor,
            max_retries=3,
        )
        assert state.status == PipelineStatus.ESCALATED
        assert "escalat" in state.error.lower()


# ---------------------------------------------------------------------------
# Phase gate
# ---------------------------------------------------------------------------


class TestPhaseGate:
    @pytest.mark.asyncio
    async def test_phase_gate_pauses_pipeline(self):
        stages = [
            _make_stage("draft", "writer"),
            _make_stage("approval", "human", HandoffType.PHASE_GATE),
        ]
        state = await execute_pipeline(
            "p-gate",
            stages,
            "input",
            _echo_executor,
        )
        assert state.status == PipelineStatus.AWAITING_APPROVAL


# ---------------------------------------------------------------------------
# Pipeline state properties
# ---------------------------------------------------------------------------


class TestPipelineState:
    @pytest.mark.asyncio
    async def test_last_output(self):
        stages = [_make_stage("s1", "a"), _make_stage("s2", "b")]
        state = await execute_pipeline("p", stages, "go", _echo_executor)
        assert "[s2]" in state.last_output

    @pytest.mark.asyncio
    async def test_is_complete(self):
        stages = [_make_stage("s", "a")]
        state = await execute_pipeline("p", stages, "go", _echo_executor)
        assert state.is_complete

    @pytest.mark.asyncio
    async def test_handoff_history_recorded(self):
        stages = [_make_stage("s1", "a"), _make_stage("s2", "b")]
        state = await execute_pipeline("p", stages, "go", _echo_executor)
        assert len(state.handoff_history) >= 2
