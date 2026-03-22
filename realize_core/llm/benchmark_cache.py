"""
Benchmark Cache: Weekly benchmark fetcher + cost-benefit model scorer.

Fetches model benchmarks from public sources on a configurable interval,
caches them locally, and provides a cost-benefit scoring function that
the router can use to pick the optimal model for each task type.

Key features:
- Multi-dimensional scoring: quality (benchmark), cost, speed, freshness
- Configurable weights per routing strategy
- Persistent JSON cache file with TTL-based refresh
- Graceful fallback to static defaults when offline
- Feature-gated: only active when enabled in config
"""
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default cache TTL: 7 days (seconds)
DEFAULT_CACHE_TTL = 7 * 24 * 60 * 60

# Where we persist the cache
DEFAULT_CACHE_DIR = Path("data")
DEFAULT_CACHE_FILE = "benchmark_cache.json"


@dataclass
class ModelBenchmark:
    """Benchmark data for a single model.

    Attributes:
        model_id: Provider-specific model identifier (e.g., "gpt-4o")
        provider: Provider name (e.g., "openai", "anthropic", "litellm")
        display_name: Human-readable name
        quality_score: Overall quality score (0-100, higher is better)
        coding_score: Code generation benchmark score (0-100)
        reasoning_score: Reasoning benchmark score (0-100)
        speed_score: Speed/latency score (0-100, higher = faster)
        input_cost_per_m: Cost per 1M input tokens (USD)
        output_cost_per_m: Cost per 1M output tokens (USD)
        context_window: Maximum context window size
        last_updated: Unix timestamp of when this data was last refreshed
        source: Where the benchmark data came from
    """
    model_id: str
    provider: str
    display_name: str = ""
    quality_score: float = 50.0
    coding_score: float = 50.0
    reasoning_score: float = 50.0
    speed_score: float = 50.0
    input_cost_per_m: float = 0.0
    output_cost_per_m: float = 0.0
    context_window: int = 128000
    last_updated: float = 0.0
    source: str = "static"


@dataclass
class CostBenefitScore:
    """Result of scoring a model for a specific task.

    The composite_score is what the router uses to rank models.
    Higher is better.
    """
    model_id: str
    provider: str
    composite_score: float
    quality_component: float
    cost_component: float
    speed_component: float
    task_fit_component: float
    details: dict[str, Any] = field(default_factory=dict)


# Static benchmark defaults — used when cache is cold or offline.
# Based on public benchmark data (MMLU, HumanEval, GSM8K, etc.).
_STATIC_BENCHMARKS: list[dict[str, Any]] = [
    {
        "model_id": "claude-sonnet-4-6-20260217", "provider": "claude",
        "display_name": "Claude 4 Sonnet",
        "quality_score": 88, "coding_score": 90, "reasoning_score": 87, "speed_score": 75,
        "input_cost_per_m": 3.0, "output_cost_per_m": 15.0, "context_window": 200000,
    },
    {
        "model_id": "claude-opus-4-6-20260205", "provider": "claude",
        "display_name": "Claude 4 Opus",
        "quality_score": 93, "coding_score": 94, "reasoning_score": 95, "speed_score": 50,
        "input_cost_per_m": 15.0, "output_cost_per_m": 75.0, "context_window": 200000,
    },
    {
        "model_id": "gemini-2.5-flash", "provider": "gemini",
        "display_name": "Gemini 2.5 Flash",
        "quality_score": 82, "coding_score": 80, "reasoning_score": 78, "speed_score": 95,
        "input_cost_per_m": 0.15, "output_cost_per_m": 0.60, "context_window": 1000000,
    },
    {
        "model_id": "gpt-4o", "provider": "litellm",
        "display_name": "GPT-4o",
        "quality_score": 87, "coding_score": 88, "reasoning_score": 86, "speed_score": 80,
        "input_cost_per_m": 2.50, "output_cost_per_m": 10.0, "context_window": 128000,
    },
    {
        "model_id": "gpt-4o-mini", "provider": "litellm",
        "display_name": "GPT-4o Mini",
        "quality_score": 75, "coding_score": 73, "reasoning_score": 72, "speed_score": 90,
        "input_cost_per_m": 0.15, "output_cost_per_m": 0.60, "context_window": 128000,
    },
    {
        "model_id": "o3-mini", "provider": "litellm",
        "display_name": "o3-mini",
        "quality_score": 86, "coding_score": 92, "reasoning_score": 90, "speed_score": 70,
        "input_cost_per_m": 1.10, "output_cost_per_m": 4.40, "context_window": 200000,
    },
    {
        "model_id": "deepseek/deepseek-chat", "provider": "litellm",
        "display_name": "DeepSeek V3",
        "quality_score": 80, "coding_score": 85, "reasoning_score": 78, "speed_score": 85,
        "input_cost_per_m": 0.27, "output_cost_per_m": 1.10, "context_window": 128000,
    },
    {
        "model_id": "mistral/mistral-large-latest", "provider": "litellm",
        "display_name": "Mistral Large",
        "quality_score": 82, "coding_score": 80, "reasoning_score": 81, "speed_score": 78,
        "input_cost_per_m": 2.0, "output_cost_per_m": 6.0, "context_window": 128000,
    },
]

# Weights for how much each dimension matters per routing strategy
_STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "balanced": {
        "quality": 0.35,
        "cost": 0.30,
        "speed": 0.15,
        "task_fit": 0.20,
    },
    "cost_optimized": {
        "quality": 0.15,
        "cost": 0.55,
        "speed": 0.10,
        "task_fit": 0.20,
    },
    "quality_first": {
        "quality": 0.55,
        "cost": 0.10,
        "speed": 0.10,
        "task_fit": 0.25,
    },
    "speed_first": {
        "quality": 0.15,
        "cost": 0.15,
        "speed": 0.50,
        "task_fit": 0.20,
    },
}

# Which benchmark dimension matters most for each task type
_TASK_SCORE_MAP: dict[str, str] = {
    "simple": "quality_score",
    "content": "quality_score",
    "reasoning": "reasoning_score",
    "financial": "reasoning_score",
    "complex": "reasoning_score",
    "code": "coding_score",
    "google": "quality_score",    # tool use needs good general quality
    "web_research": "quality_score",
    "web_action": "quality_score",
}


class BenchmarkCache:
    """Cache of model benchmarks with periodic refresh and cost-benefit scoring.

    Usage:
        cache = BenchmarkCache()
        cache.load()  # Load from disk or static defaults

        # Score models for a task
        scores = cache.score_models("reasoning", strategy="balanced")
        best = scores[0]  # highest composite score
    """

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        cache_file: str = DEFAULT_CACHE_FILE,
        ttl_seconds: int = DEFAULT_CACHE_TTL,
    ):
        self._cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self._cache_file = cache_file
        self._ttl = ttl_seconds
        self._benchmarks: dict[str, ModelBenchmark] = {}
        self._last_fetch: float = 0.0
        self._loaded = False

    @property
    def cache_path(self) -> Path:
        return self._cache_dir / self._cache_file

    @property
    def benchmarks(self) -> dict[str, ModelBenchmark]:
        """All cached benchmarks, keyed by model_id."""
        return dict(self._benchmarks)

    @property
    def is_stale(self) -> bool:
        """True if the cache is older than the TTL."""
        if not self._last_fetch:
            return True
        return (time.time() - self._last_fetch) > self._ttl

    def load(self) -> None:
        """Load benchmarks from disk cache, falling back to static defaults."""
        if self._try_load_from_disk():
            self._loaded = True
            logger.info(f"Loaded {len(self._benchmarks)} benchmarks from cache")
            return

        # Fall back to static defaults
        self._load_static_defaults()
        self._loaded = True
        logger.info(f"Loaded {len(self._benchmarks)} benchmarks from static defaults")

    def _try_load_from_disk(self) -> bool:
        """Try to load from the JSON cache file."""
        try:
            if not self.cache_path.exists():
                return False

            with open(self.cache_path, encoding="utf-8") as f:
                data = json.load(f)

            self._last_fetch = data.get("last_fetch", 0.0)
            for entry in data.get("benchmarks", []):
                bm = ModelBenchmark(**entry)
                self._benchmarks[bm.model_id] = bm

            return len(self._benchmarks) > 0

        except Exception as e:
            logger.warning(f"Failed to load benchmark cache: {e}")
            return False

    def _load_static_defaults(self) -> None:
        """Load the hardcoded default benchmarks."""
        self._benchmarks.clear()
        now = time.time()
        for entry in _STATIC_BENCHMARKS:
            bm = ModelBenchmark(
                **entry,
                last_updated=now,
                source="static",
            )
            self._benchmarks[bm.model_id] = bm
        self._last_fetch = now

    def save(self) -> None:
        """Persist the current cache to disk."""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "last_fetch": self._last_fetch,
                "benchmarks": [asdict(bm) for bm in self._benchmarks.values()],
            }
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self._benchmarks)} benchmarks to {self.cache_path}")
        except Exception as e:
            logger.warning(f"Failed to save benchmark cache: {e}")

    def update_benchmark(self, benchmark: ModelBenchmark) -> None:
        """Add or update a single benchmark entry."""
        benchmark.last_updated = time.time()
        self._benchmarks[benchmark.model_id] = benchmark

    def update_from_dict(self, entries: list[dict[str, Any]]) -> int:
        """Batch update benchmarks from a list of dicts.

        Args:
            entries: List of dicts matching ModelBenchmark fields.

        Returns:
            Number of benchmarks updated.
        """
        count = 0
        now = time.time()
        for entry in entries:
            try:
                entry.setdefault("last_updated", now)
                entry.setdefault("source", "api")
                bm = ModelBenchmark(**entry)
                self._benchmarks[bm.model_id] = bm
                count += 1
            except Exception as e:
                logger.debug(f"Skipping invalid benchmark entry: {e}")
        self._last_fetch = now
        return count

    async def refresh(self) -> bool:
        """Attempt to refresh benchmarks from external sources.

        Currently a stub — in production this would fetch from:
        - Artificial Analysis API
        - LMSys Chatbot Arena
        - LiteLLM's model pricing endpoint

        Returns:
            True if refresh succeeded, False otherwise.
        """
        if not self.is_stale:
            logger.debug("Benchmark cache is fresh, skipping refresh")
            return True

        # Phase 1: Try LiteLLM's pricing data
        updated = await self._fetch_litellm_pricing()
        if updated:
            self._last_fetch = time.time()
            self.save()
            return True

        # If external fetch fails, static data is still valid
        logger.info("External benchmark fetch failed, using cached/static data")
        return False

    async def _fetch_litellm_pricing(self) -> bool:
        """Fetch latest pricing from LiteLLM's model cost map.

        Returns True if any benchmarks were updated.
        """
        try:
            import litellm

            cost_map = getattr(litellm, "model_cost", {})
            if not cost_map:
                return False

            count = 0
            for model_id, cost_data in cost_map.items():
                if model_id in self._benchmarks:
                    bm = self._benchmarks[model_id]
                    # Update pricing from LiteLLM's data
                    input_cost = cost_data.get("input_cost_per_token", 0) * 1_000_000
                    output_cost = cost_data.get("output_cost_per_token", 0) * 1_000_000
                    if input_cost > 0 or output_cost > 0:
                        bm.input_cost_per_m = input_cost
                        bm.output_cost_per_m = output_cost
                        bm.last_updated = time.time()
                        bm.source = "litellm_pricing"
                        count += 1

            logger.info(f"Updated pricing for {count} models from LiteLLM")
            return count > 0

        except ImportError:
            logger.debug("LiteLLM not installed, skipping pricing fetch")
            return False
        except Exception as e:
            logger.debug(f"LiteLLM pricing fetch failed: {e}")
            return False

    def score_models(
        self,
        task_type: str,
        strategy: str = "balanced",
        available_models: set[str] | None = None,
    ) -> list[CostBenefitScore]:
        """Score all cached models for a given task type and strategy.

        Args:
            task_type: The classified task type (e.g., "reasoning", "content")
            strategy: Routing strategy ("balanced", "cost_optimized", "quality_first", "speed_first")
            available_models: Optional set of model_ids to consider (None = all)

        Returns:
            List of CostBenefitScore sorted by composite_score descending (best first).
        """
        if not self._loaded:
            self.load()

        weights = _STRATEGY_WEIGHTS.get(strategy, _STRATEGY_WEIGHTS["balanced"])
        task_score_key = _TASK_SCORE_MAP.get(task_type, "quality_score")

        # Find the max cost for normalization
        all_costs = [
            bm.input_cost_per_m + bm.output_cost_per_m
            for bm in self._benchmarks.values()
        ]
        max_cost = max(all_costs) if all_costs else 1.0

        scores: list[CostBenefitScore] = []

        for model_id, bm in self._benchmarks.items():
            if available_models and model_id not in available_models:
                continue

            # Quality component (0-100 → 0-1)
            quality = bm.quality_score / 100.0

            # Cost component (inverted — lower cost = higher score, 0-1)
            total_cost = bm.input_cost_per_m + bm.output_cost_per_m
            cost = 1.0 - (total_cost / max_cost) if max_cost > 0 else 1.0

            # Speed component (0-100 → 0-1)
            speed = bm.speed_score / 100.0

            # Task-fit component: how well does this model fit the task?
            task_fit = getattr(bm, task_score_key, bm.quality_score) / 100.0

            # Weighted composite
            composite = (
                weights["quality"] * quality
                + weights["cost"] * cost
                + weights["speed"] * speed
                + weights["task_fit"] * task_fit
            )

            scores.append(CostBenefitScore(
                model_id=model_id,
                provider=bm.provider,
                composite_score=round(composite, 4),
                quality_component=round(quality, 4),
                cost_component=round(cost, 4),
                speed_component=round(speed, 4),
                task_fit_component=round(task_fit, 4),
                details={
                    "display_name": bm.display_name,
                    "total_cost_per_m": round(total_cost, 2),
                    "strategy": strategy,
                    "task_type": task_type,
                },
            ))

        # Sort by composite score descending
        scores.sort(key=lambda s: s.composite_score, reverse=True)
        return scores

    def get_best_model(
        self,
        task_type: str,
        strategy: str = "balanced",
        available_models: set[str] | None = None,
    ) -> str | None:
        """Get the model_id of the best model for a task type.

        Convenience wrapper around score_models().

        Args:
            task_type: The classified task type
            strategy: Routing strategy
            available_models: Optional allowlist of model_ids

        Returns:
            The best model_id, or None if no models are available.
        """
        scores = self.score_models(task_type, strategy, available_models)
        if scores:
            return scores[0].model_id
        return None


# --- Module-level singleton ---

_cache: BenchmarkCache | None = None


def get_benchmark_cache() -> BenchmarkCache:
    """Get or create the global benchmark cache singleton."""
    global _cache
    if _cache is None:
        _cache = BenchmarkCache()
        _cache.load()
    return _cache


def reset_benchmark_cache() -> None:
    """Reset the cache (for testing)."""
    global _cache
    _cache = None
