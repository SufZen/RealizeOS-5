"""
Gemini LLM Provider: Wraps the existing gemini_client module behind BaseLLMProvider.

Supports text and vision via Google's Gemini API.
"""

import asyncio
import logging

from realize_core.llm.base_provider import (
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
)

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider (Flash)."""

    _MODELS = None

    @property
    def name(self) -> str:
        return "gemini"

    def _get_models_config(self) -> dict:
        if self._MODELS is None:
            from realize_core.config import MODELS

            GeminiProvider._MODELS = MODELS
        return self._MODELS

    def list_models(self) -> list[ModelInfo]:
        models = self._get_models_config()
        return [
            ModelInfo(
                model_id=models.get("gemini_flash", "gemini-2.5-flash"),
                display_name="Gemini Flash",
                tier=1,
                capabilities={Capability.TEXT, Capability.VISION},
                input_cost_per_m=0.15,
                output_cost_per_m=0.60,
                max_tokens=8192,
                context_window=1000000,
            ),
        ]

    def is_available(self) -> bool:
        try:
            from google import genai  # noqa: F401

            from realize_core.config import GOOGLE_AI_API_KEY

            return bool(GOOGLE_AI_API_KEY)
        except ImportError:
            return False

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: float = 60.0,
    ) -> LLMResponse:
        """Text completion via Gemini API with timeout enforcement."""
        from google import genai

        from realize_core.llm.gemini_client import _get_client

        models = self._get_models_config()
        model = model or models.get("gemini_flash")

        try:
            client = _get_client()

            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(genai.types.Content(role=role, parts=[genai.types.Part(text=msg["content"])]))

            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    ),
                ),
                timeout=timeout,
            )

            # Extract usage
            usage_meta = getattr(response, "usage_metadata", None)
            input_tokens = getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0
            output_tokens = getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0
            cost = (input_tokens * 0.15 / 1_000_000) + (output_tokens * 0.60 / 1_000_000)

            # Log usage
            try:
                from realize_core.memory.store import log_llm_usage

                log_llm_usage(model=model, input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost)
            except Exception:
                pass

            return LLMResponse(
                text=response.text or "Empty response from Gemini.",
                model=model,
                provider=self.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                raw=response,
            )

        except TimeoutError:
            logger.error(f"Gemini API call timed out after {timeout}s")
            return LLMResponse(
                text="Request timed out. Please try again.",
                model=model,
                provider=self.name,
                error="timeout",
            )

        except Exception as e:
            logger.error(f"Gemini API error: {e}", exc_info=True)
            return LLMResponse(
                text="An error occurred processing your request. Please try again.",
                model=model,
                provider=self.name,
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
        """Vision completion via Gemini API."""
        from realize_core.llm.gemini_client import call_gemini_vision

        models = self._get_models_config()
        model = model or models.get("gemini_flash")

        text = await call_gemini_vision(
            system_prompt=system_prompt,
            messages=messages,
            image_data=image_data,
            media_type=media_type,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return LLMResponse(text=text, model=model, provider=self.name)
