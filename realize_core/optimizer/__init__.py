"""Optimizer — experiment framework for A/B testing prompts, models, and parameters."""

from realize_core.optimizer.base import (
    BaseExperiment,
    ExperimentResult,
    ExperimentStatus,
    OptimizationDomain,
    OptimizationTarget,
)
from realize_core.optimizer.engine import EngineConfig, ExperimentEngine
from realize_core.optimizer.metrics import (
    BUILTIN_METRICS,
    MetricComparison,
    MetricDefinition,
    MetricDirection,
    MetricResult,
    SignificanceLevel,
    compare_groups,
    compute_composite_score,
    compute_metric,
)
from realize_core.optimizer.tracker import ExperimentRecord, ExperimentTracker

__all__ = [
    # base
    "BaseExperiment",
    "ExperimentResult",
    "ExperimentStatus",
    "OptimizationDomain",
    "OptimizationTarget",
    # metrics
    "BUILTIN_METRICS",
    "MetricComparison",
    "MetricDefinition",
    "MetricDirection",
    "MetricResult",
    "SignificanceLevel",
    "compare_groups",
    "compute_composite_score",
    "compute_metric",
    # tracker
    "ExperimentRecord",
    "ExperimentTracker",
    # engine
    "EngineConfig",
    "ExperimentEngine",
]
