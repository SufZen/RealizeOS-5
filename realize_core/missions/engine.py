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

import asyncio
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


# Held approval id -> (engine, mission id, step id) waiting on it.
_held_steps: dict[str, tuple] = {}
# Continuations started after a decision (kept so they aren't garbage-collected).
_continuations: set = set()


async def on_approval_decided(approval_id: str, approved: bool, execution: dict | None = None) -> bool:
    """Let the mission step waiting on ``approval_id`` continue from the real outcome.

    Called by the approval decision path; a no-op for approvals no mission
    waits on. When the mission has nothing left waiting it continues in the
    background. Returns True when a mission step was updated.
    """
    entry = _held_steps.pop(approval_id, None)
    if entry is None:
        return False
    engine, mission_id, step_id = entry
    if engine.record_approval(mission_id, step_id, approval_id, approved, execution):
        task = asyncio.ensure_future(engine.execute_mission(mission_id))
        _continuations.add(task)
        task.add_done_callback(_continuations.discard)
    return True


def _settle_step(step: MissionStep, final_status: str | None, requested: list[str]) -> None:
    """Set a step's status from how its runtime run ended (Codex audit N02).

    Runtimes end with ``success``, ``partial`` or ``failed``. The internal
    runtime reports ``partial`` when an action was held for an operator, so:

    - an error, a rejection that arrived while the step ran, or ``failed``: FAILED;
    - approvals still undecided (``success`` or ``partial``): AWAITING_APPROVAL,
      and the step's dependants wait for the decision;
    - every requested approval was granted while the step ran: SUCCEEDED;
    - ``success`` with nothing held: SUCCEEDED;
    - ``partial`` with nothing held, no final result, or an unknown status:
      FAILED. An error is never turned into a wait.
    """
    if step.status == StepStatus.FAILED:
        return  # an error event, an exception, or a rejection decided mid-run
    if final_status == "failed":
        step.status = StepStatus.FAILED
        step.error = step.error or "The runtime reported that the step failed"
    elif final_status in ("success", "partial", None) and step.pending_approvals:
        # Whatever the runtime said, the step's work isn't done until the
        # held actions are decided; its dependants must wait.
        step.status = StepStatus.AWAITING_APPROVAL
    elif final_status in ("success", "partial") and requested:
        step.status = StepStatus.SUCCEEDED  # everything it asked for was approved and done
    elif final_status == "success":
        step.status = StepStatus.SUCCEEDED
    else:
        step.status = StepStatus.FAILED
        if final_status == "partial":
            step.error = step.error or "The runtime returned a partial result with nothing waiting for approval"
        elif final_status is None:
            step.error = step.error or "The runtime ended without a result"
        else:
            step.error = step.error or f"The runtime returned an unknown status: {final_status}"


#: Upper bounds on a plan, so validating (and running) one stays cheap.
MAX_PLAN_STEPS = 100
MAX_STEP_INPUTS = 20


def validate_plan(steps: list[dict]) -> list[dict]:
    """Check a mission plan before it is stored (Codex audit F16).

    Every step needs a description; step ids (given or the default s1, s2,
    ...) must be unique; ``inputs_from`` must name steps of this plan and the
    dependencies must not form a cycle, or the mission could never finish.
    Plans are bounded (``MAX_PLAN_STEPS`` steps, ``MAX_STEP_INPUTS`` inputs
    per step) and checked in linear time, so a request can't make this slow.

    Returns the steps unchanged.

    Raises:
        ValueError: what is wrong, in words a caller can show.
    """
    if not isinstance(steps, list) or not steps:
        raise ValueError("A plan needs at least one step")
    if len(steps) > MAX_PLAN_STEPS:
        raise ValueError(f"A plan can have at most {MAX_PLAN_STEPS} steps")
    deps: dict[str, list[str]] = {}
    for i, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"Step {i} must be an object")
        description = step.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Step {i} needs a description")
        step_id = str(step.get("step_id") or f"s{i}")
        if step_id in deps:
            raise ValueError(f"Step id '{step_id}' is used twice")
        inputs = step.get("inputs_from") or []
        if not isinstance(inputs, list) or not all(isinstance(x, str) for x in inputs):
            raise ValueError(f"Step '{step_id}': inputs_from must be a list of step ids")
        if len(inputs) > MAX_STEP_INPUTS:
            raise ValueError(f"Step '{step_id}' can depend on at most {MAX_STEP_INPUTS} steps")
        deps[step_id] = list(dict.fromkeys(inputs))
    for step_id, inputs in deps.items():
        unknown = [x for x in inputs if x not in deps]
        if unknown:
            raise ValueError(f"Step '{step_id}' depends on unknown step(s): {', '.join(unknown)}")

    # Kahn's algorithm in O(steps + dependencies): whatever can't be ordered is on a cycle.
    waiting = {step_id: len(inputs) for step_id, inputs in deps.items()}
    dependants: dict[str, list[str]] = {step_id: [] for step_id in deps}
    for step_id, inputs in deps.items():
        for dep in inputs:
            dependants[dep].append(step_id)
    ready = [step_id for step_id, count in waiting.items() if count == 0]
    while ready:
        done = ready.pop()
        for step_id in dependants[done]:
            waiting[step_id] -= 1
            if waiting[step_id] == 0:
                ready.append(step_id)
    cyclic = sorted(step_id for step_id, count in waiting.items() if count > 0)
    if cyclic:
        raise ValueError(f"Steps depend on each other in a cycle: {', '.join(cyclic[:10])}")
    return steps


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
        steps = validate_plan(steps)  # before anything about the mission changes
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

        resumable = mission.state == MissionState.AWAITING_APPROVAL and not any(
            s.status == StepStatus.AWAITING_APPROVAL for s in mission.plan
        )
        if mission.state not in (MissionState.PLANNED, MissionState.PAUSED) and not resumable:
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

            awaiting = [s.step_id for s in mission.plan if s.status == StepStatus.AWAITING_APPROVAL]
            if mission.state != MissionState.IN_PROGRESS:
                pass  # already failed (budget)
            elif awaiting:
                mission.transition(MissionState.AWAITING_APPROVAL)
                mission.outcome_summary = f"Waiting for operator approval: {', '.join(awaiting)}"
                self._log_event(mission, "awaiting_approval", steps=awaiting)
            elif not all(s.is_complete for s in mission.plan):
                # Nothing can run: the remaining steps depend on steps that failed.
                blocked = [s.step_id for s in mission.plan if not s.is_complete]
                mission.transition(MissionState.FAILED)
                mission.outcome_summary = f"Steps blocked by failed prerequisites: {', '.join(blocked)}"
                self._log_event(mission, "failed", blocked_steps=blocked)
            # All steps completed
            elif all(s.is_complete for s in mission.plan):
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

        requested: list[str] = []  # approvals this run asked for
        final_status: str | None = None
        try:
            async for event in runtime_entry.runtime.invoke(runtime_step, context):
                if event.kind == "approval_request":
                    request_id = (getattr(event, "proposed_action", None) or {}).get("request_id")
                    if request_id:
                        requested.append(request_id)
                        step.pending_approvals.append(request_id)
                        _held_steps[request_id] = (self, mission.mission_id, step.step_id)
                elif event.kind == "final":
                    # Merge: an approval decided while the step ran may already have added its output.
                    step.output = {**(event.output or {}), **step.output}
                    final_status = event.status
                    if hasattr(event, "cost_actual") and isinstance(event.cost_actual, dict):
                        step.cost_eur = event.cost_actual.get("actual_cost_eur", 0)
                        step.cost_tokens = event.cost_actual.get("actual_tokens", 0)
                elif event.kind == "error":
                    step.status = StepStatus.FAILED
                    step.error = event.message

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)

        _settle_step(step, final_status, requested)

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

    def record_approval(self, mission_id: str, step_id: str, approval_id: str, approved: bool, execution: dict | None):
        """Apply an operator decision to the step that was waiting on it.

        A rejection, or an approved action that failed, fails the step. Once a
        step has no undecided approvals left it succeeds, carrying the actual
        outputs. Returns True when the mission can continue.
        """
        mission = self._get_mission(mission_id)
        step = next((s for s in mission.plan if s.step_id == step_id), None)
        if step is None or approval_id not in step.pending_approvals:
            return False
        step.pending_approvals.remove(approval_id)
        if not approved or not (execution or {}).get("success"):
            step.status = StepStatus.FAILED
            step.error = "an action it needed was not approved" if not approved else (execution or {}).get("error", "")
        else:
            step.output = {**(step.output or {}), "approved_output": (execution or {}).get("output", "")}
            if not step.pending_approvals and step.status == StepStatus.AWAITING_APPROVAL:
                step.status = StepStatus.SUCCEEDED
            # A step still running settles itself when its runtime finishes (_settle_step).
        self._log_event(mission, "approval_decided", step_id=step_id, approved=approved)
        return mission.state == MissionState.AWAITING_APPROVAL and not any(
            s.status == StepStatus.AWAITING_APPROVAL for s in mission.plan
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
