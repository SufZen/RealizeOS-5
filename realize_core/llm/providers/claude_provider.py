"""
Claude LLM Provider: Wraps the existing claude_client module behind BaseLLMProvider.

Supports text, vision, and tool use via Anthropic's Claude API.
"""
import logging

from realize_core.llm.base_provider import (
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
)

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider (Sonnet, Opus)."""

    _MODELS = None  # Lazy-loaded to avoid circular imports

    @property
    def name(self) -> str:
        return "claude"

    def _get_models_config(self) -> dict:
        """Load model IDs from config (lazy, avoids circular import)."""
        if self._MODELS is None:
            from realize_core.config import MODELS
            ClaudeProvider._MODELS = MODELS
        return self._MODELS

    def list_models(self) -> list[ModelInfo]:
        models = self._get_models_config()
        return [
            ModelInfo(
                model_id=models.get("claude_sonnet", "claude-sonnet-4-6-20260217"),
                display_name="Claude Sonnet",
                tier=2,
                capabilities={Capability.TEXT, Capability.VISION, Capability.TOOLS},
                input_cost_per_m=3.0,
                output_cost_per_m=15.0,
                max_tokens=8192,
                context_window=200000,
            ),
            ModelInfo(
                model_id=models.get("claude_opus", "claude-opus-4-6-20260205"),
                display_name="Claude Opus",
                tier=3,
                capabilities={Capability.TEXT, Capability.VISION, Capability.TOOLS},
                input_cost_per_m=15.0,
                output_cost_per_m=75.0,
                max_tokens=4096,
                context_window=200000,
            ),
        ]

    def is_available(self) -> bool:
        """Check if anthropic SDK is installed and API key is configured."""
        try:
            import anthropic  # noqa: F401

            from realize_core.config import ANTHROPIC_API_KEY
            return bool(ANTHROPIC_API_KEY)
        except ImportError:
            return False

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Text completion via Claude API."""
        import anthropic

        from realize_core.llm.claude_client import _log_usage

        models = self._get_models_config()
        model = model or models.get("claude_sonnet")

        try:
            from realize_core.llm.claude_client import _get_client
            client = _get_client()

            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
            )

            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)
            cost = self._calc_cost(model, input_tokens, output_tokens)

            _log_usage(model, response.usage)

            return LLMResponse(
                text=response.content[0].text,
                model=model,
                provider=self.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                raw=response,
            )

        except anthropic.RateLimitError:
            logger.warning("Claude rate limit hit.")
            return LLMResponse(
                text="Rate limit hit. Please try again in a moment.",
                model=model, provider=self.name,
                error="rate_limit",
            )

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return LLMResponse(
                text="An error occurred processing your request. Please try again.",
                model=model, provider=self.name,
                error=str(e),
            )

        except Exception as e:
            logger.error(f"Unexpected error calling Claude: {e}", exc_info=True)
            return LLMResponse(
                text="An error occurred processing your request. Please try again.",
                model=model, provider=self.name,
                error=str(e),
            )

    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Tool-use completion via Claude API."""
        from realize_core.llm.claude_client import call_claude_with_tools

        models = self._get_models_config()
        model = model or models.get("claude_sonnet")

        try:
            response = await call_claude_with_tools(
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
            )
            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)

            # Extract text from response (may have tool_use blocks)
            text_parts = [b.text for b in response.content if hasattr(b, "text")]
            text = "\n".join(text_parts) if text_parts else ""

            return LLMResponse(
                text=text,
                model=model,
                provider=self.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=self._calc_cost(model, input_tokens, output_tokens),
                raw=response,
            )
        except RuntimeError as e:
            return LLMResponse(
                text=str(e),
                model=model, provider=self.name,
                error=str(e),
            )

    async def complete_with_vision(
        self,
        system_prompt: str,
        messages: list[dict],
        image_data: bytes,
        media_type: str = "image/jpeg",
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Vision completion via Claude API."""
        from realize_core.llm.claude_client import call_claude_vision

        models = self._get_models_config()
        model = model or models.get("claude_sonnet")

        text = await call_claude_vision(
            system_prompt=system_prompt,
            messages=messages,
            image_data=image_data,
            media_type=media_type,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return LLMResponse(text=text, model=model, provider=self.name)

    def _calc_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost based on model pricing."""
        pricing = {}
        for m_info in self.list_models():
            pricing[m_info.model_id] = (m_info.input_cost_per_m, m_info.output_cost_per_m)

        in_rate, out_rate = pricing.get(model, (3.0, 15.0))
        return (input_tokens * in_rate / 1_000_000) + (output_tokens * out_rate / 1_000_000)
