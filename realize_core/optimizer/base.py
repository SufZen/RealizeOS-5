"""
Optimizer base interfaces for RealizeOS experiment & optimization system.

Defines the shared contracts for A/B experiments and prompt optimization:
- BaseExperiment: Abstract base for experiment definitions
- ExperimentResult: Outcome record for a completed experiment run
- OptimizationTarget: What is being optimized (prompt, model, parameter)
- ExperimentStatus: Lifecycle enum for experiment tracking

Used by Agent 3's Sprint 4 optimizer implementations.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExperimentStatus(StrEnum):
    """Lifecycle status of an experiment."""
    PENDING = "pending"
    RUNNING = "running"
    IMPROVED = "improved"
    REGRESSED = "regressed"
    NEUTRAL = "neutral"
    CANCELLED = "cancelled"


class OptimizationDomain(StrEnum):
    """What domain the optimization targets."""
    PROMPT = "prompt"
    MODEL_SELECTION = "model_selection"
    PARAMETER = "parameter"
    ROUTING = "routing"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizationTarget:
    """
    Specifies what is being optimized in an experiment.

    Examples:
        - domain=PROMPT, key="system_prompt_layer_3"
        - domain=MODEL_SELECTION, key="complex_task_provider"
        - domain=PARAMETER, key="temperature"
    """
    domain: OptimizationDomain
    key: str
    description: str = ""
    current_value: Any = None
    candidate_value: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentResult:
    """
    Outcome of a completed experiment run.

    Captures the metrics comparison between control and candidate,
    the verdict (improved / regressed / neutral), and timing.
    """
    experiment_id: str
    status: ExperimentStatus
    target: OptimizationTarget
    control_score: float = 0.0
    candidate_score: float = 0.0
    improvement_pct: float = 0.0
    sample_size: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_positive(self) -> bool:
        """True if the experiment showed improvement."""
        return self.status == ExperimentStatus.IMPROVED

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock duration of the experiment, if completed."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class BaseExperiment:
    """
    Base definition for an optimization experiment.

    Concrete experiment runners extend this with domain-specific
    evaluation logic (e.g. prompt A/B test, model benchmark).
    """
    id: str
    name: str
    target: OptimizationTarget
    status: ExperimentStatus = ExperimentStatus.PENDING
    description: str = ""
    created_at: datetime | None = None
    max_samples: int = 100
    min_improvement_pct: float = 5.0  # minimum % improvement to accept
    tags: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """True if the experiment is running or pending."""
        return self.status in (ExperimentStatus.PENDING, ExperimentStatus.RUNNING)

    @property
    def is_complete(self) -> bool:
        """True if the experiment has reached a terminal state."""
        return self.status in (
            ExperimentStatus.IMPROVED,
            ExperimentStatus.REGRESSED,
            ExperimentStatus.NEUTRAL,
            ExperimentStatus.CANCELLED,
        )
