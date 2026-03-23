"""Tests for realize_core.llm.base_provider — provider abstraction layer.

Covers:
- ModelInfo and LLMResponse dataclasses
- Capability enum
- BaseLLMProvider ABC contract enforcement
- Default method behaviors (supports, is_available, tool/vision not implemented)
"""

import pytest
from realize_core.llm.base_provider import (
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
)

# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestModelInfo:
    def test_defaults(self):
        m = ModelInfo(model_id="test-model")
        assert m.model_id == "test-model"
        assert m.display_name == ""
        assert m.tier == 2
        assert Capability.TEXT in m.capabilities
        assert m.input_cost_per_m == 0.0
        assert m.max_tokens == 4096

    def test_custom_values(self):
        m = ModelInfo(
            model_id="claude-opus",
            display_name="Claude Opus",
            tier=3,
            capabilities={Capability.TEXT, Capability.VISION, Capability.TOOLS},
            input_cost_per_m=15.0,
            output_cost_per_m=75.0,
            max_tokens=8192,
            context_window=200000,
        )
        assert m.tier == 3
        assert Capability.TOOLS in m.capabilities
        assert m.context_window == 200000


class TestLLMResponse:
    def test_ok_response(self):
        r = LLMResponse(text="Hello", model="test", provider="test")
        assert r.ok is True
        assert r.error is None

    def test_error_response(self):
        r = LLMResponse(text="Failed", model="test", provider="test", error="rate_limit")
        assert r.ok is False
        assert r.error == "rate_limit"

    def test_cost_tracking(self):
        r = LLMResponse(
            text="Response",
            model="claude-sonnet",
            provider="claude",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0105,
        )
        assert r.input_tokens == 1000
        assert r.output_tokens == 500
        assert r.cost_usd > 0

    def test_raw_passthrough(self):
        raw_obj = {"content": [{"text": "hi"}]}
        r = LLMResponse(text="hi", raw=raw_obj)
        assert r.raw == raw_obj


class TestCapability:
    def test_all_capabilities(self):
        caps = list(Capability)
        assert Capability.TEXT in caps
        assert Capability.VISION in caps
        assert Capability.TOOLS in caps
        assert Capability.STREAMING in caps
        assert Capability.CODE in caps

    def test_enum_values(self):
        assert Capability.TEXT.value == "text"
        assert Capability.VISION.value == "vision"


# ---------------------------------------------------------------------------
# BaseLLMProvider contract
# ---------------------------------------------------------------------------


class ConcreteTestProvider(BaseLLMProvider):
    """Minimal concrete implementation for testing ABC."""

    @property
    def name(self) -> str:
        return "test"

    async def complete(self, system_prompt, messages, model=None, max_tokens=4096, temperature=0.7):
        return LLMResponse(text="test response", model=model or "test-model", provider=self.name)

    def list_models(self):
        return [
            ModelInfo(
                model_id="test-model",
                display_name="Test Model",
                tier=1,
                capabilities={Capability.TEXT},
            ),
            ModelInfo(
                model_id="test-vision",
                display_name="Test Vision",
                tier=2,
                capabilities={Capability.TEXT, Capability.VISION},
            ),
        ]


class TestBaseLLMProvider:
    def test_concrete_instantiation(self):
        provider = ConcreteTestProvider()
        assert provider.name == "test"

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseLLMProvider()

    @pytest.mark.asyncio
    async def test_complete(self):
        provider = ConcreteTestProvider()
        response = await provider.complete("prompt", [{"role": "user", "content": "hi"}])
        assert response.ok
        assert response.text == "test response"

    def test_list_models(self):
        provider = ConcreteTestProvider()
        models = provider.list_models()
        assert len(models) == 2
        assert models[0].model_id == "test-model"

    def test_is_available_default(self):
        provider = ConcreteTestProvider()
        assert provider.is_available() is True

    def test_supports_text(self):
        provider = ConcreteTestProvider()
        assert provider.supports(Capability.TEXT) is True

    def test_supports_vision(self):
        provider = ConcreteTestProvider()
        assert provider.supports(Capability.VISION) is True  # test-vision model

    def test_not_supports_tools(self):
        provider = ConcreteTestProvider()
        assert provider.supports(Capability.TOOLS) is False

    @pytest.mark.asyncio
    async def test_tools_not_implemented(self):
        provider = ConcreteTestProvider()
        with pytest.raises(NotImplementedError):
            await provider.complete_with_tools("prompt", [], [])

    @pytest.mark.asyncio
    async def test_vision_not_implemented(self):
        provider = ConcreteTestProvider()
        with pytest.raises(NotImplementedError):
            await provider.complete_with_vision("prompt", [], b"image")
