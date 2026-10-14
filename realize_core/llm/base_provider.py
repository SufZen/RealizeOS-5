"""
Base LLM Provider: Abstract interface for all LLM providers.

All providers (Claude, Gemini, OpenAI, Ollama, etc.) implement this interface,
enabling provider-agnostic routing and easy addition of new models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar


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
        model_id: The provider's model identifier string (e.g., "claude-sonnet-5-5")
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


# LLMResponse.error value for a safety refusal (see LLMResponse.refused).
REFUSAL_ERROR = "refusal"

# User-facing text of a refusal that came back without text of its own
# (a Gemini SAFETY block, an OpenAI content_filter stop).
REFUSAL_TEXT = "I can't help with that request."

# LLMResponse.error value when a model returned neither text nor tool calls.
# Treated as a failure so the router falls back to the next provider.
EMPTY_ERROR = "empty_response"

# Provider-neutral stop reasons (LLMResponse.stop_reason).
STOP_END = "end"
STOP_TOOL_USE = "tool_use"
STOP_MAX_TOKENS = "max_tokens"
STOP_REFUSAL = "refusal"
STOP_PAUSE = "pause"
STOP_ERROR = "error"


def empty_or_text(text: str | None) -> tuple[str, str | None]:
    """Normalise model text and flag empty output.

    Returns ``(text, error)``: ``error`` is ``EMPTY_ERROR`` when the text is
    empty or whitespace-only, else None. Call it only when there are no tool
    calls (a tool-only turn legitimately has no text).
    """
    text = text or ""
    if not text.strip():
        return text, EMPTY_ERROR
    return text, None


@dataclass
class ToolCall:
    """A provider-neutral tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict


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
        tool_calls: Tool invocations the model requested (neutral form)
        stop_reason: One of the STOP_* constants
        assistant_message: Provider-native assistant message to append to the
            history when continuing a tool loop
    """

    text: str
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    raw: Any = None
    error: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = STOP_END
    assistant_message: dict | None = None

    @property
    def ok(self) -> bool:
        """True if the response completed without errors."""
        return self.error is None

    @property
    def refused(self) -> bool:
        """True if the model declined the request on safety grounds.

        A refusal is a final answer: callers must not retry it on another
        provider, which would route around the model's safety decision.
        """
        return self.error == REFUSAL_ERROR


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
    - user_text_message() / tool_result_messages(): history message shapes
      (defaults are OpenAI-shaped)
    """

    # Wire format used to serialise tool schemas ("openai" or "claude").
    tools_format: str = "openai"
    # Routing tier ("fast", "standard", "deep") -> registry model key for that tier.
    # A tier without an entry uses default_model_id().
    tier_models: ClassVar[dict[str, str]] = {}
    # True when complete_with_vision() reads application/pdf natively; other
    # providers get a PDF's extracted text instead.
    supports_pdf_input: ClassVar[bool] = False

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
        timeout: float = 60.0,
        response_schema: dict | None = None,
    ) -> LLMResponse:
        """Send a text completion request.

        Args:
            system_prompt: The assembled system prompt
            messages: Conversation history [{"role": "user"/"assistant", "content": "..."}]
            model: Model identifier. Uses provider default if None.
            max_tokens: Maximum response tokens
            temperature: Creativity level (0.0 = deterministic, 1.0 = creative)
            timeout: Request timeout in seconds (default 60s)
            response_schema: Optional JSON schema the reply must follow.
                Providers without native support may ignore it or fall back
                to a JSON instruction in the prompt.

        Returns:
            LLMResponse with the completion result.
        """
        ...

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """Return the models this provider offers."""
        ...

    def user_text_message(self, text: str) -> dict:
        """Build a user message carrying plain text (OpenAI shape by default)."""
        return {"role": "user", "content": text}

    def tool_result_messages(self, results: list[tuple[ToolCall, str, bool]]) -> list[dict]:
        """Build history messages returning tool results to the model.

        Args:
            results: ``(call, output, is_error)`` per executed tool call.

        Default is OpenAI-shaped: one ``role=tool`` message per result.
        """
        return [
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": f"ERROR: {output}" if is_error else output,
            }
            for call, output, is_error in results
        ]

    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        timeout: float = 60.0,
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

    def default_model_id(self) -> str | None:
        """Model used when a call names none (None = the provider decides)."""
        return None

    def is_model_usable(self, model_id: str) -> bool:
        """Check whether a specific model can be called on this provider.

        Default returns True. Providers that learn a model is gone (for example
        a retired model ID answering 404) override this so routing skips it.
        """
        return True

    def model_errors(self) -> dict[str, str]:
        """Return configured models known to be unusable, mapped to the reason.

        Default is empty. Shown in Settings so a dead model ID is visible
        instead of the provider looking healthy because its key is set.
        """
        return {}

    def supports(self, capability: Capability) -> bool:
        """Check if any of this provider's models support a capability."""
        return any(capability in m.capabilities for m in self.list_models())
