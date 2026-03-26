"""
Advanced Routing Engine: Routes tasks to the best provider+model by strategy.

.. deprecated:: V5 Audit
    **This module is currently NOT wired into any production code.**
    The active routing module is ``realize_core.llm.router``, which is
    imported by ``base_handler.py``, ``__init__.py``, ``workflows/``,
    ``pipeline/creative.py``, ``memory/consolidator.py``, and
    ``llm/classifier.py``.

    This module contains a more advanced YAML-driven strategy engine
    that could replace ``router.py`` in a future refactor.  Until then,
    it is kept as reference / experimental code.

Loads provider capabilities from YAML, supports routing strategies
(cost_optimized, quality_first, balanced, speed_first),
fallback chains, and per-request cost tracking.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from realize_core.llm.classifier import TaskClassification

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ModelCapability:
    """Parsed model capability from YAML registry."""

    key: str
    display_name: str
    provider: str
    modalities: list[str]
    tier: int
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    cost_per_image: float = 0.0
    cost_per_second: float = 0.0
    max_tokens: int = 0
    speed: str = "medium"
    quality: str = "standard"

    def supports_modality(self, modality: str) -> bool:
        return modality in self.modalities


@dataclass
class RoutingDecision:
    """Result of the routing engine selecting a model."""

    model_key: str
    provider: str
    display_name: str
    task_type: str
    modality: str
    tier: int
    strategy: str
    fallback_chain: list[str]
    confidence: float


@dataclass
class CostRecord:
    """Tracks cost of a single LLM call."""

    model_key: str
    provider: str
    modality: str
    input_tokens: int = 0
    output_tokens: int = 0
    images_generated: int = 0
    video_seconds: float = 0.0
    cost_usd: float = 0.0
    timestamp: float = field(default_factory=time.time)


# Speed order for comparison
_SPEED_ORDER = {"very_fast": 4, "fast": 3, "medium": 2, "slow": 1}
_QUALITY_ORDER = {"premium": 4, "high": 3, "standard": 2, "low": 1}


# ---------------------------------------------------------------------------
# Routing Engine
# ---------------------------------------------------------------------------


class RoutingEngine:
    """
    Routes tasks to the optimal provider+model.

    Loads provider capabilities from YAML, supports multiple
    routing strategies, and tracks costs.
    """

    def __init__(self, config_path: str | Path | None = None):
        self._config: dict[str, Any] = {}
        self._models: dict[str, ModelCapability] = {}
        self._strategies: dict[str, dict] = {}
        self._defaults: dict[str, str] = {}
        self._fallbacks: dict[str, list[str]] = {}
        self._cost_log: list[CostRecord] = []
        self._loaded = False

        if config_path:
            self.load_config(config_path)
        else:
            self._try_default_config()

    def _try_default_config(self):
        """Try loading the default config from the package directory."""
        default = Path(__file__).parent / "provider_capabilities.yaml"
        if default.exists():
            self.load_config(default)

    def load_config(self, config_path: str | Path):
        """Load the provider capability registry from YAML."""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Capabilities config not found: {path}")
            return

        with open(path, encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}

        # Parse models
        self._models.clear()
        for provider_key, provider_data in self._config.get("providers", {}).items():
            for model_key, model_data in provider_data.get("models", {}).items():
                self._models[model_key] = ModelCapability(
                    key=model_key,
                    display_name=model_data.get("display_name", model_key),
                    provider=provider_key,
                    modalities=model_data.get("modalities", ["text"]),
                    tier=model_data.get("tier", 1),
                    cost_per_1k_input=model_data.get("cost_per_1k_input", 0.0),
                    cost_per_1k_output=model_data.get("cost_per_1k_output", 0.0),
                    cost_per_image=model_data.get("cost_per_image", 0.0),
                    cost_per_second=model_data.get("cost_per_second", 0.0),
                    max_tokens=model_data.get("max_tokens", 0),
                    speed=model_data.get("speed", "medium"),
                    quality=model_data.get("quality", "standard"),
                )

        # Parse strategies, defaults, fallbacks
        self._strategies = self._config.get("strategies", {})
        self._defaults = self._config.get("defaults", {})
        self._fallbacks = self._config.get("fallbacks", {})
        self._loaded = True
        logger.info(f"Loaded {len(self._models)} models from {len(self._config.get('providers', {}))} providers")

    def route(
        self,
        classification: TaskClassification,
        strategy: str = "balanced",
        available_providers: set[str] | None = None,
    ) -> RoutingDecision:
        """
        Route a classified task to the best model.

        Args:
            classification: The task classification result
            strategy: Routing strategy name (balanced, cost_optimized, quality_first, speed_first)
            available_providers: Set of available provider keys (None = all available)

        Returns:
            RoutingDecision with the selected model and metadata
        """
        modality_str = classification.modality.value

        # Step 1: Try the default model for this task type
        default_key = self._defaults.get(classification.task_type)
        if default_key and default_key in self._models:
            model = self._models[default_key]
            if available_providers is None or model.provider in available_providers:
                return self._make_decision(model, classification, strategy)

        # Step 2: Find candidates that support the required modality
        candidates = [
            m
            for m in self._models.values()
            if m.supports_modality(modality_str) and (available_providers is None or m.provider in available_providers)
        ]

        if not candidates:
            # Step 3: Fallback to any text-capable model
            candidates = [
                m
                for m in self._models.values()
                if m.supports_modality("text") and (available_providers is None or m.provider in available_providers)
            ]

        if not candidates:
            # Step 4: Ultimate fallback — return the default
            logger.warning(f"No candidates for {modality_str}, using first available model")
            candidates = list(self._models.values())
            if not candidates:
                return RoutingDecision(
                    model_key="gemini_flash",
                    provider="gemini",
                    display_name="Gemini Flash (fallback)",
                    task_type=classification.task_type,
                    modality=modality_str,
                    tier=1,
                    strategy=strategy,
                    fallback_chain=[],
                    confidence=0.1,
                )

        # Step 5: Sort by strategy
        sorted_candidates = self._sort_by_strategy(candidates, strategy, classification.tier)

        selected = sorted_candidates[0]
        return self._make_decision(selected, classification, strategy)

    def _sort_by_strategy(
        self,
        candidates: list[ModelCapability],
        strategy: str,
        preferred_tier: int,
    ) -> list[ModelCapability]:
        """Sort candidates by the given routing strategy."""
        self._strategies.get(strategy, {})

        if strategy == "cost_optimized":
            return sorted(
                candidates,
                key=lambda m: (
                    m.cost_per_1k_input + m.cost_per_1k_output,
                    abs(m.tier - preferred_tier),
                    -_SPEED_ORDER.get(m.speed, 2),
                ),
            )
        elif strategy == "quality_first":
            return sorted(
                candidates,
                key=lambda m: (
                    -_QUALITY_ORDER.get(m.quality, 2),
                    -m.tier,
                    -_SPEED_ORDER.get(m.speed, 2),
                ),
            )
        elif strategy == "speed_first":
            return sorted(
                candidates,
                key=lambda m: (
                    -_SPEED_ORDER.get(m.speed, 2),
                    m.cost_per_1k_input + m.cost_per_1k_output,
                    -_QUALITY_ORDER.get(m.quality, 2),
                ),
            )
        else:  # balanced (default)
            return sorted(
                candidates,
                key=lambda m: (
                    abs(m.tier - preferred_tier),
                    -_QUALITY_ORDER.get(m.quality, 2),
                    m.cost_per_1k_input + m.cost_per_1k_output,
                    -_SPEED_ORDER.get(m.speed, 2),
                ),
            )

    def _make_decision(
        self,
        model: ModelCapability,
        classification: TaskClassification,
        strategy: str,
    ) -> RoutingDecision:
        """Create a RoutingDecision from a selected model."""
        fallbacks = self._fallbacks.get(model.key, [])
        return RoutingDecision(
            model_key=model.key,
            provider=model.provider,
            display_name=model.display_name,
            task_type=classification.task_type,
            modality=classification.modality.value,
            tier=model.tier,
            strategy=strategy,
            fallback_chain=fallbacks,
            confidence=classification.confidence,
        )

    def get_fallback_chain(self, model_key: str) -> list[str]:
        """Get the fallback chain for a model."""
        return self._fallbacks.get(model_key, [])

    # -----------------------------------------------------------------------
    # Cost Tracking
    # -----------------------------------------------------------------------

    def record_cost(
        self,
        model_key: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        images: int = 0,
        video_seconds: float = 0.0,
    ) -> CostRecord:
        """
        Record the cost of an LLM call.

        Args:
            model_key: The model that was used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            images: Number of images generated
            video_seconds: Seconds of video generated

        Returns:
            CostRecord with the calculated cost
        """
        model = self._models.get(model_key)
        if not model:
            logger.warning(f"Unknown model '{model_key}' for cost tracking")
            record = CostRecord(
                model_key=model_key,
                provider="unknown",
                modality="text",
                cost_usd=0.0,
            )
            self._cost_log.append(record)
            return record

        cost = 0.0
        cost += (input_tokens / 1000) * model.cost_per_1k_input
        cost += (output_tokens / 1000) * model.cost_per_1k_output
        cost += images * model.cost_per_image
        cost += video_seconds * model.cost_per_second

        record = CostRecord(
            model_key=model_key,
            provider=model.provider,
            modality=model.modalities[0] if model.modalities else "text",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            images_generated=images,
            video_seconds=video_seconds,
            cost_usd=cost,
        )
        self._cost_log.append(record)
        return record

    def get_cost_summary(self, last_n: int | None = None) -> dict:
        """
        Get a summary of costs.

        Args:
            last_n: If provided, only summarize the last N records

        Returns:
            Dict with total_cost, by_provider, by_modality, record_count
        """
        records = self._cost_log[-last_n:] if last_n else self._cost_log

        by_provider: dict[str, float] = {}
        by_modality: dict[str, float] = {}
        total = 0.0

        for r in records:
            total += r.cost_usd
            by_provider[r.provider] = by_provider.get(r.provider, 0) + r.cost_usd
            by_modality[r.modality] = by_modality.get(r.modality, 0) + r.cost_usd

        return {
            "total_cost_usd": round(total, 6),
            "by_provider": {k: round(v, 6) for k, v in sorted(by_provider.items())},
            "by_modality": {k: round(v, 6) for k, v in sorted(by_modality.items())},
            "record_count": len(records),
        }

    @property
    def models(self) -> dict[str, ModelCapability]:
        return dict(self._models)

    @property
    def loaded(self) -> bool:
        return self._loaded


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_engine: RoutingEngine | None = None


def get_routing_engine() -> RoutingEngine:
    """Get the global routing engine singleton."""
    global _engine
    if _engine is None:
        _engine = RoutingEngine()
    return _engine
