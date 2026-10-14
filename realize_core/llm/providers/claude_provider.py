"""
Claude LLM Provider: Wraps the existing claude_client module behind BaseLLMProvider.

Supports text, vision, and tool use via Anthropic's Claude API.
"""

import asyncio
import logging
from typing import Any, ClassVar, cast

from realize_core.config import DEFAULT_CLAUDE_OPUS_MODEL, DEFAULT_CLAUDE_SONNET_MODEL
from realize_core.llm.base_provider import (
    REFUSAL_ERROR,
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
)
from realize_core.llm.claude_models import (
    ClaudeModelNotFoundError,
    claude_price,
    is_refusal,
    request_params,
    response_text,
)

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider (Sonnet, Opus)."""

    _MODELS: ClassVar[dict[str, str] | None] = None  # Lazy-loaded to avoid circular imports
    # Model IDs Anthropic answered 404 for (retired or misspelled), mapped to the error.
    # Process-wide: a restart with a corrected CLAUDE_*_MODEL clears it.
    _dead_models: ClassVar[dict[str, str]] = {}

    @property
    def name(self) -> str:
        return "claude"

    def _get_models_config(self) -> dict[str, str]:
        """Load model IDs from config (lazy, avoids circular import)."""
        if self._MODELS is None:
            from realize_core.config import MODELS

            ClaudeProvider._MODELS = MODELS
        return ClaudeProvider._MODELS or {}

    def list_models(self) -> list[ModelInfo]:
        models = self._get_models_config()
        sonnet = models.get("claude_sonnet", DEFAULT_CLAUDE_SONNET_MODEL)
        opus = models.get("claude_opus", DEFAULT_CLAUDE_OPUS_MODEL)
        return [
            ModelInfo(
                model_id=sonnet,
                display_name="Claude Sonnet",
                tier=2,
                capabilities={Capability.TEXT, Capability.VISION, Capability.TOOLS},
                input_cost_per_m=claude_price(sonnet)[0],
                output_cost_per_m=claude_price(sonnet)[1],
                max_tokens=128000,
                context_window=1000000,
            ),
            ModelInfo(
                model_id=opus,
                display_name="Claude Opus",
                tier=3,
                capabilities={Capability.TEXT, Capability.VISION, Capability.TOOLS},
                input_cost_per_m=claude_price(opus)[0],
                output_cost_per_m=claude_price(opus)[1],
                max_tokens=128000,
                context_window=1000000,
            ),
        ]

    def is_available(self) -> bool:
        """Check the SDK is installed, the API key is set, and a configured model still answers.

        Once every configured model has returned 404 the provider reports itself
        unavailable, so Settings stop showing it healthy and the fallback chain skips it.
        """
        try:
            import anthropic  # noqa: F401

        except ImportError:
            return False
        from realize_core.config import anthropic_api_key

        if not anthropic_api_key():
            return False
        configured = {m.model_id for m in self.list_models()}
        return not configured.issubset(self._dead_models)

    def is_model_usable(self, model_id: str) -> bool:
        """Return False for a model ID that Anthropic has answered 404 for."""
        return model_id not in self._dead_models

    def model_errors(self) -> dict[str, str]:
        """Return configured model IDs known to be unusable, with the API error."""
        return dict(self._dead_models)

    @classmethod
    def _mark_model_dead(cls, model: str, error: str) -> None:
        """Remember that a model ID returned 404 and log it once, loudly."""
        if model not in cls._dead_models:
            logger.error(
                "Claude model %r was not found (404). It is likely retired; set "
                "CLAUDE_SONNET_MODEL / CLAUDE_OPUS_MODEL to a current ID. Routing will skip it.",
                model,
            )
        cls._dead_models[model] = error

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: float = 60.0,
        response_schema: dict | None = None,  # accepted for interface parity; unused
    ) -> LLMResponse:
        """Text completion via Claude API with timeout enforcement."""
        import anthropic

        from realize_core.llm.claude_client import _log_usage

        models = self._get_models_config()
        model = model or models.get("claude_sonnet") or DEFAULT_CLAUDE_SONNET_MODEL

        try:
            from realize_core.llm.claude_client import _get_client

            client = _get_client()

            response = await asyncio.wait_for(
                client.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=cast(Any, messages),
                    **request_params(model, max_tokens, temperature),
                ),
                timeout=timeout,
            )

            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)
            cost = self._calc_cost(model, input_tokens, output_tokens)

            _log_usage(model, response.usage)

            if is_refusal(response):
                # Final: the router returns this as-is and does not retry another provider.
                return LLMResponse(
                    text="I can't help with that request.",
                    model=model,
                    provider=self.name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    error=REFUSAL_ERROR,
                )

            return LLMResponse(
                text=response_text(response),
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
                model=model,
                provider=self.name,
                error="rate_limit",
            )

        except anthropic.NotFoundError as e:
            self._mark_model_dead(model, str(e))
            return LLMResponse(
                text="An error occurred processing your request. Please try again.",
                model=model,
                provider=self.name,
                error="model_not_found",
            )

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return LLMResponse(
                text="An error occurred processing your request. Please try again.",
                model=model,
                provider=self.name,
                error=str(e),
            )

        except TimeoutError:
            logger.error(f"Claude API call timed out after {timeout}s")
            return LLMResponse(
                text="Request timed out. Please try again.",
                model=model,
                provider=self.name,
                error="timeout",
            )

        except Exception as e:
            logger.error(f"Unexpected error calling Claude: {e}", exc_info=True)
            return LLMResponse(
                text="An error occurred processing your request. Please try again.",
                model=model,
                provider=self.name,
                error=str(e),
            )

    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ) -> LLMResponse:
        """Tool-use completion via Claude API.

        If a model answers 404 it is marked dead and the same request is sent
        to the next configured Claude model. The failed call produced nothing,
        so no tool is dispatched twice. Other errors are returned as-is; they
        never trigger a model switch.
        """
        from realize_core.llm.claude_client import call_claude_with_tools

        models = self._get_models_config()
        requested = model or models.get("claude_sonnet") or DEFAULT_CLAUDE_SONNET_MODEL
        candidates = [requested] + [m.model_id for m in self.list_models() if m.model_id != requested]
        candidates = [m for m in candidates if self.is_model_usable(m)]

        for candidate in candidates:
            try:
                response = await call_claude_with_tools(
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=tools,
                    model=candidate,
                    max_tokens=max_tokens,
                )
            except ClaudeModelNotFoundError as e:
                self._mark_model_dead(candidate, str(e))
                continue
            except RuntimeError as e:
                return LLMResponse(text=str(e), model=candidate, provider=self.name, error=str(e))

            if candidate != requested:
                logger.warning("Tool call sent to %s because %s is unavailable", candidate, requested)
            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)
            return LLMResponse(
                text=response_text(response),
                model=candidate,
                provider=self.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=self._calc_cost(candidate, input_tokens, output_tokens),
                raw=response,
            )

        return LLMResponse(
            text="An error occurred with the AI service.",
            model=requested,
            provider=self.name,
            error="model_not_found",
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
        model = model or models.get("claude_sonnet") or DEFAULT_CLAUDE_SONNET_MODEL

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
        in_rate, out_rate = claude_price(model)
        return (input_tokens * in_rate / 1_000_000) + (output_tokens * out_rate / 1_000_000)
