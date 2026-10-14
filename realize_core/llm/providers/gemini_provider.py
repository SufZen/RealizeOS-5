"""
Gemini LLM Provider: Google Gemini through LiteLLM.

Text, vision and tool use are inherited from ``LiteLLMProvider``. The API key
is read from GOOGLE_AI_API_KEY and passed explicitly (LiteLLM's own variable is
GEMINI_API_KEY).
"""

import importlib.util
import logging
import os
from typing import Any

from realize_core import config
from realize_core.llm.base_provider import Capability, ModelInfo
from realize_core.llm.providers._litellm_adapter import PrefixedLiteLLMProvider

logger = logging.getLogger(__name__)

_CAPS = {Capability.TEXT, Capability.VISION, Capability.TOOLS}
# Thinking tokens count against max_tokens, so Gemini needs headroom.
_MIN_MAX_TOKENS = 8192


def model_keys() -> dict[str, str]:
    """Registry model keys -> LiteLLM model IDs for Gemini."""
    return {"gemini_flash": GeminiProvider._flash(), "gemini_pro": GeminiProvider._pro()}


class GeminiProvider(PrefixedLiteLLMProvider):
    """Google Gemini provider (Flash and Pro)."""

    prefix = "gemini/"

    def __init__(self) -> None:
        super().__init__(default_model=self._flash())

    @property
    def name(self) -> str:
        return "gemini"

    @staticmethod
    def _flash() -> str:
        return f"gemini/{config.MODELS.get('gemini_flash') or 'gemini-2.5-flash'}"

    @staticmethod
    def _pro() -> str:
        return f"gemini/{os.getenv('GEMINI_PRO_MODEL') or 'gemini-2.5-pro'}"

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                model_id=self._flash(),
                display_name="Gemini Flash",
                tier=1,
                capabilities=set(_CAPS),
                input_cost_per_m=0.30,
                output_cost_per_m=2.50,
                max_tokens=65536,
                context_window=1000000,
            ),
            ModelInfo(
                model_id=self._pro(),
                display_name="Gemini Pro",
                tier=2,
                capabilities=set(_CAPS),
                input_cost_per_m=1.25,
                output_cost_per_m=10.0,
                max_tokens=65536,
                context_window=1000000,
            ),
        ]

    def is_available(self) -> bool:
        """True when litellm is installed and GOOGLE_AI_API_KEY is set."""
        return bool(config.google_ai_api_key()) and importlib.util.find_spec("litellm") is not None

    def _min_max_tokens(self, model: str) -> int:
        return _MIN_MAX_TOKENS

    def _call_kwargs(self, model: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"api_key": config.google_ai_api_key()}
        if "2.5" in model:
            # LiteLLM maps reasoning_effort to Gemini's thinking budget; keep it small.
            kwargs["reasoning_effort"] = "low"
        return kwargs
