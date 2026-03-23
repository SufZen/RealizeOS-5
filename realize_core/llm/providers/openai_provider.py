"""
OpenAI LLM Provider: Stub for future OpenAI/GPT integration.

To activate: pip install openai, set OPENAI_API_KEY, and uncomment registration in registry.
"""

import logging

from realize_core.llm.base_provider import (
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider (stub — ready for implementation)."""

    @property
    def name(self) -> str:
        return "openai"

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                model_id="gpt-4o",
                display_name="GPT-4o",
                tier=2,
                capabilities={Capability.TEXT, Capability.VISION, Capability.TOOLS},
                input_cost_per_m=2.50,
                output_cost_per_m=10.0,
                max_tokens=4096,
                context_window=128000,
            ),
            ModelInfo(
                model_id="gpt-4o-mini",
                display_name="GPT-4o Mini",
                tier=1,
                capabilities={Capability.TEXT, Capability.VISION, Capability.TOOLS},
                input_cost_per_m=0.15,
                output_cost_per_m=0.60,
                max_tokens=4096,
                context_window=128000,
            ),
        ]

    def is_available(self) -> bool:
        try:
            import os

            import openai  # noqa: F401

            return bool(os.getenv("OPENAI_API_KEY"))
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
        """Text completion via OpenAI API (stub)."""
        if not self.is_available():
            return LLMResponse(
                text="OpenAI provider not configured. Install openai and set OPENAI_API_KEY.",
                model=model or "gpt-4o",
                provider=self.name,
                error="not_configured",
            )

        # TODO: Implement when ready
        # import openai
        # client = openai.AsyncOpenAI()
        # response = await client.chat.completions.create(
        #     model=model or "gpt-4o",
        #     messages=[{"role": "system", "content": system_prompt}] + messages,
        #     max_tokens=max_tokens,
        #     temperature=temperature,
        # )
        # return LLMResponse(text=response.choices[0].message.content, ...)

        return LLMResponse(
            text="OpenAI provider not yet implemented.",
            model=model or "gpt-4o",
            provider=self.name,
            error="not_implemented",
        )
