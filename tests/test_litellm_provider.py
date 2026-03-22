"""Tests for realize_core.llm.litellm_provider — LiteLLM unified provider.

Covers:
- Provider interface compliance (name, list_models, is_available)
- Text completion with mocked LiteLLM
- Tool-use completion with mocked LiteLLM
- Vision completion with base64 encoding
- Cost calculation fallback
- Error handling (API errors, import errors)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realize_core.llm.base_provider import Capability, LLMResponse

# ---------------------------------------------------------------------------
# We mock litellm at the module level since it may not be installed
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_litellm():
    """Create a mock litellm module."""
    mock = MagicMock()
    mock.suppress_debug_info = False
    mock.acompletion = AsyncMock()
    mock.completion_cost = MagicMock(return_value=0.001)
    return mock


@pytest.fixture
def provider(mock_litellm):
    """Create a LiteLLMProvider with mocked litellm."""
    with patch.dict("sys.modules", {"litellm": mock_litellm}):
        from realize_core.llm.litellm_provider import LiteLLMProvider
        p = LiteLLMProvider(default_model="gpt-4o-mini")
        p._litellm = mock_litellm
        return p


# ---------------------------------------------------------------------------
# Interface compliance
# ---------------------------------------------------------------------------

class TestProviderInterface:
    """Test that LiteLLMProvider implements BaseLLMProvider correctly."""

    def test_name_is_litellm(self, provider):
        assert provider.name == "litellm"

    def test_list_models_returns_models(self, provider):
        models = provider.list_models()
        assert len(models) > 0
        # Check first model has expected fields
        first = models[0]
        assert first.model_id
        assert first.display_name
        assert "(LiteLLM)" in first.display_name
        assert isinstance(first.tier, int)
        assert first.capabilities

    def test_list_models_includes_gpt4o(self, provider):
        models = provider.list_models()
        model_ids = [m.model_id for m in models]
        assert "gpt-4o" in model_ids

    def test_list_models_includes_gpt4o_mini(self, provider):
        models = provider.list_models()
        model_ids = [m.model_id for m in models]
        assert "gpt-4o-mini" in model_ids

    def test_list_models_includes_deepseek(self, provider):
        models = provider.list_models()
        model_ids = [m.model_id for m in models]
        assert "deepseek/deepseek-chat" in model_ids

    def test_list_models_filtered(self, mock_litellm):
        """When enabled_models is set, only those models are listed."""
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            from realize_core.llm.litellm_provider import LiteLLMProvider
            p = LiteLLMProvider(enabled_models=["gpt-4o", "gpt-4o-mini"])
            models = p.list_models()
            assert len(models) == 2
            model_ids = {m.model_id for m in models}
            assert model_ids == {"gpt-4o", "gpt-4o-mini"}

    def test_is_available_true_when_litellm_installed(self, provider, mock_litellm):
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            assert provider.is_available() is True

    def test_is_available_false_when_litellm_missing(self):
        """is_available returns False when litellm is not installed."""
        with patch.dict("sys.modules", {"litellm": None}):
            from realize_core.llm.litellm_provider import LiteLLMProvider
            p = LiteLLMProvider()
            assert p.is_available() is False

    def test_supports_text(self, provider):
        assert provider.supports(Capability.TEXT) is True

    def test_supports_vision(self, provider):
        assert provider.supports(Capability.VISION) is True

    def test_supports_tools(self, provider):
        assert provider.supports(Capability.TOOLS) is True


# ---------------------------------------------------------------------------
# Text completion
# ---------------------------------------------------------------------------

class TestComplete:
    """Test text completion via LiteLLM."""

    @pytest.mark.asyncio
    async def test_complete_success(self, provider, mock_litellm):
        """Successful completion returns proper LLMResponse."""
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from GPT!"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_litellm.acompletion.return_value = mock_response

        result = await provider.complete(
            system_prompt="You are a helpful assistant.",
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert isinstance(result, LLMResponse)
        assert result.text == "Hello from GPT!"
        assert result.ok is True
        assert result.provider == "litellm"
        assert result.model == "gpt-4o-mini"
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    @pytest.mark.asyncio
    async def test_complete_with_explicit_model(self, provider, mock_litellm):
        """Explicit model parameter is passed to LiteLLM."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 25
        mock_litellm.acompletion.return_value = mock_response

        await provider.complete(
            system_prompt="test",
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4o",
        )

        # Verify the model was passed to acompletion
        call_kwargs = mock_litellm.acompletion.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_complete_includes_system_prompt(self, provider, mock_litellm):
        """System prompt is prepended as the first message."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 25
        mock_litellm.acompletion.return_value = mock_response

        await provider.complete(
            system_prompt="Be concise.",
            messages=[{"role": "user", "content": "Hi"}],
        )

        call_kwargs = mock_litellm.acompletion.call_args
        msgs = call_kwargs.kwargs["messages"]
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "Be concise."
        assert msgs[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_complete_error_returns_error_response(self, provider, mock_litellm):
        """API errors return an LLMResponse with error set."""
        mock_litellm.acompletion.side_effect = Exception("API rate limit")

        result = await provider.complete(
            system_prompt="test",
            messages=[{"role": "user", "content": "test"}],
        )

        assert result.ok is False
        assert result.error is not None
        assert "rate limit" in result.error.lower()

    @pytest.mark.asyncio
    async def test_complete_empty_response(self, provider, mock_litellm):
        """Handles empty response content gracefully."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 0
        mock_litellm.acompletion.return_value = mock_response

        result = await provider.complete(
            system_prompt="test",
            messages=[{"role": "user", "content": "test"}],
        )

        assert result.ok is True
        assert result.text == ""


# ---------------------------------------------------------------------------
# Tool-use completion
# ---------------------------------------------------------------------------

class TestCompleteWithTools:
    """Test tool-use completion via LiteLLM."""

    @pytest.mark.asyncio
    async def test_tool_completion_success(self, provider, mock_litellm):
        """Tool completion returns response with raw tool-use data."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I'll search for that."
        mock_response.usage.prompt_tokens = 200
        mock_response.usage.completion_tokens = 100
        mock_litellm.acompletion.return_value = mock_response

        tools = [{
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Search the web",
                "parameters": {"type": "object", "properties": {}},
            },
        }]

        result = await provider.complete_with_tools(
            system_prompt="You can search the web.",
            messages=[{"role": "user", "content": "Search for AI news"}],
            tools=tools,
        )

        assert result.ok is True
        # Verify tools were passed to acompletion
        call_kwargs = mock_litellm.acompletion.call_args
        assert call_kwargs.kwargs["tools"] == tools


# ---------------------------------------------------------------------------
# Vision completion
# ---------------------------------------------------------------------------

class TestCompleteWithVision:
    """Test vision completion via LiteLLM."""

    @pytest.mark.asyncio
    async def test_vision_completion_success(self, provider, mock_litellm):
        """Vision completion encodes image as base64 and sends to LiteLLM."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This image shows a cat."
        mock_response.usage.prompt_tokens = 500
        mock_response.usage.completion_tokens = 20
        mock_litellm.acompletion.return_value = mock_response

        result = await provider.complete_with_vision(
            system_prompt="Describe images.",
            messages=[{"role": "user", "content": "What's in this image?"}],
            image_data=b"fake_image_bytes",
            media_type="image/png",
        )

        assert result.ok is True
        assert result.text == "This image shows a cat."

        # Verify the image was included as base64
        call_kwargs = mock_litellm.acompletion.call_args
        msgs = call_kwargs.kwargs["messages"]
        # Last message should contain image_url
        last_msg = msgs[-1]
        assert isinstance(last_msg["content"], list)
        assert any(
            item.get("type") == "image_url"
            for item in last_msg["content"]
        )


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------

class TestCostCalculation:
    """Test cost calculation logic."""

    def test_calc_cost_uses_litellm(self, provider, mock_litellm):
        """Cost calculation tries LiteLLM's pricing first."""
        mock_litellm.completion_cost.return_value = 0.0025
        cost = provider._calc_cost("gpt-4o", 1000, 500)
        assert cost == 0.0025

    def test_calc_cost_local_fallback(self, provider, mock_litellm):
        """Falls back to local pricing when LiteLLM fails."""
        mock_litellm.completion_cost.side_effect = Exception("No pricing data")
        cost = provider._calc_cost("gpt-4o", 1_000_000, 1_000_000)
        # GPT-4o: $2.50/M in + $10.00/M out = $12.50
        assert cost == pytest.approx(12.50, abs=0.01)

    def test_calc_cost_unknown_model_returns_zero(self, provider, mock_litellm):
        """Unknown models return zero cost when LiteLLM has no pricing."""
        mock_litellm.completion_cost.side_effect = Exception("Unknown")
        cost = provider._calc_cost("unknown-model-xyz", 1000, 500)
        assert cost == 0.0


# ---------------------------------------------------------------------------
# Default model catalog verification
# ---------------------------------------------------------------------------

class TestModelCatalog:
    """Verify the default model catalog is well-formed."""

    def test_all_models_have_display_name(self, provider):
        for model in provider.list_models():
            assert model.display_name, f"Model {model.model_id} has no display name"

    def test_all_models_have_capabilities(self, provider):
        for model in provider.list_models():
            assert len(model.capabilities) > 0, f"Model {model.model_id} has no capabilities"

    def test_all_models_have_text_capability(self, provider):
        for model in provider.list_models():
            assert Capability.TEXT in model.capabilities, f"Model {model.model_id} missing TEXT"

    def test_tier_1_costs_less_than_tier_2(self, provider):
        models = provider.list_models()
        tier1 = [m for m in models if m.tier == 1]
        tier2 = [m for m in models if m.tier == 2]
        if tier1 and tier2:
            max_tier1_cost = max(m.input_cost_per_m + m.output_cost_per_m for m in tier1)
            min_tier2_cost = min(m.input_cost_per_m + m.output_cost_per_m for m in tier2)
            # Tier 1 should generally be cheaper (not strictly enforced)
            assert max_tier1_cost <= min_tier2_cost * 2  # Allow some overlap
