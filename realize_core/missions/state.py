"""
Mission State Machine.

Defines the Mission, MissionStep, and MissionState data structures.
Handles lifecycle transitions: proposed → planned → in-progress → completed/failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MissionState(str, Enum):
    """Mission lifecycle states."""

    PROPOSED = "proposed"
    PLANNED = "planned"
    IN_PROGRESS = "in-progress"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting-approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Individual step execution status."""

    PENDING = "pending"
    IN_PROGRESS = "in-progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


# Valid state transitions
_VALID_TRANSITIONS = {
    MissionState.PROPOSED: {MissionState.PLANNED, MissionState.CANCELLED},
    MissionState.PLANNED: {MissionState.IN_PROGRESS, MissionState.CANCELLED},
    MissionState.IN_PROGRESS: {
        MissionState.PAUSED,
        MissionState.AWAITING_APPROVAL,
        MissionState.COMPLETED,
        MissionState.FAILED,
        MissionState.CANCELLED,
    },
    MissionState.PAUSED: {MissionState.IN_PROGRESS, MissionState.CANCELLED},
    MissionState.AWAITING_APPROVAL: {MissionState.IN_PROGRESS, MissionState.CANCELLED},
    MissionState.COMPLETED: set(),  # Terminal
    MissionState.FAILED: {MissionState.PROPOSED},  # Can retry
    MissionState.CANCELLED: set(),  # Terminal
}


@dataclass
class MissionStep:
    """A single step in a mission's execution plan."""

    step_id: str
    description: str
    runtime: str = "internal"  # Which runtime executes this step
    agent: str = ""  # Specific agent within the runtime
    action: str = ""  # Action to perform
    args: dict = field(default_factory=dict)
    inputs_from: list[str] = field(default_factory=list)  # Step IDs whose outputs feed this
    expected_output_schema: dict | None = None

    # Execution state
    status: StepStatus = StepStatus.PENDING
    output: dict = field(default_factory=dict)
    error: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cost_eur: float = 0.0
    cost_tokens: int = 0

    @property
    def is_complete(self) -> bool:
        return self.status in (StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED)

    @property
    def duration_sec(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "runtime": self.runtime,
            "agent": self.agent,
            "action": self.action,
            "args": self.args,
            "inputs_from": self.inputs_from,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "cost_eur": self.cost_eur,
            "cost_tokens": self.cost_tokens,
        }


@dataclass
class Mission:
    """
    A goal-oriented work unit executed by one or more agent runtimes.

    Central to the Mission Engine; tracked in Synapse L4 throughout its lifecycle.
    """

    # Identity
    mission_id: str
    title: str
    goal: str
    venture: str = ""
    owner: str = ""

    # State
    state: MissionState = MissionState.PROPOSED

    # Plan
    plan: list[MissionStep] = field(default_factory=list)

    # Constraints
    budget_eur: float | None = None
    deadline: datetime | None = None
    max_duration_sec: int | None = None
    requires_approval_for: list[str] = field(default_factory=list)
    deny_actions: list[str] = field(default_factory=list)

    # Cost tracking
    cost_consumed_eur: float = 0.0
    cost_consumed_tokens: int = 0

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Results
    outcome_summary: str = ""
    produced_entities: list[str] = field(default_factory=list)
    related_decisions: list[str] = field(default_factory=list)

    def transition(self, new_state: MissionState) -> bool:
        """
        Attempt a state transition.

        Returns True if transition is valid and was applied.
        """
        valid_targets = _VALID_TRANSITIONS.get(self.state, set())
        if new_state not in valid_targets:
            return False

        self.state = new_state

        if new_state == MissionState.IN_PROGRESS and self.started_at is None:
            self.started_at = datetime.now()
        elif new_state in (MissionState.COMPLETED, MissionState.FAILED, MissionState.CANCELLED):
            self.completed_at = datetime.now()

        return True

    @property
    def current_step(self) -> MissionStep | None:
        """Get the currently executing step."""
        for step in self.plan:
            if step.status == StepStatus.IN_PROGRESS:
                return step
        return None

    @property
    def next_step(self) -> MissionStep | None:
        """Get the next pending step."""
        for step in self.plan:
            if step.status == StepStatus.PENDING:
                # Check if inputs are ready
                if all(
                    self._get_step(dep) and self._get_step(dep).status == StepStatus.SUCCEEDED
                    for dep in step.inputs_from
                ):
                    return step
        return None

    @property
    def progress(self) -> float:
        """Compute 0.0-1.0 progress based on step completion."""
        if not self.plan:
            return 0.0
        completed = sum(1 for s in self.plan if s.is_complete)
        return completed / len(self.plan)

    @property
    def is_over_budget(self) -> bool:
        """Check if the mission has exceeded its budget."""
        if self.budget_eur is None:
            return False
        return self.cost_consumed_eur > self.budget_eur

    def _get_step(self, step_id: str) -> MissionStep | None:
        """Find a step by ID."""
        for step in self.plan:
            if step.step_id == step_id:
                return step
        return None

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "goal": self.goal,
            "venture": self.venture,
            "owner": self.owner,
            "state": self.state.value,
            "plan": [s.to_dict() for s in self.plan],
            "budget_eur": self.budget_eur,
            "cost_consumed_eur": self.cost_consumed_eur,
            "cost_consumed_tokens": self.cost_consumed_tokens,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "outcome_summary": self.outcome_summary,
            "produced_entities": self.produced_entities,
        }
