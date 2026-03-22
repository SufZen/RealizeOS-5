"""Tests for realize_core.llm.benchmark_cache — benchmark-based model scoring.

Covers:
- Loading from static defaults
- Persistence (save/load JSON)
- Benchmark update operations
- Cost-benefit scoring with different strategies
- get_best_model() convenience method
- Staleness detection
- Module-level singleton lifecycle
"""
import json
import time

import pytest
from realize_core.llm.benchmark_cache import (
    _STATIC_BENCHMARKS,
    _STRATEGY_WEIGHTS,
    _TASK_SCORE_MAP,
    BenchmarkCache,
    CostBenefitScore,
    ModelBenchmark,
    get_benchmark_cache,
    reset_benchmark_cache,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cache(tmp_path):
    """Create a BenchmarkCache using a temp directory."""
    return BenchmarkCache(cache_dir=tmp_path, ttl_seconds=3600)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level singleton between tests."""
    reset_benchmark_cache()
    yield
    reset_benchmark_cache()


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class TestLoading:
    """Test loading benchmarks from different sources."""

    def test_load_static_defaults(self, cache):
        """Loading without a cache file uses static defaults."""
        cache.load()
        assert len(cache.benchmarks) == len(_STATIC_BENCHMARKS)

    def test_static_defaults_nonempty(self):
        """Static benchmarks list is not empty."""
        assert len(_STATIC_BENCHMARKS) > 0

    def test_loaded_models_have_valid_scores(self, cache):
        """All loaded models have scores in range 0-100."""
        cache.load()
        for model_id, bm in cache.benchmarks.items():
            assert 0 <= bm.quality_score <= 100, f"{model_id} quality_score out of range"
            assert 0 <= bm.coding_score <= 100, f"{model_id} coding_score out of range"
            assert 0 <= bm.reasoning_score <= 100, f"{model_id} reasoning_score out of range"
            assert 0 <= bm.speed_score <= 100, f"{model_id} speed_score out of range"

    def test_loaded_models_have_provider(self, cache):
        """All loaded models have a provider set."""
        cache.load()
        for model_id, bm in cache.benchmarks.items():
            assert bm.provider, f"{model_id} has no provider"

    def test_load_from_disk(self, cache, tmp_path):
        """Loading from a saved JSON cache file works."""
        # Write a cache file
        cache.load()
        cache.save()

        # Create a new cache that should load from disk
        cache2 = BenchmarkCache(cache_dir=tmp_path)
        cache2.load()
        assert len(cache2.benchmarks) == len(cache.benchmarks)

    def test_load_with_corrupted_file(self, tmp_path):
        """Corrupted cache file falls back to static defaults."""
        # Write garbage to cache file
        cache_path = tmp_path / "benchmark_cache.json"
        cache_path.write_text("{invalid json---")

        cache = BenchmarkCache(cache_dir=tmp_path)
        cache.load()
        # Should fall back to static defaults
        assert len(cache.benchmarks) == len(_STATIC_BENCHMARKS)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    """Test save/load cycle."""

    def test_save_creates_file(self, cache, tmp_path):
        """Saving creates a JSON file on disk."""
        cache.load()
        cache.save()
        assert cache.cache_path.exists()

    def test_save_valid_json(self, cache, tmp_path):
        """Saved cache file is valid JSON."""
        cache.load()
        cache.save()
        with open(cache.cache_path) as f:
            data = json.load(f)
        assert "benchmarks" in data
        assert "last_fetch" in data
        assert len(data["benchmarks"]) == len(cache.benchmarks)

    def test_roundtrip_preserves_data(self, cache, tmp_path):
        """Save then load preserves all benchmark data."""
        cache.load()
        original_ids = set(cache.benchmarks.keys())
        cache.save()

        cache2 = BenchmarkCache(cache_dir=tmp_path)
        cache2.load()
        loaded_ids = set(cache2.benchmarks.keys())

        assert original_ids == loaded_ids


# ---------------------------------------------------------------------------
# Updates
# ---------------------------------------------------------------------------

class TestUpdates:
    """Test benchmark update operations."""

    def test_update_benchmark(self, cache):
        """Can add a new benchmark entry."""
        cache.load()
        new_bm = ModelBenchmark(
            model_id="test-model-v1",
            provider="test_provider",
            display_name="Test Model",
            quality_score=75.0,
        )
        cache.update_benchmark(new_bm)
        assert "test-model-v1" in cache.benchmarks

    def test_update_benchmark_sets_timestamp(self, cache):
        """update_benchmark sets last_updated to now."""
        cache.load()
        before = time.time()
        new_bm = ModelBenchmark(model_id="ts-test", provider="test")
        cache.update_benchmark(new_bm)
        after = time.time()
        assert before <= cache.benchmarks["ts-test"].last_updated <= after

    def test_update_from_dict(self, cache):
        """Batch update from list of dicts works."""
        cache.load()
        original_count = len(cache.benchmarks)
        entries = [
            {"model_id": "new-model-a", "provider": "test", "quality_score": 80},
            {"model_id": "new-model-b", "provider": "test", "quality_score": 70},
        ]
        updated = cache.update_from_dict(entries)
        assert updated == 2
        assert len(cache.benchmarks) == original_count + 2

    def test_update_from_dict_skips_invalid(self, cache):
        """Invalid entries are skipped without error."""
        cache.load()
        entries = [
            {"model_id": "valid", "provider": "test"},
            {"not_a_valid_field": True},  # Missing required fields
        ]
        updated = cache.update_from_dict(entries)
        assert updated == 1


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------

class TestStaleness:
    """Test cache staleness detection."""

    def test_fresh_cache_is_not_stale(self, cache):
        """Freshly loaded cache is not stale."""
        cache.load()
        assert cache.is_stale is False

    def test_old_cache_is_stale(self, tmp_path):
        """Cache older than TTL is stale."""
        cache = BenchmarkCache(cache_dir=tmp_path, ttl_seconds=1)
        cache.load()
        cache._last_fetch = time.time() - 100  # 100 seconds ago
        assert cache.is_stale is True

    def test_unloaded_cache_is_stale(self, cache):
        """Unloaded cache (no fetch time) is stale."""
        assert cache.is_stale is True


# ---------------------------------------------------------------------------
# Cost-benefit scoring
# ---------------------------------------------------------------------------

class TestScoring:
    """Test the cost-benefit scoring algorithm."""

    def test_score_models_returns_sorted_scores(self, cache):
        """Scores are returned sorted by composite_score descending."""
        cache.load()
        scores = cache.score_models("reasoning")
        assert len(scores) > 0
        for i in range(len(scores) - 1):
            assert scores[i].composite_score >= scores[i + 1].composite_score

    def test_score_models_returns_cost_benefit_scores(self, cache):
        """Each score is a CostBenefitScore with valid components."""
        cache.load()
        scores = cache.score_models("content")
        for s in scores:
            assert isinstance(s, CostBenefitScore)
            assert 0 <= s.quality_component <= 1.0
            assert 0 <= s.cost_component <= 1.0
            assert 0 <= s.speed_component <= 1.0
            assert 0 <= s.task_fit_component <= 1.0
            assert 0 <= s.composite_score <= 1.0

    def test_cost_optimized_prefers_cheap(self, cache):
        """Cost-optimized strategy should rank cheap models higher."""
        cache.load()
        scores = cache.score_models("simple", strategy="cost_optimized")
        if len(scores) >= 2:
            # The top model should have a high cost component
            assert scores[0].cost_component >= 0.5

    def test_quality_first_prefers_quality(self, cache):
        """Quality-first strategy should rank high-quality models higher."""
        cache.load()
        scores = cache.score_models("reasoning", strategy="quality_first")
        if len(scores) >= 2:
            # The top model should have a high quality component
            assert scores[0].quality_component >= 0.7

    def test_speed_first_prefers_fast(self, cache):
        """Speed-first strategy should rank fast models higher."""
        cache.load()
        scores = cache.score_models("simple", strategy="speed_first")
        if len(scores) >= 2:
            assert scores[0].speed_component >= 0.7

    def test_different_strategies_may_rank_differently(self, cache):
        """Different strategies can produce different top models."""
        cache.load()
        cost_top = cache.score_models("reasoning", strategy="cost_optimized")[0]
        quality_top = cache.score_models("reasoning", strategy="quality_first")[0]
        # They CAN be the same, but typically won't be
        # Just verify both are valid
        assert cost_top.model_id
        assert quality_top.model_id

    def test_available_models_filter(self, cache):
        """Only specified models are scored when available_models is set."""
        cache.load()
        # Only score Claude models
        available = {"claude-sonnet-4-6-20260217", "claude-opus-4-6-20260205"}
        scores = cache.score_models("reasoning", available_models=available)
        for s in scores:
            assert s.model_id in available

    def test_all_strategies_exist(self):
        """All strategy weights are defined."""
        expected = {"balanced", "cost_optimized", "quality_first", "speed_first"}
        assert set(_STRATEGY_WEIGHTS.keys()) == expected

    def test_all_task_types_mapped(self):
        """All known task types have a score mapping."""
        expected_tasks = {
            "simple", "content", "reasoning", "financial",
            "complex", "code", "google", "web_research", "web_action",
        }
        assert expected_tasks.issubset(set(_TASK_SCORE_MAP.keys()))

    def test_strategy_weights_sum_to_one(self):
        """Strategy weights should sum to approximately 1.0."""
        for strategy, weights in _STRATEGY_WEIGHTS.items():
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.01, f"{strategy} weights sum to {total}"


# ---------------------------------------------------------------------------
# Convenience: get_best_model
# ---------------------------------------------------------------------------

class TestGetBestModel:
    """Test the get_best_model convenience method."""

    def test_returns_model_id(self, cache):
        cache.load()
        best = cache.get_best_model("reasoning")
        assert best is not None
        assert isinstance(best, str)

    def test_returns_none_for_empty_cache(self, tmp_path):
        """Empty cache returns None."""
        cache = BenchmarkCache(cache_dir=tmp_path)
        cache._loaded = True
        cache._benchmarks = {}
        assert cache.get_best_model("reasoning") is None

    def test_reasoning_prefers_high_reasoning_score(self, cache):
        """Reasoning tasks should prefer models with high reasoning scores."""
        cache.load()
        best = cache.get_best_model("reasoning", strategy="quality_first")
        bm = cache.benchmarks.get(best)
        assert bm is not None
        assert bm.reasoning_score >= 80  # Should pick a strong reasoner


# ---------------------------------------------------------------------------
# Singleton lifecycle
# ---------------------------------------------------------------------------

class TestSingleton:
    """Test the module-level singleton."""

    def test_get_benchmark_cache_returns_loaded(self):
        """Singleton is auto-loaded."""
        cache = get_benchmark_cache()
        assert cache is not None
        assert len(cache.benchmarks) > 0

    def test_get_benchmark_cache_idempotent(self):
        """Calling twice returns the same instance."""
        c1 = get_benchmark_cache()
        c2 = get_benchmark_cache()
        assert c1 is c2

    def test_reset_clears_singleton(self):
        """Resetting clears the singleton."""
        c1 = get_benchmark_cache()
        reset_benchmark_cache()
        c2 = get_benchmark_cache()
        assert c1 is not c2


# ---------------------------------------------------------------------------
# ModelBenchmark dataclass
# ---------------------------------------------------------------------------

class TestModelBenchmark:
    """Test ModelBenchmark dataclass."""

    def test_default_values(self):
        bm = ModelBenchmark(model_id="test", provider="test_provider")
        assert bm.quality_score == 50.0
        assert bm.speed_score == 50.0
        assert bm.source == "static"

    def test_custom_values(self):
        bm = ModelBenchmark(
            model_id="custom",
            provider="custom_provider",
            quality_score=90.0,
            speed_score=85.0,
            source="api",
        )
        assert bm.quality_score == 90.0
        assert bm.speed_score == 85.0
        assert bm.source == "api"


# ---------------------------------------------------------------------------
# Static benchmark data integrity
# ---------------------------------------------------------------------------

class TestStaticBenchmarkIntegrity:
    """Verify the static benchmark data is well-formed."""

    def test_all_entries_have_model_id(self):
        for entry in _STATIC_BENCHMARKS:
            assert "model_id" in entry, f"Entry missing model_id: {entry}"

    def test_all_entries_have_provider(self):
        for entry in _STATIC_BENCHMARKS:
            assert "provider" in entry, f"Entry missing provider: {entry}"

    def test_all_entries_have_quality_score(self):
        for entry in _STATIC_BENCHMARKS:
            assert "quality_score" in entry, f"Entry missing quality_score: {entry}"

    def test_quality_scores_in_valid_range(self):
        for entry in _STATIC_BENCHMARKS:
            qs = entry["quality_score"]
            assert 0 <= qs <= 100, f"{entry['model_id']} quality_score={qs} out of range"

    def test_includes_claude_models(self):
        model_ids = [e["model_id"] for e in _STATIC_BENCHMARKS]
        assert any("claude" in m for m in model_ids)

    def test_includes_gemini_models(self):
        model_ids = [e["model_id"] for e in _STATIC_BENCHMARKS]
        assert any("gemini" in m for m in model_ids)

    def test_includes_gpt_models(self):
        model_ids = [e["model_id"] for e in _STATIC_BENCHMARKS]
        assert any("gpt" in m for m in model_ids)
