"""
Mission Engine — Goal → Plan → Execute.

Orchestrates mission lifecycle:
1. Create a mission from a goal
2. Decompose into steps (plan)
3. Route each step to the best runtime via the Smart Kanban Router
4. Execute steps, collecting events
5. Track costs, handle approvals, write to Synapse L4
"""

from __future__ import annotations

import logging
from datetime import datetime

from realize_core.fabric.event_log import EventLog
from realize_core.fabric.event_types import mission_event
from realize_core.fabric.id_gen import generate_id
from realize_core.missions.state import (
    Mission,
    MissionState,
    MissionStep,
    StepStatus,
)
from realize_core.runtimes.contract import Context, StepConstraints, Task
from realize_core.runtimes.contract import MissionStep as RuntimeMissionStep
from realize_core.runtimes.registry import RuntimeRegistry

logger = logging.getLogger(__name__)


class MissionEngine:
    """
    Core mission orchestrator.

    Manages mission lifecycle: creation, planning, execution, and completion.
    Works with the RuntimeRegistry to route steps to the best runtime.
    """

    def __init__(
        self,
        registry: RuntimeRegistry,
        event_log: EventLog | None = None,
        synapse=None,
    ):
        self._registry = registry
        self._event_log = event_log
        self._synapse = synapse
        self._missions: dict[str, Mission] = {}

    @property
    def missions(self) -> dict[str, Mission]:
        """All tracked missions."""
        return self._missions

    # ─── Mission Lifecycle ────────────────────────────────────────────

    def create_mission(
        self,
        title: str,
        goal: str,
        venture: str = "",
        owner: str = "",
        budget_eur: float | None = None,
        deadline: datetime | None = None,
        requires_approval_for: list[str] | None = None,
    ) -> Mission:
        """
        Create a new mission.

        The mission starts in PROPOSED state. Call plan_mission() to
        decompose it into steps, then execute_mission() to run it.
        """
        mission_id = generate_id("mission", title[:30])

        mission = Mission(
            mission_id=mission_id,
            title=title,
            goal=goal,
            venture=venture,
            owner=owner,
            budget_eur=budget_eur,
            deadline=deadline,
            requires_approval_for=requires_approval_for or [],
        )

        self._missions[mission_id] = mission

        self._log_event(mission, "created", title=title, goal=goal)
        logger.info(f"Mission created: {mission_id} — {title}")
        return mission

    def plan_mission(
        self,
        mission_id: str,
        steps: list[dict],
    ) -> Mission:
        """
        Add an execution plan to a mission.

        Args:
            mission_id: The mission to plan.
            steps: List of step definitions, each with:
                - description (required)
                - runtime (default: "internal")
                - agent (optional)
                - action (optional)
                - args (optional)
                - inputs_from (optional list of step IDs)

        Returns:
            The updated mission.
        """
        mission = self._get_mission(mission_id)

        plan: list[MissionStep] = []
        for i, step_def in enumerate(steps):
            step = MissionStep(
                step_id=step_def.get("step_id", f"s{i + 1}"),
                description=step_def["description"],
                runtime=step_def.get("runtime", "internal"),
                agent=step_def.get("agent", ""),
                action=step_def.get("action", ""),
                args=step_def.get("args", {}),
                inputs_from=step_def.get("inputs_from", []),
            )
            plan.append(step)

        mission.plan = plan
        mission.transition(MissionState.PLANNED)

        self._log_event(mission, "planned", step_count=len(plan))
        logger.info(f"Mission planned: {mission_id} — {len(plan)} steps")
        return mission

    async def execute_mission(self, mission_id: str) -> Mission:
        """
        Execute a mission's plan step by step.

        Routes each step to the best runtime, collects results,
        and tracks costs. Returns the completed mission.
        """
        mission = self._get_mission(mission_id)

        if mission.state not in (MissionState.PLANNED, MissionState.PAUSED):
            raise ValueError(f"Mission {mission_id} cannot be executed from state {mission.state.value}")

        mission.transition(MissionState.IN_PROGRESS)
        self._log_event(mission, "started")

        try:
            while True:
                step = mission.next_step
                if step is None:
                    break

                # Check budget
                if mission.is_over_budget:
                    logger.warning(f"Mission {mission_id} over budget, stopping")
                    mission.transition(MissionState.FAILED)
                    mission.outcome_summary = "Mission exceeded budget"
                    self._log_event(mission, "budget_exceeded")
                    break

                await self._execute_step(mission, step)

            # All steps completed
            if all(s.is_complete for s in mission.plan):
                all_succeeded = all(s.status == StepStatus.SUCCEEDED for s in mission.plan)
                if all_succeeded:
                    mission.transition(MissionState.COMPLETED)
                    self._log_event(mission, "completed")
                else:
                    mission.transition(MissionState.FAILED)
                    failed_steps = [s.step_id for s in mission.plan if s.status == StepStatus.FAILED]
                    mission.outcome_summary = f"Steps failed: {', '.join(failed_steps)}"
                    self._log_event(mission, "failed", failed_steps=failed_steps)

        except Exception as e:
            logger.error(f"Mission {mission_id} execution error: {e}")
            mission.transition(MissionState.FAILED)
            mission.outcome_summary = f"Execution error: {e!s}"
            self._log_event(mission, "error", error=str(e))

        # Update Synapse L4
        self._update_mission_memory(mission)

        return mission

    async def _execute_step(self, mission: Mission, step: MissionStep) -> None:
        """Execute a single mission step through a runtime."""
        step.status = StepStatus.IN_PROGRESS
        step.started_at = datetime.now()

        self._log_event(
            mission,
            "step_started",
            step_id=step.step_id,
            runtime=step.runtime,
            description=step.description,
        )

        # Find the best runtime for this step
        task = Task(
            description=step.description,
            required_capabilities=[step.action] if step.action else [],
            venture_id=mission.venture,
        )

        runtime_entry = None

        # Try the specified runtime first
        if step.runtime:
            runtime_entry = self._registry.get(step.runtime)

        # Fall back to best match
        if runtime_entry is None or runtime_entry.status not in ("ready", "degraded"):
            matches = self._registry.match_runtimes(task)
            if matches:
                runtime_entry = self._registry.get(matches[0][0])

        if runtime_entry is None:
            step.status = StepStatus.FAILED
            step.error = "No runtime available"
            step.completed_at = datetime.now()
            logger.error(f"No runtime for step {step.step_id}")
            return

        # Build context
        context = Context(
            venture_id=mission.venture,
            audit_trace_id=mission.mission_id,
        )

        # Build runtime-level mission step
        runtime_step = RuntimeMissionStep(
            step_id=step.step_id,
            mission_id=mission.mission_id,
            description=step.description,
            inputs=self._gather_inputs(mission, step),
            constraints=StepConstraints(
                max_cost_eur=mission.budget_eur,
                requires_approval_for=mission.requires_approval_for,
                deny_actions=mission.deny_actions,
            ),
        )

        try:
            async for event in runtime_entry.runtime.invoke(runtime_step, context):
                if event.kind == "final":
                    step.output = event.output
                    step.status = StepStatus.SUCCEEDED if event.status == "success" else StepStatus.FAILED
                    if hasattr(event, "cost_actual") and isinstance(event.cost_actual, dict):
                        step.cost_eur = event.cost_actual.get("actual_cost_eur", 0)
                        step.cost_tokens = event.cost_actual.get("actual_tokens", 0)
                elif event.kind == "error":
                    step.status = StepStatus.FAILED
                    step.error = event.message

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)

        step.completed_at = datetime.now()

        # Update mission cost totals
        mission.cost_consumed_eur += step.cost_eur
        mission.cost_consumed_tokens += step.cost_tokens

        # Track runtime usage
        runtime_entry.invocation_count += 1
        runtime_entry.last_used = datetime.now()
        runtime_entry.total_cost_eur += step.cost_eur

        self._log_event(
            mission,
            "step_completed",
            step_id=step.step_id,
            status=step.status.value,
            duration_sec=step.duration_sec,
            cost_eur=step.cost_eur,
        )

    def cancel_mission(self, mission_id: str) -> Mission:
        """Cancel a mission."""
        mission = self._get_mission(mission_id)
        if mission.transition(MissionState.CANCELLED):
            mission.outcome_summary = "Cancelled by user"
            self._log_event(mission, "cancelled")
        return mission

    def pause_mission(self, mission_id: str) -> Mission:
        """Pause a running mission."""
        mission = self._get_mission(mission_id)
        if mission.transition(MissionState.PAUSED):
            self._log_event(mission, "paused")
        return mission

    def get_mission(self, mission_id: str) -> Mission | None:
        """Get a mission by ID."""
        return self._missions.get(mission_id)

    def list_missions(
        self,
        venture: str = "",
        state: str = "",
    ) -> list[Mission]:
        """List missions with optional filters."""
        result = list(self._missions.values())
        if venture:
            result = [m for m in result if m.venture == venture]
        if state:
            result = [m for m in result if m.state.value == state]
        return sorted(result, key=lambda m: m.created_at, reverse=True)

    # ─── Helpers ──────────────────────────────────────────────────────

    def _get_mission(self, mission_id: str) -> Mission:
        mission = self._missions.get(mission_id)
        if mission is None:
            raise ValueError(f"Mission not found: {mission_id}")
        return mission

    def _gather_inputs(self, mission: Mission, step: MissionStep) -> dict:
        """Gather outputs from dependency steps."""
        inputs = {}
        for dep_id in step.inputs_from:
            dep = mission._get_step(dep_id)
            if dep and dep.output:
                inputs[dep_id] = dep.output
        return inputs

    def _log_event(self, mission: Mission, action: str, **payload) -> None:
        """Log a mission event."""
        if self._event_log:
            event = mission_event(
                mission_id=mission.mission_id,
                action=action,
                venture=mission.venture,
                **payload,
            )
            self._event_log.append(event)

    def _update_mission_memory(self, mission: Mission) -> None:
        """Update Synapse L4 mission memory."""
        if self._synapse:
            self._synapse.update_mission_memory(
                mission_id=mission.mission_id,
                summary=mission.outcome_summary or f"{mission.title}: {mission.state.value}",
                decisions=mission.related_decisions,
                blockers=[s.error for s in mission.plan if s.status == StepStatus.FAILED and s.error],
            )
