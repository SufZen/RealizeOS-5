"""
KPI definition and measurement for RealizeOS experiments.

Provides a framework for defining, computing, and comparing metrics:
- MetricDefinition: declarative metric specification
- MetricResult: a single metric observation
- MetricComparison: control vs candidate comparison with significance

Metrics can measure anything: response quality, latency, cost, token usage,
user satisfaction, etc. They are consumed by the ExperimentEngine.
"""

from __future__ import annotations

import logging
import math
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MetricDirection(StrEnum):
    """Whether higher or lower is better for a metric."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class SignificanceLevel(StrEnum):
    """Statistical significance of a comparison."""

    SIGNIFICANT = "significant"
    MARGINAL = "marginal"
    NOT_SIGNIFICANT = "not_significant"


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricDefinition:
    """
    Declarative specification for a measurable KPI.

    Examples:
        MetricDefinition("response_quality", direction=HIGHER_IS_BETTER, weight=1.0)
        MetricDefinition("token_cost", direction=LOWER_IS_BETTER, unit="tokens")
        MetricDefinition("latency_ms", direction=LOWER_IS_BETTER, threshold=500)
    """

    name: str
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER
    weight: float = 1.0  # relative importance in composite scoring
    unit: str = ""
    description: str = ""
    threshold: float | None = None  # optional pass/fail threshold
    compute_fn: Callable[..., float] | None = None  # optional custom computation

    def is_passing(self, value: float) -> bool:
        """Check whether a value passes the threshold (if defined)."""
        if self.threshold is None:
            return True
        if self.direction == MetricDirection.HIGHER_IS_BETTER:
            return value >= self.threshold
        return value <= self.threshold


@dataclass
class MetricResult:
    """A single observation of a metric."""

    metric_name: str
    value: float
    sample_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricComparison:
    """
    Statistical comparison between control and candidate for one metric.
    """

    metric_name: str
    control_mean: float
    candidate_mean: float
    control_std: float = 0.0
    candidate_std: float = 0.0
    control_n: int = 0
    candidate_n: int = 0
    improvement_pct: float = 0.0
    significance: SignificanceLevel = SignificanceLevel.NOT_SIGNIFICANT
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER

    @property
    def is_improved(self) -> bool:
        """True if candidate is better than control in the right direction."""
        if self.direction == MetricDirection.HIGHER_IS_BETTER:
            return self.candidate_mean > self.control_mean
        return self.candidate_mean < self.control_mean


# ---------------------------------------------------------------------------
# Built-in metric definitions
# ---------------------------------------------------------------------------

# Standard metrics for LLM optimization
BUILTIN_METRICS: dict[str, MetricDefinition] = {
    "response_quality": MetricDefinition(
        name="response_quality",
        direction=MetricDirection.HIGHER_IS_BETTER,
        weight=1.0,
        unit="score",
        description="LLM-judged response quality (0-100)",
    ),
    "token_count": MetricDefinition(
        name="token_count",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=0.3,
        unit="tokens",
        description="Total tokens used (prompt + completion)",
    ),
    "prompt_tokens": MetricDefinition(
        name="prompt_tokens",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=0.2,
        unit="tokens",
        description="System prompt token count",
    ),
    "completion_tokens": MetricDefinition(
        name="completion_tokens",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=0.1,
        unit="tokens",
        description="Completion token count",
    ),
    "latency_ms": MetricDefinition(
        name="latency_ms",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=0.5,
        unit="ms",
        description="End-to-end response latency",
        threshold=5000,  # 5 seconds max
    ),
    "cost_usd": MetricDefinition(
        name="cost_usd",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=0.4,
        unit="USD",
        description="Request cost in USD",
    ),
    "user_satisfaction": MetricDefinition(
        name="user_satisfaction",
        direction=MetricDirection.HIGHER_IS_BETTER,
        weight=1.5,
        unit="rating",
        description="User satisfaction score (1-5)",
        threshold=3.0,
    ),
    "task_success": MetricDefinition(
        name="task_success",
        direction=MetricDirection.HIGHER_IS_BETTER,
        weight=2.0,
        unit="ratio",
        description="Task completion success rate (0-1)",
        threshold=0.8,
    ),
}


# ---------------------------------------------------------------------------
# Metric computation helpers
# ---------------------------------------------------------------------------


def compute_metric(
    definition: MetricDefinition,
    data: dict[str, Any],
) -> float:
    """
    Compute a metric value from response data.

    If the definition has a custom compute_fn, use it.
    Otherwise, look for the metric name as a key in data.
    """
    if definition.compute_fn:
        return definition.compute_fn(data)
    return float(data.get(definition.name, 0.0))


def compare_groups(
    metric_def: MetricDefinition,
    control_values: list[float],
    candidate_values: list[float],
    min_significance_pct: float = 5.0,
) -> MetricComparison:
    """
    Statistically compare control vs candidate metric values.

    Uses a simple effect size check (not a full t-test) for speed.
    """
    if not control_values or not candidate_values:
        return MetricComparison(
            metric_name=metric_def.name,
            control_mean=0.0,
            candidate_mean=0.0,
            direction=metric_def.direction,
        )

    ctrl_mean = statistics.mean(control_values)
    cand_mean = statistics.mean(candidate_values)
    ctrl_std = statistics.stdev(control_values) if len(control_values) > 1 else 0.0
    cand_std = statistics.stdev(candidate_values) if len(candidate_values) > 1 else 0.0

    # Calculate improvement percentage
    if ctrl_mean == 0:
        improvement_pct = 100.0 if cand_mean > 0 else 0.0
    else:
        raw_pct = ((cand_mean - ctrl_mean) / abs(ctrl_mean)) * 100
        # For LOWER_IS_BETTER, flip the sign
        if metric_def.direction == MetricDirection.LOWER_IS_BETTER:
            improvement_pct = -raw_pct  # Lower is better → negative change is improvement
        else:
            improvement_pct = raw_pct

    # Simple significance check based on effect size + sample size
    pooled_std = math.sqrt((ctrl_std**2 + cand_std**2) / 2) if (ctrl_std > 0 or cand_std > 0) else 0.0

    if pooled_std > 0:
        effect_size = abs(cand_mean - ctrl_mean) / pooled_std
    else:
        effect_size = float("inf") if cand_mean != ctrl_mean else 0.0

    min_samples = min(len(control_values), len(candidate_values))

    if effect_size > 0.8 and min_samples >= 5:
        significance = SignificanceLevel.SIGNIFICANT
    elif effect_size > 0.5 and min_samples >= 3:
        significance = SignificanceLevel.MARGINAL
    else:
        significance = SignificanceLevel.NOT_SIGNIFICANT

    return MetricComparison(
        metric_name=metric_def.name,
        control_mean=ctrl_mean,
        candidate_mean=cand_mean,
        control_std=ctrl_std,
        candidate_std=cand_std,
        control_n=len(control_values),
        candidate_n=len(candidate_values),
        improvement_pct=improvement_pct,
        significance=significance,
        direction=metric_def.direction,
    )


def compute_composite_score(
    comparisons: list[MetricComparison],
    metric_defs: dict[str, MetricDefinition] | None = None,
) -> float:
    """
    Compute a weighted composite improvement score across all metrics.

    Returns a score where positive = improvement, negative = regression.
    """
    if not comparisons:
        return 0.0

    defs = metric_defs or BUILTIN_METRICS
    total_weight = 0.0
    weighted_sum = 0.0

    for comp in comparisons:
        weight = defs.get(comp.metric_name, MetricDefinition(name=comp.metric_name)).weight
        total_weight += weight
        weighted_sum += comp.improvement_pct * weight

    if total_weight == 0:
        return 0.0

    return weighted_sum / total_weight
