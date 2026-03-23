"""
LiteLLM Provider: Unified interface to 50+ LLM providers via LiteLLM.

Wraps the LiteLLM library behind BaseLLMProvider, enabling access to
OpenAI, Azure, Bedrock, Cohere, Mistral, Together, Replicate, and many
more — all through a single provider instance.

Key features:
- Dynamically lists available models based on configured API keys
- Supports text, vision, and tool-use completions
- Calculates cost using LiteLLM's built-in cost tracker
- Feature-gated: only active when `litellm` is installed
"""

import logging

from realize_core.llm.base_provider import (
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
)

logger = logging.getLogger(__name__)

# Default models per provider that LiteLLM can route to.
# Each entry: (litellm_model_id, display_name, tier, capabilities, input_cost_m, output_cost_m, max_tokens, ctx_window)
_DEFAULT_LITELLM_MODELS: list[tuple[str, str, int, set[Capability], float, float, int, int]] = [
    (
        "gpt-4o",
        "GPT-4o",
        2,
        {Capability.TEXT, Capability.VISION, Capability.TOOLS},
        2.50,
        10.00,
        16384,
        128000,
    ),
    (
        "gpt-4o-mini",
        "GPT-4o Mini",
        1,
        {Capability.TEXT, Capability.VISION, Capability.TOOLS},
        0.15,
        0.60,
        16384,
        128000,
    ),
    (
        "o3-mini",
        "o3-mini",
        2,
        {Capability.TEXT, Capability.CODE},
        1.10,
        4.40,
        100000,
        200000,
    ),
    (
        "mistral/mistral-large-latest",
        "Mistral Large",
        2,
        {Capability.TEXT, Capability.TOOLS},
        2.00,
        6.00,
        8192,
        128000,
    ),
    (
        "mistral/mistral-small-latest",
        "Mistral Small",
        1,
        {Capability.TEXT},
        0.10,
        0.30,
        8192,
        32000,
    ),
    (
        "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "Llama 3.3 70B",
        1,
        {Capability.TEXT, Capability.CODE},
        0.88,
        0.88,
        8192,
        128000,
    ),
    (
        "deepseek/deepseek-chat",
        "DeepSeek V3",
        1,
        {Capability.TEXT, Capability.CODE},
        0.27,
        1.10,
        8192,
        128000,
    ),
    (
        "cohere/command-r-plus",
        "Cohere Command R+",
        2,
        {Capability.TEXT, Capability.TOOLS},
        2.50,
        10.00,
        4096,
        128000,
    ),
]


class LiteLLMProvider(BaseLLMProvider):
    """Provider that routes to 50+ LLM providers via the LiteLLM library.

    LiteLLM normalizes the interface for OpenAI, Azure, Bedrock, Cohere,
    Mistral, Together, Replicate, and many more. This provider exposes
    them all through the standard BaseLLMProvider interface.

    Configuration:
        Set the appropriate API keys as environment variables:
        - OPENAI_API_KEY (for GPT-4o, o3-mini, etc.)
        - MISTRAL_API_KEY
        - TOGETHER_API_KEY
        - DEEPSEEK_API_KEY
        - COHERE_API_KEY
        - etc.

    LiteLLM automatically discovers which providers are available based
    on the API keys present in the environment.
    """

    def __init__(
        self,
        enabled_models: list[str] | None = None,
        default_model: str = "gpt-4o-mini",
    ):
        """Initialize the LiteLLM provider.

        Args:
            enabled_models: Optional list of LiteLLM model IDs to expose.
                            If None, uses the default model catalog.
            default_model: The model to use when none is explicitly specified.
        """
        self._enabled_models = enabled_models
        self._default_model = default_model
        self._litellm = None  # Lazy-loaded

    @property
    def name(self) -> str:
        return "litellm"

    def _get_litellm(self):
        """Lazy-load the litellm module."""
        if self._litellm is None:
            import litellm

            # Suppress litellm's verbose logging by default
            litellm.suppress_debug_info = True
            self._litellm = litellm
        return self._litellm

    def is_available(self) -> bool:
        """Check if litellm is installed."""
        try:
            import litellm  # noqa: F401

            return True
        except ImportError:
            return False

    def list_models(self) -> list[ModelInfo]:
        """Return the models exposed through LiteLLM.

        If `enabled_models` was provided at init, only those models
        are listed. Otherwise, the full default catalog is returned.
        """
        models = []
        for model_id, display, tier, caps, in_cost, out_cost, max_tok, ctx in _DEFAULT_LITELLM_MODELS:
            if self._enabled_models and model_id not in self._enabled_models:
                continue
            models.append(
                ModelInfo(
                    model_id=model_id,
                    display_name=f"{display} (LiteLLM)",
                    tier=tier,
                    capabilities=caps,
                    input_cost_per_m=in_cost,
                    output_cost_per_m=out_cost,
                    max_tokens=max_tok,
                    context_window=ctx,
                )
            )
        return models

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Text completion via LiteLLM.

        Delegates to litellm.acompletion(), which auto-routes to the
        correct provider SDK based on the model string prefix.
        """
        litellm = self._get_litellm()
        model = model or self._default_model

        try:
            # Build messages in OpenAI format (LiteLLM uses this universally)
            openai_messages = []
            if system_prompt:
                openai_messages.append({"role": "system", "content": system_prompt})
            openai_messages.extend(messages)

            response = await litellm.acompletion(
                model=model,
                messages=openai_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            # Extract response data
            text = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

            # Calculate cost using LiteLLM's built-in pricing
            cost = self._calc_cost(model, input_tokens, output_tokens)

            return LLMResponse(
                text=text,
                model=model,
                provider=self.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                raw=response,
            )

        except Exception as e:
            logger.error(f"LiteLLM completion error ({model}): {e}", exc_info=True)
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
    ) -> LLMResponse:
        """Tool-use completion via LiteLLM.

        Passes OpenAI-format tool definitions; LiteLLM translates them
        to the target provider's format automatically.
        """
        litellm = self._get_litellm()
        model = model or self._default_model

        try:
            openai_messages = []
            if system_prompt:
                openai_messages.append({"role": "system", "content": system_prompt})
            openai_messages.extend(messages)

            response = await litellm.acompletion(
                model=model,
                messages=openai_messages,
                tools=tools,
                max_tokens=max_tokens,
            )

            choice = response.choices[0]
            text = choice.message.content or ""
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

            return LLMResponse(
                text=text,
                model=model,
                provider=self.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=self._calc_cost(model, input_tokens, output_tokens),
                raw=response,
            )

        except Exception as e:
            logger.error(f"LiteLLM tool completion error ({model}): {e}", exc_info=True)
            return LLMResponse(
                text=str(e),
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
        """Vision completion via LiteLLM.

        Encodes the image as base64 in the OpenAI vision message format.
        """
        import base64

        litellm = self._get_litellm()
        model = model or self._default_model

        b64_image = base64.b64encode(image_data).decode("utf-8")

        # Build vision message
        openai_messages = []
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})

        # Add any prior text messages
        for msg in messages[:-1] if messages else []:
            openai_messages.append(msg)

        # Last user message gets the image
        last_text = messages[-1]["content"] if messages else "Describe this image."
        openai_messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": last_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{b64_image}",
                        },
                    },
                ],
            }
        )

        try:
            response = await litellm.acompletion(
                model=model,
                messages=openai_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            text = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

            return LLMResponse(
                text=text,
                model=model,
                provider=self.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=self._calc_cost(model, input_tokens, output_tokens),
                raw=response,
            )

        except Exception as e:
            logger.error(f"LiteLLM vision error ({model}): {e}", exc_info=True)
            return LLMResponse(
                text="Vision processing failed. Please try again.",
                model=model,
                provider=self.name,
                error=str(e),
            )

    def _calc_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost using LiteLLM's pricing data, with local fallback."""
        # Try LiteLLM's built-in cost calculation first
        try:
            litellm = self._get_litellm()
            return litellm.completion_cost(
                model=model,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
            )
        except Exception:
            pass

        # Fallback: use our local pricing data
        for m_info in self.list_models():
            if m_info.model_id == model:
                return (input_tokens * m_info.input_cost_per_m / 1_000_000) + (
                    output_tokens * m_info.output_cost_per_m / 1_000_000
                )

        return 0.0
