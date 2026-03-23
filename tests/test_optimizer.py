"""
Tests for realize_core.optimizer — engine, tracker, and metrics.

Covers:
- MetricDefinition (direction, threshold, weight)
- MetricComparison via compare_groups
- Composite scoring
- ExperimentTracker (register, record, list, filter, persistence)
- ExperimentEngine (create, run, early stop, cancel)
- Token optimization in prompt builder (estimate_tokens, truncate_to_budget, deduplicate_layers)
"""

import pytest
from realize_core.optimizer.base import (
    BaseExperiment,
    ExperimentResult,
    ExperimentStatus,
    OptimizationDomain,
    OptimizationTarget,
)
from realize_core.optimizer.engine import (
    EngineConfig,
    ExperimentEngine,
)
from realize_core.optimizer.metrics import (
    BUILTIN_METRICS,
    MetricComparison,
    MetricDefinition,
    MetricDirection,
    SignificanceLevel,
    compare_groups,
    compute_composite_score,
    compute_metric,
)
from realize_core.optimizer.tracker import (
    ExperimentRecord,
    ExperimentTracker,
)
from realize_core.prompt.builder import (
    _get_layer_priority,
    build_system_prompt,
    clear_cache,
    deduplicate_layers,
    estimate_tokens,
    truncate_to_budget,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def tmp_experiments_dir(tmp_path):
    """Temporary experiments directory."""
    d = tmp_path / "experiments"
    d.mkdir()
    return d


@pytest.fixture
def tracker(tmp_experiments_dir):
    """Fresh ExperimentTracker with temp directory."""
    return ExperimentTracker(experiments_dir=tmp_experiments_dir, enable_git=False)


@pytest.fixture
def sample_target():
    return OptimizationTarget(
        domain=OptimizationDomain.PROMPT,
        key="system_prompt_v2",
        description="Test prompt optimization",
        current_value="You are helpful.",
        candidate_value="You are an expert consultant.",
    )


@pytest.fixture
def sample_experiment(sample_target):
    return BaseExperiment(
        id="exp-001",
        name="Test Prompt Experiment",
        target=sample_target,
        description="Testing prompt A vs B",
        max_samples=10,
        min_improvement_pct=5.0,
        tags=["prompt", "test"],
    )


# ===========================================================================
# Metrics: MetricDefinition
# ===========================================================================


class TestMetricDefinition:
    def test_higher_is_better_threshold(self):
        m = MetricDefinition(
            name="quality",
            direction=MetricDirection.HIGHER_IS_BETTER,
            threshold=80.0,
        )
        assert m.is_passing(90.0)
        assert m.is_passing(80.0)
        assert not m.is_passing(79.9)

    def test_lower_is_better_threshold(self):
        m = MetricDefinition(
            name="latency",
            direction=MetricDirection.LOWER_IS_BETTER,
            threshold=500.0,
        )
        assert m.is_passing(400.0)
        assert m.is_passing(500.0)
        assert not m.is_passing(501.0)

    def test_no_threshold_always_passes(self):
        m = MetricDefinition(name="score")
        assert m.is_passing(0.0)
        assert m.is_passing(-100.0)

    def test_builtin_metrics_exist(self):
        assert "response_quality" in BUILTIN_METRICS
        assert "latency_ms" in BUILTIN_METRICS
        assert "cost_usd" in BUILTIN_METRICS
        assert "token_count" in BUILTIN_METRICS
        assert "task_success" in BUILTIN_METRICS
        assert len(BUILTIN_METRICS) >= 8

    def test_metric_default_direction(self):
        m = MetricDefinition(name="test")
        assert m.direction == MetricDirection.HIGHER_IS_BETTER

    def test_custom_compute_fn(self):
        m = MetricDefinition(
            name="custom",
            compute_fn=lambda data: data.get("a", 0) + data.get("b", 0),
        )
        result = compute_metric(m, {"a": 3, "b": 7})
        assert result == 10.0


# ===========================================================================
# Metrics: compare_groups
# ===========================================================================


class TestCompareGroups:
    def test_basic_comparison(self):
        m = MetricDefinition(name="quality", direction=MetricDirection.HIGHER_IS_BETTER)
        result = compare_groups(m, [70, 72, 68], [85, 87, 83])
        assert result.is_improved
        assert result.candidate_mean > result.control_mean
        assert result.improvement_pct > 0

    def test_regression_detected(self):
        m = MetricDefinition(name="quality", direction=MetricDirection.HIGHER_IS_BETTER)
        result = compare_groups(m, [90, 92, 88], [70, 72, 68])
        assert not result.is_improved
        assert result.improvement_pct < 0

    def test_lower_is_better_comparison(self):
        m = MetricDefinition(name="latency", direction=MetricDirection.LOWER_IS_BETTER)
        result = compare_groups(m, [500, 520, 480], [300, 310, 290])
        assert result.is_improved  # Lower latency = better

    def test_empty_values_return_zeros(self):
        m = MetricDefinition(name="test")
        result = compare_groups(m, [], [])
        assert result.control_mean == 0.0
        assert result.candidate_mean == 0.0

    def test_significance_with_large_effect(self):
        m = MetricDefinition(name="test")
        result = compare_groups(
            m,
            [50, 52, 48, 51, 49, 50, 51],
            [90, 92, 88, 91, 89, 90, 91],
        )
        assert result.significance == SignificanceLevel.SIGNIFICANT

    def test_no_significance_small_sample(self):
        m = MetricDefinition(name="test")
        result = compare_groups(m, [50], [55])
        # Single sample can't be significant
        assert result.significance != SignificanceLevel.SIGNIFICANT


# ===========================================================================
# Metrics: composite score
# ===========================================================================


class TestCompositeScore:
    def test_positive_composite(self):
        comparisons = [
            MetricComparison(
                metric_name="quality",
                control_mean=70,
                candidate_mean=85,
                improvement_pct=21.4,
                direction=MetricDirection.HIGHER_IS_BETTER,
            ),
            MetricComparison(
                metric_name="latency_ms",
                control_mean=500,
                candidate_mean=300,
                improvement_pct=40.0,
                direction=MetricDirection.LOWER_IS_BETTER,
            ),
        ]
        score = compute_composite_score(comparisons)
        assert score > 0

    def test_negative_composite(self):
        comparisons = [
            MetricComparison(
                metric_name="quality",
                control_mean=85,
                candidate_mean=70,
                improvement_pct=-17.6,
                direction=MetricDirection.HIGHER_IS_BETTER,
            ),
        ]
        score = compute_composite_score(comparisons)
        assert score < 0

    def test_empty_comparisons_return_zero(self):
        assert compute_composite_score([]) == 0.0


# ===========================================================================
# Tracker: Registration & Recording
# ===========================================================================


class TestExperimentTracker:
    def test_register_experiment(self, tracker, sample_experiment):
        record = tracker.register(sample_experiment)
        assert record.experiment.id == "exp-001"
        assert record.experiment.name == "Test Prompt Experiment"
        assert record.created_at != ""

    def test_get_experiment(self, tracker, sample_experiment):
        tracker.register(sample_experiment)
        record = tracker.get("exp-001")
        assert record is not None
        assert record.experiment.id == "exp-001"

    def test_get_nonexistent_returns_none(self, tracker):
        assert tracker.get("nonexistent") is None

    def test_record_result(self, tracker, sample_experiment, sample_target):
        tracker.register(sample_experiment)
        result = ExperimentResult(
            experiment_id="exp-001",
            status=ExperimentStatus.IMPROVED,
            target=sample_target,
            control_score=70.0,
            candidate_score=85.0,
            improvement_pct=21.4,
            sample_size=10,
        )
        record = tracker.record_result(result)
        assert record is not None
        assert len(record.results) == 1
        assert record.experiment.status == ExperimentStatus.IMPROVED

    def test_record_result_unknown_experiment(self, tracker, sample_target):
        result = ExperimentResult(
            experiment_id="unknown",
            status=ExperimentStatus.IMPROVED,
            target=sample_target,
        )
        record = tracker.record_result(result)
        assert record is None

    def test_list_experiments_all(self, tracker, sample_experiment):
        tracker.register(sample_experiment)
        records = tracker.list_experiments()
        assert len(records) == 1

    def test_list_experiments_by_status(self, tracker, sample_experiment):
        tracker.register(sample_experiment)
        pending = tracker.list_experiments(status=ExperimentStatus.PENDING)
        assert len(pending) == 1
        improved = tracker.list_experiments(status=ExperimentStatus.IMPROVED)
        assert len(improved) == 0

    def test_list_experiments_by_domain(self, tracker, sample_experiment):
        tracker.register(sample_experiment)
        prompt = tracker.list_experiments(domain=OptimizationDomain.PROMPT)
        assert len(prompt) == 1
        routing = tracker.list_experiments(domain=OptimizationDomain.ROUTING)
        assert len(routing) == 0

    def test_list_experiments_by_tag(self, tracker, sample_experiment):
        tracker.register(sample_experiment)
        tagged = tracker.list_experiments(tag="prompt")
        assert len(tagged) == 1
        untagged = tracker.list_experiments(tag="unrelated")
        assert len(untagged) == 0

    def test_delete_experiment(self, tracker, sample_experiment):
        tracker.register(sample_experiment)
        assert tracker.delete("exp-001")
        assert tracker.get("exp-001") is None
        assert not tracker.delete("exp-001")  # Already deleted

    def test_clear_all(self, tracker, sample_experiment):
        tracker.register(sample_experiment)
        count = tracker.clear_all()
        assert count == 1
        assert len(tracker.list_experiments()) == 0

    def test_summary(self, tracker, sample_experiment):
        tracker.register(sample_experiment)
        summary = tracker.summary()
        assert summary["total"] == 1
        assert "pending" in summary["by_status"]

    def test_persistence_roundtrip(self, tmp_experiments_dir, sample_experiment, sample_target):
        """Data survives tracker restart."""
        # Write
        t1 = ExperimentTracker(experiments_dir=tmp_experiments_dir, enable_git=False)
        t1.register(sample_experiment)
        result = ExperimentResult(
            experiment_id="exp-001",
            status=ExperimentStatus.IMPROVED,
            target=sample_target,
            improvement_pct=15.0,
            sample_size=10,
        )
        t1.record_result(result)

        # Read with a new tracker instance
        t2 = ExperimentTracker(experiments_dir=tmp_experiments_dir, enable_git=False)
        record = t2.get("exp-001")
        assert record is not None
        assert len(record.results) == 1
        assert record.results[0].improvement_pct == 15.0


# ===========================================================================
# Tracker: ExperimentRecord serialization
# ===========================================================================


class TestExperimentRecordSerialization:
    def test_to_dict_roundtrip(self, sample_experiment, sample_target):
        record = ExperimentRecord(
            experiment=sample_experiment,
            results=[
                ExperimentResult(
                    experiment_id="exp-001",
                    status=ExperimentStatus.IMPROVED,
                    target=sample_target,
                    improvement_pct=10.0,
                )
            ],
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T01:00:00",
        )
        data = record.to_dict()
        restored = ExperimentRecord.from_dict(data)

        assert restored.experiment.id == "exp-001"
        assert restored.experiment.name == "Test Prompt Experiment"
        assert len(restored.results) == 1
        assert restored.results[0].improvement_pct == 10.0

    def test_from_dict_with_minimal_data(self):
        data = {
            "experiment": {
                "id": "min",
                "name": "Minimal",
                "target": {"domain": "prompt", "key": "test"},
            },
        }
        record = ExperimentRecord.from_dict(data)
        assert record.experiment.id == "min"
        assert record.experiment.target.domain == OptimizationDomain.PROMPT


# ===========================================================================
# Engine: ExperimentEngine
# ===========================================================================


class TestExperimentEngine:
    def test_create_experiment(self, tracker):
        engine = ExperimentEngine(tracker=tracker)
        exp = engine.create_experiment(
            name="Test",
            domain=OptimizationDomain.PROMPT,
            key="test_prompt",
            current_value="A",
            candidate_value="B",
        )
        assert exp.id is not None
        assert exp.name == "Test"
        assert exp.target.current_value == "A"
        # Should be registered in tracker
        assert tracker.get(exp.id) is not None

    def test_run_improved(self, tracker):
        engine = ExperimentEngine(
            tracker=tracker,
            config=EngineConfig(
                metrics=["response_quality"],
                min_samples=3,
                max_samples=5,
            ),
        )
        exp = engine.create_experiment(
            name="Quality Test",
            domain="prompt",
            key="test",
            current_value="old",
            candidate_value="new",
            min_improvement_pct=5.0,
        )

        # Evaluator: candidate consistently scores higher
        def evaluator(config, sample_id):
            if "control" in sample_id:
                return {"response_quality": 70.0}
            return {"response_quality": 90.0}

        result = engine.run(exp, evaluator=evaluator)
        assert result.status == ExperimentStatus.IMPROVED
        assert result.improvement_pct > 0

    def test_run_regressed(self, tracker):
        engine = ExperimentEngine(
            tracker=tracker,
            config=EngineConfig(
                metrics=["response_quality"],
                min_samples=3,
                max_samples=5,
            ),
        )
        exp = engine.create_experiment(
            name="Regression Test",
            domain="prompt",
            key="test",
            min_improvement_pct=5.0,
        )

        # Candidate scores much lower
        def evaluator(config, sample_id):
            if "control" in sample_id:
                return {"response_quality": 90.0}
            return {"response_quality": 50.0}

        result = engine.run(exp, evaluator=evaluator)
        assert result.status == ExperimentStatus.REGRESSED

    def test_run_neutral(self, tracker):
        engine = ExperimentEngine(
            tracker=tracker,
            config=EngineConfig(
                metrics=["response_quality"],
                min_samples=3,
                max_samples=5,
                stop_early=False,
            ),
        )
        exp = engine.create_experiment(
            name="Neutral Test",
            domain="prompt",
            key="test",
            min_improvement_pct=5.0,
        )

        # Same scores
        def evaluator(config, sample_id):
            return {"response_quality": 80.0}

        result = engine.run(exp, evaluator=evaluator)
        assert result.status == ExperimentStatus.NEUTRAL

    def test_cancel_experiment(self, tracker):
        engine = ExperimentEngine(tracker=tracker)
        exp = engine.create_experiment(
            name="Cancel Test",
            domain="prompt",
            key="test",
        )
        result = engine.cancel(exp)
        assert result.status == ExperimentStatus.CANCELLED

    def test_result_has_details(self, tracker):
        engine = ExperimentEngine(
            tracker=tracker,
            config=EngineConfig(
                metrics=["response_quality", "latency_ms"],
                min_samples=2,
                max_samples=3,
                stop_early=False,
            ),
        )
        exp = engine.create_experiment(
            name="Details Test",
            domain="prompt",
            key="test",
        )

        def evaluator(config, sample_id):
            return {"response_quality": 80.0, "latency_ms": 200.0}

        result = engine.run(exp, evaluator=evaluator)
        assert "comparisons" in result.details
        assert "composite_score" in result.details
        assert "samples_run" in result.details

    def test_evaluator_error_handled(self, tracker):
        engine = ExperimentEngine(
            tracker=tracker,
            config=EngineConfig(
                metrics=["response_quality"],
                min_samples=2,
                max_samples=3,
                stop_early=False,
            ),
        )
        exp = engine.create_experiment(
            name="Error Test",
            domain="prompt",
            key="test",
        )

        call_count = 0

        def evaluator(config, sample_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Eval failed")
            return {"response_quality": 80.0}

        result = engine.run(exp, evaluator=evaluator)
        # Should complete despite one failure
        assert result.status in (
            ExperimentStatus.IMPROVED,
            ExperimentStatus.REGRESSED,
            ExperimentStatus.NEUTRAL,
        )


# ===========================================================================
# Token Optimization: estimate_tokens
# ===========================================================================


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_string(self):
        result = estimate_tokens("Hello world")
        assert result >= 1
        assert result <= 10

    def test_long_string(self):
        text = "a" * 3500  # ~1000 tokens
        result = estimate_tokens(text)
        assert 900 <= result <= 1100

    def test_proportional_to_length(self):
        short = estimate_tokens("abc")
        long = estimate_tokens("abc" * 100)
        assert long > short


# ===========================================================================
# Token Optimization: truncate_to_budget
# ===========================================================================


class TestTruncateToBudget:
    def test_under_budget_unchanged(self):
        layers = ["## Identity\nShort content", "## Active Agent\nAgent stuff"]
        result = truncate_to_budget(layers, token_budget=10000)
        assert result == layers

    def test_over_budget_trims_low_priority(self):
        layers = [
            "## Identity\nCritical identity content",
            "## Active Agent\nAgent definition",
            "## Cross-System Awareness\n" + "x " * 500,  # Low priority, long
            "## Recent Learning\n" + "y " * 500,  # Low priority, long
        ]
        result = truncate_to_budget(layers, token_budget=100)
        # Should trim low-priority layers but keep identity and agent
        total_text = "\n".join(result)
        assert "Identity" in total_text
        assert "Agent" in total_text

    def test_preserves_critical_layers(self):
        layers = [
            "## Identity\n" + "important " * 100,
            "## Active Agent\n" + "critical " * 100,
            "## Writing Style\n" + "format " * 100,
        ]
        result = truncate_to_budget(layers, token_budget=50)
        # Critical layers (priority >= 8) should never be cut
        total = "\n".join(result)
        assert "Identity" in total
        assert "Active Agent" in total
        assert "Writing Style" in total

    def test_empty_layers(self):
        assert truncate_to_budget([], token_budget=100) == []


# ===========================================================================
# Token Optimization: deduplicate_layers
# ===========================================================================


class TestDeduplicateLayers:
    def test_no_duplicates_unchanged(self):
        layers = [
            "## Identity\nI am a test user.",
            "## Agent\nI do agent things.",
        ]
        result = deduplicate_layers(layers)
        assert len(result) == 2

    def test_duplicate_content_removed(self):
        shared = "This is a shared line of content that appears in both layers.\n" * 5
        layers = [
            f"## Loaded Context\n{shared}",
            f"## Relevant Knowledge\n{shared}",
        ]
        result = deduplicate_layers(layers, similarity_threshold=0.7)
        assert len(result) == 1

    def test_single_layer_unchanged(self):
        layers = ["## Only layer"]
        assert deduplicate_layers(layers) == layers

    def test_empty_unchanged(self):
        assert deduplicate_layers([]) == []


# ===========================================================================
# Token Optimization: layer priorities
# ===========================================================================


class TestLayerPriorities:
    def test_identity_is_highest(self):
        assert _get_layer_priority("## Identity\nSome content") == 9

    def test_agent_is_critical(self):
        assert _get_layer_priority("## Active Agent: writer\nDefinition") == 8

    def test_cross_system_is_lowest(self):
        assert _get_layer_priority("## Cross-System Awareness\nContext") == 2

    def test_unknown_gets_default(self):
        assert _get_layer_priority("## Random Heading\nStuff") == 5


# ===========================================================================
# Token Optimization: integrated with build_system_prompt
# ===========================================================================


class TestTokenBudgetIntegration:
    @pytest.fixture(autouse=True)
    def reset(self):
        clear_cache()
        yield
        clear_cache()

    def test_build_with_budget_produces_output(self, kb_root, system_config, shared_config):
        prompt = build_system_prompt(
            kb_path=kb_root,
            system_config=system_config,
            system_key="test",
            agent_key="orchestrator",
            shared_config=shared_config,
            token_budget=500,
        )
        # Should still produce a prompt even with tight budget
        assert len(prompt) > 0
        tokens = estimate_tokens(prompt)
        # Might not perfectly hit budget but should be reasonable
        assert tokens > 0

    def test_build_without_budget_is_full(self, kb_root, system_config, shared_config):
        prompt_full = build_system_prompt(
            kb_path=kb_root,
            system_config=system_config,
            system_key="test",
            agent_key="orchestrator",
            shared_config=shared_config,
        )
        prompt_budget = build_system_prompt(
            kb_path=kb_root,
            system_config=system_config,
            system_key="test",
            agent_key="orchestrator",
            shared_config=shared_config,
            token_budget=50,
        )
        # Budget prompt should be shorter
        assert len(prompt_budget) <= len(prompt_full)
