"""
Pipeline Executor — sequential multi-agent pipeline with structured handoffs.

Implements:
- Sequential stage execution through an ordered list of agents
- Dev-QA retry loop: max 3 retries → auto-escalation
- Handoff routing via the handoff module
- Pipeline state tracking (current stage, history, results)
- Guardrail enforcement at stage boundaries

The pipeline does NOT call LLMs directly — it delegates to a
``stage_executor`` callback that the caller provides.  This keeps
the pipeline logic pure and testable.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from realize_core.agents.base import GuardrailConfig, HandoffData, HandoffType, PipelineStage
from realize_core.agents.guardrails import (
    Verdict,
    check_guardrails,
    has_strict_violations,
    parse_verdict,
)
from realize_core.agents.handoff import HandoffResult, process_handoff

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------


class PipelineStatus(StrEnum):
    """Overall pipeline status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"
    ESCALATED = "escalated"


@dataclass
class StageResult:
    """Result of executing a single pipeline stage."""

    stage_name: str
    agent_key: str
    output: str = ""
    verdict: Verdict = Verdict.UNKNOWN
    duration_ms: float = 0.0
    retry_count: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineState:
    """
    Tracks the state of a pipeline execution.

    Mutable — updated as stages execute.
    """

    pipeline_id: str
    stages: list[PipelineStage]
    status: PipelineStatus = PipelineStatus.PENDING
    current_stage_index: int = 0
    results: list[StageResult] = field(default_factory=list)
    handoff_history: list[HandoffResult] = field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str | None = None

    @property
    def current_stage(self) -> PipelineStage | None:
        """The current stage, or None if pipeline is complete."""
        if 0 <= self.current_stage_index < len(self.stages):
            return self.stages[self.current_stage_index]
        return None

    @property
    def is_complete(self) -> bool:
        """Whether the pipeline has finished (success or failure)."""
        return self.status in (
            PipelineStatus.COMPLETED,
            PipelineStatus.FAILED,
            PipelineStatus.ESCALATED,
        )

    @property
    def total_duration_ms(self) -> float:
        """Total elapsed time in milliseconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        if self.started_at:
            return (time.time() - self.started_at) * 1000
        return 0.0

    @property
    def last_output(self) -> str:
        """The output from the most recent stage."""
        if self.results:
            return self.results[-1].output
        return ""


# Type alias for the stage executor callback
StageExecutor = Callable[
    [PipelineStage, str, dict[str, Any]],  # stage, input_text, context
    Awaitable[str],  # output text
]


# ---------------------------------------------------------------------------
# Pipeline executor
# ---------------------------------------------------------------------------


async def execute_pipeline(
    pipeline_id: str,
    stages: list[PipelineStage],
    initial_input: str,
    stage_executor: StageExecutor,
    context: dict[str, Any] | None = None,
    guardrail_configs: dict[str, list[GuardrailConfig]] | None = None,
    max_retries: int = 3,
) -> PipelineState:
    """
    Execute a sequential multi-agent pipeline.

    Args:
        pipeline_id: Unique identifier for this pipeline run.
        stages: Ordered list of pipeline stages to execute.
        initial_input: The starting input text for the first stage.
        stage_executor: Async callback that executes a stage and returns output.
            Signature: ``async (stage, input_text, context) -> output_text``
        context: Optional shared context passed to every stage.
        guardrail_configs: Optional mapping of agent_key → guardrails to enforce.
        max_retries: Maximum Dev-QA retries before escalation (default 3).

    Returns:
        PipelineState with full execution history and results.
    """
    context = context or {}
    guardrail_configs = guardrail_configs or {}

    state = PipelineState(
        pipeline_id=pipeline_id,
        stages=stages,
        status=PipelineStatus.RUNNING,
        started_at=time.time(),
    )

    current_input = initial_input

    while state.current_stage_index < len(stages):
        stage = stages[state.current_stage_index]
        retry_count = 0

        logger.info(
            "Pipeline %s: executing stage %d/%d '%s' (agent: %s)",
            pipeline_id,
            state.current_stage_index + 1,
            len(stages),
            stage.name,
            stage.agent_key,
        )

        # Dev-QA retry loop
        while True:
            start_time = time.time()

            try:
                output = await stage_executor(stage, current_input, context)
            except Exception as exc:
                logger.error(
                    "Pipeline %s: stage '%s' failed: %s",
                    pipeline_id,
                    stage.name,
                    exc,
                )
                state.results.append(
                    StageResult(
                        stage_name=stage.name,
                        agent_key=stage.agent_key,
                        error=str(exc),
                        duration_ms=(time.time() - start_time) * 1000,
                        retry_count=retry_count,
                    )
                )

                # Create incident handoff
                incident = HandoffData(
                    source_agent=stage.agent_key,
                    target_agent="incident_handler",
                    handoff_type=HandoffType.INCIDENT,
                    context={"error": str(exc), "stage": stage.name},
                )
                result = process_handoff(incident)
                state.handoff_history.append(result)
                state.status = PipelineStatus.FAILED
                state.error = str(exc)
                state.completed_at = time.time()
                return state

            duration_ms = (time.time() - start_time) * 1000

            # Check guardrails on output
            agent_guardrails = guardrail_configs.get(stage.agent_key, [])
            violations = check_guardrails(output, agent_guardrails, context)

            if has_strict_violations(violations):
                logger.warning(
                    "Pipeline %s: strict guardrail violation in stage '%s'",
                    pipeline_id,
                    stage.name,
                )
                state.results.append(
                    StageResult(
                        stage_name=stage.name,
                        agent_key=stage.agent_key,
                        output=output,
                        verdict=Verdict.FAIL,
                        duration_ms=duration_ms,
                        retry_count=retry_count,
                        metadata={"violations": [v.guardrail_name for v in violations]},
                    )
                )
                state.status = PipelineStatus.FAILED
                state.error = f"Guardrail violation: {violations[0].guardrail_name}"
                state.completed_at = time.time()
                return state

            # Parse verdict from QA agent output
            verdict = Verdict.PASS  # Default for non-QA stages
            if stage.handoff_type == HandoffType.QA_PASS:
                verdict_result = parse_verdict(output)
                verdict = verdict_result.verdict

            # Build handoff data
            handoff = HandoffData(
                source_agent=stage.agent_key,
                target_agent=(
                    stages[state.current_stage_index + 1].agent_key
                    if state.current_stage_index + 1 < len(stages)
                    else "pipeline_complete"
                ),
                handoff_type=stage.handoff_type,
                payload={"output": output, "input": current_input},
                retry_count=retry_count,
                max_retries=max_retries,
            )

            # Handle QA fail (verdict parsing)
            if verdict == Verdict.FAIL:
                handoff = HandoffData(
                    source_agent=handoff.source_agent,
                    target_agent=handoff.target_agent,
                    handoff_type=HandoffType.QA_FAIL,
                    payload=handoff.payload,
                    context={"feedback": output},
                    retry_count=retry_count,
                    max_retries=max_retries,
                )

            handoff_result = process_handoff(handoff)
            state.handoff_history.append(handoff_result)

            # Record stage result
            state.results.append(
                StageResult(
                    stage_name=stage.name,
                    agent_key=stage.agent_key,
                    output=output,
                    verdict=verdict,
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                )
            )

            # Act on handoff result
            if handoff_result.action == "continue":
                current_input = output
                break  # Exit retry loop, move to next stage

            elif handoff_result.action == "retry":
                retry_count += 1
                logger.info(
                    "Pipeline %s: retrying stage '%s' (%d/%d)",
                    pipeline_id,
                    stage.name,
                    retry_count,
                    max_retries,
                )
                # Feed back the QA feedback as input for the retry
                current_input = (
                    f"Previous output was rejected. Feedback:\n{output}\n\n"
                    f"Original input:\n{handoff.payload.get('input', current_input)}"
                )
                continue  # Retry same stage

            elif handoff_result.action == "escalate":
                state.status = PipelineStatus.ESCALATED
                state.error = handoff_result.message
                state.completed_at = time.time()
                logger.warning(
                    "Pipeline %s: escalated at stage '%s'",
                    pipeline_id,
                    stage.name,
                )
                return state

            elif handoff_result.action == "await_approval":
                state.status = PipelineStatus.AWAITING_APPROVAL
                state.completed_at = time.time()
                logger.info(
                    "Pipeline %s: awaiting approval at stage '%s'",
                    pipeline_id,
                    stage.name,
                )
                return state

            elif handoff_result.action == "checkpoint":
                current_input = output
                break  # Continue to next stage after checkpoint

            elif handoff_result.action == "halt":
                state.status = PipelineStatus.FAILED
                state.error = handoff_result.message
                state.completed_at = time.time()
                return state

            else:
                # Unknown action — treat as continue
                logger.warning(
                    "Unknown handoff action '%s', treating as continue",
                    handoff_result.action,
                )
                current_input = output
                break

        # Move to next stage
        state.current_stage_index += 1

    # All stages complete
    state.status = PipelineStatus.COMPLETED
    state.completed_at = time.time()
    logger.info(
        "Pipeline %s completed in %.0fms (%d stages)",
        pipeline_id,
        state.total_duration_ms,
        len(stages),
    )
    return state
