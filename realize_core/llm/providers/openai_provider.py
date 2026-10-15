"""
OpenAI LLM Provider: GPT models through LiteLLM.

Text, vision and tool use are inherited from ``LiteLLMProvider``; LiteLLM reads
OPENAI_API_KEY itself.
"""

import importlib.util
import os
from typing import ClassVar

from realize_core.llm.base_provider import Capability, ModelInfo
from realize_core.llm.providers._litellm_adapter import PrefixedLiteLLMProvider


def model_keys() -> dict[str, str]:
    """Registry model keys -> LiteLLM model IDs for OpenAI."""
    return {"gpt4o": "openai/gpt-4o", "gpt4o_mini": "openai/gpt-4o-mini"}


class OpenAIProvider(PrefixedLiteLLMProvider):
    """OpenAI GPT provider (GPT-4o, GPT-4o mini)."""

    prefix = "openai/"
    tier_models: ClassVar[dict[str, str]] = {"fast": "gpt4o_mini", "standard": "gpt4o", "deep": "gpt4o"}

    def __init__(self) -> None:
        super().__init__(default_model="openai/gpt-4o-mini")

    @property
    def name(self) -> str:
        return "openai"

    def list_models(self) -> list[ModelInfo]:
        caps = {Capability.TEXT, Capability.VISION, Capability.TOOLS}
        return [
            ModelInfo(
                model_id="openai/gpt-4o",
                display_name="GPT-4o",
                tier=2,
                capabilities=set(caps),
                input_cost_per_m=2.50,
                output_cost_per_m=10.0,
                max_tokens=16384,
                context_window=128000,
            ),
            ModelInfo(
                model_id="openai/gpt-4o-mini",
                display_name="GPT-4o Mini",
                tier=1,
                capabilities=set(caps),
                input_cost_per_m=0.15,
                output_cost_per_m=0.60,
                max_tokens=16384,
                context_window=128000,
            ),
        ]

    def _transcription_model(self) -> str | None:
        """Whisper, through ``litellm.atranscription`` (LiteLLM reads OPENAI_API_KEY)."""
        return "openai/whisper-1"

    def is_available(self) -> bool:
        """True when litellm is installed and OPENAI_API_KEY is set."""
        return bool(os.getenv("OPENAI_API_KEY")) and importlib.util.find_spec("litellm") is not None
