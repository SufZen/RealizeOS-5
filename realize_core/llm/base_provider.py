"""
Base LLM Provider: Abstract interface for all LLM providers.

All providers (Claude, Gemini, OpenAI, Ollama, etc.) implement this interface,
enabling provider-agnostic routing and easy addition of new models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Capability(Enum):
    """Features a provider may support."""

    TEXT = "text"
    VISION = "vision"
    TOOLS = "tools"
    STREAMING = "streaming"
    CODE = "code"


@dataclass
class ModelInfo:
    """Metadata about a specific model offered by a provider.

    Attributes:
        model_id: The provider's model identifier string (e.g., "claude-sonnet-4-6-20260217")
        display_name: Human-readable name (e.g., "Claude Sonnet")
        tier: Cost tier (1=cheap, 2=mid, 3=premium)
        capabilities: Set of supported capabilities
        input_cost_per_m: Cost per 1M input tokens in USD
        output_cost_per_m: Cost per 1M output tokens in USD
        max_tokens: Maximum output tokens
        context_window: Maximum context window size
    """

    model_id: str
    display_name: str = ""
    tier: int = 2
    capabilities: set[Capability] = field(default_factory=lambda: {Capability.TEXT})
    input_cost_per_m: float = 0.0
    output_cost_per_m: float = 0.0
    max_tokens: int = 4096
    context_window: int = 128000


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider.

    Attributes:
        text: The response text content
        model: The model that generated the response
        provider: The provider name (e.g., "claude", "gemini")
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens generated
        cost_usd: Estimated cost in USD
        raw: The raw provider-specific response object (for tool_use, etc.)
        error: Error message if the call failed (text will contain a user-friendly fallback)
    """

    text: str
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    raw: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True if the response completed without errors."""
        return self.error is None


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.

    Subclasses must implement:
    - name: provider identifier string
    - complete(): text completion
    - list_models(): available models

    Optional overrides:
    - complete_with_tools(): tool-use completion
    - complete_with_vision(): vision completion
    - is_available(): runtime availability check
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'claude', 'gemini', 'openai')."""
        ...

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send a text completion request.

        Args:
            system_prompt: The assembled system prompt
            messages: Conversation history [{"role": "user"/"assistant", "content": "..."}]
            model: Model identifier. Uses provider default if None.
            max_tokens: Maximum response tokens
            temperature: Creativity level (0.0 = deterministic, 1.0 = creative)

        Returns:
            LLMResponse with the completion result.
        """
        ...

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """Return the models this provider offers."""
        ...

    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a completion request with tool definitions.

        Default implementation raises NotImplementedError.
        Override in providers that support tool use.
        """
        raise NotImplementedError(f"{self.name} does not support tool use")

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
        """Send a completion request with an image.

        Default implementation raises NotImplementedError.
        Override in providers that support vision.
        """
        raise NotImplementedError(f"{self.name} does not support vision")

    def is_available(self) -> bool:
        """Check if this provider is available (SDK installed, key configured).

        Default returns True. Override to add runtime checks.
        """
        return True

    def supports(self, capability: Capability) -> bool:
        """Check if any of this provider's models support a capability."""
        return any(capability in m.capabilities for m in self.list_models())
