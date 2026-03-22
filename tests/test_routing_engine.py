"""Tests for realize_core.llm.routing_engine — advanced routing."""
import pytest
from pathlib import Path

from realize_core.llm.classifier import Modality, TaskClassification
from realize_core.llm.routing_engine import (
    ModelCapability,
    RoutingDecision,
    CostRecord,
    RoutingEngine,
    get_routing_engine,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def yaml_path():
    """Path to the real provider_capabilities.yaml."""
    return Path(__file__).parent.parent / "realize_core" / "llm" / "provider_capabilities.yaml"


@pytest.fixture
def engine(yaml_path):
    """An engine loaded from the real YAML config."""
    e = RoutingEngine(config_path=yaml_path)
    assert e.loaded
    return e


@pytest.fixture
def simple_task():
    return TaskClassification(
        task_type="simple", modality=Modality.TEXT,
        tier=1, confidence=0.8, requires_tools=False,
    )


@pytest.fixture
def content_task():
    return TaskClassification(
        task_type="content", modality=Modality.TEXT,
        tier=2, confidence=0.9, requires_tools=False,
    )


@pytest.fixture
def image_task():
    return TaskClassification(
        task_type="image_gen", modality=Modality.IMAGE_GEN,
        tier=2, confidence=0.85, requires_tools=True,
    )


@pytest.fixture
def complex_task():
    return TaskClassification(
        task_type="complex", modality=Modality.REASONING,
        tier=3, confidence=0.95, requires_tools=False,
    )


# ---------------------------------------------------------------------------
# ModelCapability tests
# ---------------------------------------------------------------------------


class TestModelCapability:
    def test_supports_modality(self):
        m = ModelCapability(
            key="test", display_name="Test", provider="test",
            modalities=["text", "code", "vision"], tier=2,
        )
        assert m.supports_modality("text")
        assert m.supports_modality("code")
        assert not m.supports_modality("image_gen")


# ---------------------------------------------------------------------------
# RoutingEngine tests
# ---------------------------------------------------------------------------


class TestRoutingEngine:
    def test_loads_config(self, engine):
        assert len(engine.models) > 0
        assert "gemini_flash" in engine.models
        assert "claude_sonnet" in engine.models

    def test_route_simple_task(self, engine, simple_task):
        decision = engine.route(simple_task)
        assert isinstance(decision, RoutingDecision)
        assert decision.model_key == "gemini_flash"
        assert decision.tier == 1

    def test_route_content_task(self, engine, content_task):
        decision = engine.route(content_task)
        assert decision.model_key == "claude_sonnet"

    def test_route_image_task(self, engine, image_task):
        decision = engine.route(image_task)
        assert decision.model_key == "imagen"

    def test_route_complex_task(self, engine, complex_task):
        decision = engine.route(complex_task)
        assert decision.model_key == "claude_opus"
        assert decision.tier == 3

    def test_route_with_strategy_cost(self, engine, content_task):
        decision = engine.route(content_task, strategy="cost_optimized")
        assert isinstance(decision, RoutingDecision)
        # Cost-optimized should not select the most expensive option
        model = engine.models[decision.model_key]
        assert model.cost_per_1k_input <= 0.015  # Not opus-tier

    def test_route_with_limited_providers(self, engine, simple_task):
        decision = engine.route(simple_task, available_providers={"claude"})
        assert decision.provider == "claude"

    def test_fallback_chain_exists(self, engine):
        chain = engine.get_fallback_chain("claude_sonnet")
        assert isinstance(chain, list)
        assert len(chain) > 0

    def test_fallback_chain_empty(self, engine):
        chain = engine.get_fallback_chain("veo")
        assert chain == []

    def test_route_no_config(self):
        """Engine without config returns safe fallback."""
        e = RoutingEngine(config_path="/nonexistent.yaml")
        assert not e.loaded
        task = TaskClassification(
            task_type="simple", modality=Modality.TEXT,
            tier=1, confidence=0.5, requires_tools=False,
        )
        decision = e.route(task)
        assert isinstance(decision, RoutingDecision)


# ---------------------------------------------------------------------------
# Cost tracking tests
# ---------------------------------------------------------------------------


class TestCostTracking:
    def test_record_cost(self, engine):
        record = engine.record_cost("claude_sonnet", input_tokens=1000, output_tokens=500)
        assert isinstance(record, CostRecord)
        assert record.cost_usd > 0
        assert record.model_key == "claude_sonnet"

    def test_record_cost_free_model(self, engine):
        record = engine.record_cost("gemini_flash", input_tokens=5000, output_tokens=2000)
        assert record.cost_usd == 0.0

    def test_record_cost_image(self, engine):
        record = engine.record_cost("imagen", images=3)
        assert record.cost_usd == pytest.approx(0.06)
        assert record.images_generated == 3

    def test_record_cost_unknown_model(self, engine):
        record = engine.record_cost("unknown_model", input_tokens=1000)
        assert record.cost_usd == 0.0

    def test_cost_summary(self, engine):
        engine.record_cost("claude_sonnet", input_tokens=1000, output_tokens=500)
        engine.record_cost("gemini_flash", input_tokens=2000, output_tokens=1000)
        summary = engine.get_cost_summary()
        assert summary["record_count"] >= 2
        assert "total_cost_usd" in summary
        assert "by_provider" in summary
        assert "by_modality" in summary

    def test_cost_summary_last_n(self, engine):
        engine.record_cost("claude_sonnet", input_tokens=1000)
        engine.record_cost("gemini_flash", input_tokens=2000)
        engine.record_cost("claude_opus", input_tokens=500)
        summary = engine.get_cost_summary(last_n=1)
        assert summary["record_count"] == 1


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_routing_engine_returns_same_instance(self):
        import realize_core.llm.routing_engine as mod
        mod._engine = None
        e1 = get_routing_engine()
        e2 = get_routing_engine()
        assert e1 is e2
        mod._engine = None  # Reset for other tests
