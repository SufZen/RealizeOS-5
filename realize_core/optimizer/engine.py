"""
Experiment engine — the auto-research loop runner for RealizeOS.

Implements the experiment lifecycle:
1. Define experiment (target, metrics, sample count)
2. Run evaluation loop (control vs candidate)
3. Compute metrics and compare
4. Decide verdict (improved / regressed / neutral)
5. Record result to tracker

Supports:
- Prompt A/B testing (swap system prompt layers)
- Model selection experiments (compare providers/models)
- Parameter optimization (temperature, max_tokens, etc.)
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from realize_core.optimizer.base import (
    BaseExperiment,
    ExperimentResult,
    ExperimentStatus,
    OptimizationDomain,
    OptimizationTarget,
)
from realize_core.optimizer.metrics import (
    BUILTIN_METRICS,
    MetricComparison,
    MetricDefinition,
    compare_groups,
    compute_composite_score,
)
from realize_core.optimizer.tracker import ExperimentTracker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evaluation function type
# ---------------------------------------------------------------------------

# An evaluator takes (config_dict, sample_id) and returns metric observations
EvaluatorFn = Callable[[dict[str, Any], str], dict[str, float]]


# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------

@dataclass
class EngineConfig:
    """Configuration for an experiment run."""
    metrics: list[str] = field(default_factory=lambda: ["response_quality", "latency_ms", "cost_usd"])
    min_samples: int = 5
    max_samples: int = 50
    min_improvement_pct: float = 5.0
    auto_apply: bool = False  # Auto-apply winning candidates
    stop_early: bool = True   # Stop if significance reached before max_samples


# ---------------------------------------------------------------------------
# Experiment Engine
# ---------------------------------------------------------------------------

class ExperimentEngine:
    """
    Runs optimization experiments in an auto-research loop.

    Usage:
        engine = ExperimentEngine(tracker=tracker)

        # Define the experiment
        experiment = engine.create_experiment(
            name="Prompt layer 3 optimization",
            domain=OptimizationDomain.PROMPT,
            key="system_prompt_layer_3",
            current_value="You are a helpful assistant.",
            candidate_value="You are an expert consultant.",
        )

        # Run with an evaluator function
        result = engine.run(experiment, evaluator=my_eval_fn)
    """

    def __init__(
        self,
        tracker: ExperimentTracker | None = None,
        config: EngineConfig | None = None,
        metric_defs: dict[str, MetricDefinition] | None = None,
    ):
        self._tracker = tracker or ExperimentTracker()
        self._config = config or EngineConfig()
        self._metric_defs = metric_defs or BUILTIN_METRICS

    def create_experiment(
        self,
        name: str,
        domain: OptimizationDomain | str,
        key: str,
        current_value: Any = None,
        candidate_value: Any = None,
        description: str = "",
        tags: list[str] | None = None,
        max_samples: int | None = None,
        min_improvement_pct: float | None = None,
    ) -> BaseExperiment:
        """
        Create and register a new experiment.
        """
        if isinstance(domain, str):
            domain = OptimizationDomain(domain)

        target = OptimizationTarget(
            domain=domain,
            key=key,
            current_value=current_value,
            candidate_value=candidate_value,
            description=description,
        )

        experiment = BaseExperiment(
            id=str(uuid.uuid4())[:8],
            name=name,
            target=target,
            description=description,
            created_at=datetime.now(),
            max_samples=max_samples or self._config.max_samples,
            min_improvement_pct=min_improvement_pct or self._config.min_improvement_pct,
            tags=tags or [],
        )

        self._tracker.register(experiment)
        return experiment

    def run(
        self,
        experiment: BaseExperiment,
        evaluator: EvaluatorFn,
        control_config: dict[str, Any] | None = None,
        candidate_config: dict[str, Any] | None = None,
    ) -> ExperimentResult:
        """
        Run an experiment: evaluate control and candidate, compare, and decide.

        Args:
            experiment: The experiment to run
            evaluator: Function that takes (config, sample_id) and returns metric values
            control_config: Config dict for the control variant (default: use current_value)
            candidate_config: Config dict for the candidate variant (default: use candidate_value)

        Returns:
            ExperimentResult with the verdict
        """
        # Mark as running
        experiment.status = ExperimentStatus.RUNNING
        started_at = datetime.now()

        # Build configs
        ctrl_config = control_config or {"value": experiment.target.current_value}
        cand_config = candidate_config or {"value": experiment.target.candidate_value}

        # Collect metric observations
        control_metrics: dict[str, list[float]] = {m: [] for m in self._config.metrics}
        candidate_metrics: dict[str, list[float]] = {m: [] for m in self._config.metrics}

        samples_run = 0
        for i in range(experiment.max_samples):
            sample_id = f"s{i:03d}"

            # Evaluate control
            try:
                ctrl_obs = evaluator(ctrl_config, f"control_{sample_id}")
                for metric_name in self._config.metrics:
                    if metric_name in ctrl_obs:
                        control_metrics[metric_name].append(ctrl_obs[metric_name])
            except Exception as e:
                logger.warning(f"Control evaluation failed for {sample_id}: {e}")

            # Evaluate candidate
            try:
                cand_obs = evaluator(cand_config, f"candidate_{sample_id}")
                for metric_name in self._config.metrics:
                    if metric_name in cand_obs:
                        candidate_metrics[metric_name].append(cand_obs[metric_name])
            except Exception as e:
                logger.warning(f"Candidate evaluation failed for {sample_id}: {e}")

            samples_run += 1

            # Early stopping check
            if self._config.stop_early and samples_run >= self._config.min_samples:
                comparisons = self._compare_all(control_metrics, candidate_metrics)
                composite = compute_composite_score(comparisons, self._metric_defs)
                if abs(composite) > experiment.min_improvement_pct:
                    logger.info(f"Early stop at sample {samples_run}: composite={composite:+.1f}%")
                    break

        # Final comparison
        comparisons = self._compare_all(control_metrics, candidate_metrics)
        composite_score = compute_composite_score(comparisons, self._metric_defs)

        # Determine verdict
        if composite_score >= experiment.min_improvement_pct:
            status = ExperimentStatus.IMPROVED
        elif composite_score <= -experiment.min_improvement_pct:
            status = ExperimentStatus.REGRESSED
        else:
            status = ExperimentStatus.NEUTRAL

        completed_at = datetime.now()

        result = ExperimentResult(
            experiment_id=experiment.id,
            status=status,
            target=experiment.target,
            control_score=composite_score if composite_score < 0 else 0.0,
            candidate_score=composite_score if composite_score > 0 else 0.0,
            improvement_pct=composite_score,
            sample_size=samples_run,
            started_at=started_at,
            completed_at=completed_at,
            details={
                "comparisons": [
                    {
                        "metric": c.metric_name,
                        "control_mean": c.control_mean,
                        "candidate_mean": c.candidate_mean,
                        "improvement_pct": c.improvement_pct,
                        "significance": str(c.significance),
                    }
                    for c in comparisons
                ],
                "composite_score": composite_score,
                "samples_run": samples_run,
                "early_stopped": samples_run < experiment.max_samples,
            },
        )

        # Record to tracker
        self._tracker.record_result(result)

        logger.info(
            f"Experiment {experiment.id} complete: {status} "
            f"(composite: {composite_score:+.1f}%, samples: {samples_run})"
        )

        return result

    def _compare_all(
        self,
        control_metrics: dict[str, list[float]],
        candidate_metrics: dict[str, list[float]],
    ) -> list[MetricComparison]:
        """Compare all configured metrics between control and candidate."""
        comparisons = []
        for metric_name in self._config.metrics:
            metric_def = self._metric_defs.get(
                metric_name,
                MetricDefinition(name=metric_name),
            )
            ctrl_vals = control_metrics.get(metric_name, [])
            cand_vals = candidate_metrics.get(metric_name, [])

            comparison = compare_groups(metric_def, ctrl_vals, cand_vals)
            comparisons.append(comparison)

        return comparisons

    def cancel(self, experiment: BaseExperiment) -> ExperimentResult:
        """Cancel a running experiment."""
        experiment.status = ExperimentStatus.CANCELLED
        result = ExperimentResult(
            experiment_id=experiment.id,
            status=ExperimentStatus.CANCELLED,
            target=experiment.target,
        )
        self._tracker.record_result(result)
        return result
