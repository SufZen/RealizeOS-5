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

import json
import logging
import os
from typing import Any

from realize_core.llm.base_provider import (
    EMPTY_ERROR,
    REFUSAL_ERROR,
    STOP_END,
    STOP_ERROR,
    STOP_MAX_TOKENS,
    STOP_REFUSAL,
    STOP_TOOL_USE,
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
    ToolCall,
    empty_or_text,
)
from realize_core.tools.base_tool import convert_tool_schemas

logger = logging.getLogger(__name__)

# OpenAI-style finish_reason -> neutral stop reason.
_FINISH_REASON_MAP = {
    "stop": STOP_END,
    "tool_calls": STOP_TOOL_USE,
    "function_call": STOP_TOOL_USE,
    "length": STOP_MAX_TOKENS,
    "content_filter": STOP_REFUSAL,
}

_FALLBACK_MODEL = "gpt-4o-mini"

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
        default_model: str | None = None,
    ):
        """Initialize the LiteLLM provider.

        Args:
            enabled_models: Optional list of LiteLLM model IDs to expose.
                            If None, uses the default model catalog.
            default_model: The model to use when none is explicitly specified.
                Falls back to $LITELLM_MODEL, then "gpt-4o-mini".

        $LITELLM_API_BASE, when set, is passed as ``api_base`` on every call
        (self-hosted / OpenAI-compatible endpoints).
        """
        self._enabled_models = enabled_models
        self._default_model = default_model or os.getenv("LITELLM_MODEL") or _FALLBACK_MODEL
        self._api_base = os.getenv("LITELLM_API_BASE") or None
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
        """True if litellm is installed and credentials or an endpoint exist.

        Reads the environment on every call (it can change at runtime).
        """
        try:
            import litellm

            if os.getenv("LITELLM_API_BASE"):
                return True
            return bool(litellm.validate_environment(model=self._default_model).get("keys_in_environment"))
        except Exception:
            return False

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
        """Build the kwargs shared by every ``litellm.acompletion`` call.

        Prepends the system prompt, omits ``temperature`` when None, adds
        ``api_base`` when configured, and merges provider-specific ``extra``.
        """
        full_messages: list[dict] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        api_base = os.getenv("LITELLM_API_BASE") or self._api_base
        if api_base:
            kwargs["api_base"] = api_base
        kwargs.update(extra)
        return kwargs

    def _supports_response_schema(self, model: str) -> bool:
        """True if LiteLLM reports native JSON-schema output for ``model``."""
        try:
            return bool(self._get_litellm().supports_response_schema(model=model))
        except Exception:
            return False

    @staticmethod
    def _usage(response: Any) -> tuple[int, int]:
        usage = getattr(response, "usage", None)
        return (
            getattr(usage, "prompt_tokens", 0) if usage else 0,
            getattr(usage, "completion_tokens", 0) if usage else 0,
        )

    @staticmethod
    def _parse_tool_calls(message: Any) -> list[ToolCall]:
        """Extract neutral ToolCalls from an OpenAI-shaped message."""
        calls: list[ToolCall] = []
        for tc in getattr(message, "tool_calls", None) or []:
            fn = tc.function
            raw_args = getattr(fn, "arguments", None)
            try:
                args = json.loads(raw_args) if raw_args else {}
                if not isinstance(args, dict):
                    raise ValueError("arguments is not an object")
            except (ValueError, TypeError):
                logger.warning("LiteLLM tool call %s has invalid JSON arguments: %r", fn.name, raw_args)
                args = {}
            calls.append(ToolCall(id=tc.id, name=fn.name, arguments=args))
        return calls

    def _build_response(self, response: Any, model: str, with_tools: bool = False) -> LLMResponse:
        """Turn a LiteLLM ModelResponse into a neutral LLMResponse."""
        choice = response.choices[0]
        message = choice.message
        text = message.content if isinstance(message.content, str) else ""
        tool_calls = self._parse_tool_calls(message) if with_tools else []
        stop_reason = _FINISH_REASON_MAP.get(getattr(choice, "finish_reason", None), STOP_END)
        if tool_calls:
            stop_reason = STOP_TOOL_USE

        error: str | None = None
        if stop_reason == STOP_REFUSAL:
            error = REFUSAL_ERROR
        elif not tool_calls:
            text, error = empty_or_text(text)
            if error == EMPTY_ERROR:
                stop_reason = STOP_ERROR

        assistant_message: dict | None = None
        if with_tools:
            assistant_message = {"role": "assistant", "content": text or None}
            if tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                    }
                    for c in tool_calls
                ]

        input_tokens, output_tokens = self._usage(response)
        return LLMResponse(
            text=text,
            model=model,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=self._calc_cost(model, input_tokens, output_tokens),
            raw=response,
            error=error,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            assistant_message=assistant_message,
        )

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
        timeout: float = 60.0,
        response_schema: dict | None = None,
    ) -> LLMResponse:
        """Text completion via LiteLLM.

        Delegates to litellm.acompletion(), which auto-routes to the
        correct provider SDK based on the model string prefix. With
        ``response_schema``, uses native JSON-schema output when the model
        supports it, else JSON mode plus a schema instruction in the prompt.
        """
        litellm = self._get_litellm()
        model = model or self._default_model

        try:
            extra: dict[str, Any] = {}
            if response_schema is not None:
                if self._supports_response_schema(model):
                    extra["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": "response", "schema": response_schema, "strict": False},
                    }
                else:
                    extra["response_format"] = {"type": "json_object"}
                    instruction = f"Respond ONLY with JSON matching this schema: {json.dumps(response_schema)}"
                    system_prompt = f"{system_prompt}\n\n{instruction}" if system_prompt else instruction

            response = await litellm.acompletion(
                **self._acompletion_kwargs(system_prompt, messages, model, max_tokens, temperature, timeout, **extra)
            )
            return self._build_response(response, model)

        except Exception as e:
            logger.error(f"LiteLLM completion error ({model}): {e}", exc_info=True)
            return LLMResponse(
                text="An error occurred processing your request. Please try again.",
                model=model,
                provider=self.name,
                error=str(e),
                stop_reason=STOP_ERROR,
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
        """Tool-use completion via LiteLLM.

        ``tools`` are Claude-format schemas (OpenAI-format entries pass
        through); they are sent in OpenAI format and LiteLLM translates them
        to the target provider's format.
        """
        litellm = self._get_litellm()
        model = model or self._default_model

        try:
            response = await litellm.acompletion(
                **self._acompletion_kwargs(
                    system_prompt,
                    messages,
                    model,
                    max_tokens,
                    timeout=timeout,
                    tools=convert_tool_schemas(tools, "openai"),
                )
            )
            return self._build_response(response, model, with_tools=True)

        except Exception as e:
            logger.error(f"LiteLLM tool completion error ({model}): {e}", exc_info=True)
            return LLMResponse(
                text="",
                model=model,
                provider=self.name,
                error=str(e),
                stop_reason=STOP_ERROR,
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

        # Prior messages stay as-is; the last user message gets the image.
        history = list(messages[:-1]) if messages else []
        last_text = messages[-1]["content"] if messages else "Describe this image."
        history.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": last_text},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64_image}"}},
                ],
            }
        )

        try:
            response = await litellm.acompletion(
                **self._acompletion_kwargs(system_prompt, history, model, max_tokens, temperature)
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
