"""
Shared base for providers that are thin adapters over LiteLLM.

A subclass sets a LiteLLM model prefix (``gemini/``, ``openai/``, ``ollama_chat/``)
and supplies provider-specific call arguments (API key, base URL, ...). All
request building and response parsing is inherited from ``LiteLLMProvider``.
"""

from typing import Any, ClassVar

from realize_core.llm.litellm_provider import LiteLLMProvider


class PrefixedLiteLLMProvider(LiteLLMProvider):
    """LiteLLM provider pinned to a single upstream provider via a model prefix."""

    # LiteLLM routing prefix, e.g. "gemini/". Models given without it get it added.
    prefix: ClassVar[str] = ""

    def _litellm_model(self, model: str) -> str:
        """Return ``model`` in LiteLLM form (prefix added when missing)."""
        return model if model.startswith(self.prefix) else f"{self.prefix}{model}"

    def _call_kwargs(self, model: str) -> dict[str, Any]:
        """Extra ``acompletion`` kwargs for this provider (api_key, api_base, ...)."""
        return {}

    def _min_max_tokens(self, model: str) -> int:
        """Lower bound applied to ``max_tokens`` (0 = none)."""
        return 0

    def _acompletion_kwargs(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float | None = None,
        timeout: float = 60.0,
        **extra: Any,
    ) -> dict[str, Any]:
        model = self._litellm_model(model)
        kwargs = super()._acompletion_kwargs(
            system_prompt, messages, model, max(max_tokens, self._min_max_tokens(model)), temperature, timeout
        )
        # LITELLM_API_BASE belongs to the generic gateway, not to a pinned provider.
        kwargs.pop("api_base", None)
        kwargs.update(self._call_kwargs(model))
        kwargs.update(extra)
        return kwargs

    def _supports_response_schema(self, model: str) -> bool:
        return super()._supports_response_schema(self._litellm_model(model))

    def _calc_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        return super()._calc_cost(self._litellm_model(model), input_tokens, output_tokens)
