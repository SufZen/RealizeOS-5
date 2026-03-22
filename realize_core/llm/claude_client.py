"""
Anthropic Claude API client wrapper.
Supports multiple tiers: Sonnet (reasoning, content) and Opus (complex strategy).
"""
import logging

import anthropic

logger = logging.getLogger(__name__)

# Lazy-initialized client (created on first use)
_client: anthropic.AsyncAnthropic | None = None


def _get_client(api_key: str = None) -> anthropic.AsyncAnthropic:
    """Get or create the async Anthropic client."""
    global _client
    if _client is None:
        from realize_core.config import ANTHROPIC_API_KEY
        key = api_key or ANTHROPIC_API_KEY
        if not key:
            raise RuntimeError("Anthropic API key not configured. Set ANTHROPIC_API_KEY.")
        _client = anthropic.AsyncAnthropic(api_key=key)
    return _client


async def call_claude(
    system_prompt: str,
    messages: list[dict],
    model: str = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """
    Send a request to Claude API (async).

    Args:
        system_prompt: The assembled system prompt
        messages: Conversation history [{"role": "user"/"assistant", "content": "..."}]
        model: Model name. Defaults to Claude Sonnet.
        max_tokens: Maximum response tokens.
        temperature: Creativity level (0.0 = deterministic, 1.0 = creative)

    Returns:
        The assistant's response text.
    """
    from realize_core.config import MODELS

    client = _get_client()
    model = model or MODELS["claude_sonnet"]

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
        )

        _log_usage(model, response.usage)
        return response.content[0].text

    except anthropic.RateLimitError:
        logger.warning("Claude rate limit hit.")
        return "Rate limit hit. Please try again in a moment."

    except anthropic.APIError as e:
        logger.error(f"Claude API error: {e}")
        return "An error occurred processing your request. Please try again."

    except Exception as e:
        logger.error(f"Unexpected error calling Claude: {e}", exc_info=True)
        return "An error occurred processing your request. Please try again."


async def call_claude_with_tools(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    model: str = None,
    max_tokens: int = 4096,
) -> anthropic.types.Message:
    """
    Call Claude with tool definitions. Returns the full Message object
    so the caller can inspect tool_use blocks.

    Raises:
        RuntimeError: If API call fails.
    """
    from realize_core.config import MODELS

    client = _get_client()
    model = model or MODELS["claude_sonnet"]

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.3,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )
        logger.info(f"Claude tool_use: model={model}, stop={response.stop_reason}, "
                     f"usage={response.usage.input_tokens}in/{response.usage.output_tokens}out")

        _log_usage(model, response.usage)
        return response

    except anthropic.RateLimitError as e:
        raise RuntimeError("Rate limit hit. Please try again in a moment.") from e

    except anthropic.BadRequestError as e:
        logger.error(f"Claude bad request (tool_use): {e}")
        raise RuntimeError("Could not process the request. Please try again.") from e

    except anthropic.APIError as e:
        logger.error(f"Claude API error (tool_use): {e}")
        raise RuntimeError("An error occurred with the AI service.") from e


async def call_claude_vision(
    system_prompt: str,
    messages: list[dict],
    image_data: bytes,
    media_type: str = "image/jpeg",
    model: str = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """
    Send a request to Claude API with an image for vision analysis.

    Supports images (jpeg, png, gif, webp) and PDFs.
    """
    import base64

    from realize_core.config import MODELS

    client = _get_client()
    model = model or MODELS["claude_sonnet"]

    try:
        vision_messages = []
        for msg in messages:
            if msg["role"] == "user" and msg is messages[-1]:
                b64_data = base64.b64encode(image_data).decode("utf-8")
                if media_type == "application/pdf":
                    content_blocks = [{
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": b64_data},
                    }]
                else:
                    content_blocks = [{
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64_data},
                    }]
                text = msg.get("content") or "Please analyze this image."
                content_blocks.append({"type": "text", "text": text})
                vision_messages.append({"role": "user", "content": content_blocks})
            else:
                vision_messages.append(msg)

        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=vision_messages,
        )
        return response.content[0].text

    except anthropic.RateLimitError:
        logger.warning("Claude rate limit hit (vision).")
        return "Rate limit hit. Please try again in a moment."

    except anthropic.APIError as e:
        logger.error(f"Claude API error (vision): {e}")
        return "An error occurred processing your image. Please try again."

    except Exception as e:
        logger.error(f"Unexpected error calling Claude vision: {e}", exc_info=True)
        return "An error occurred processing your image. Please try again."


def _log_usage(model: str, usage):
    """Log Claude API usage for cost tracking."""
    try:
        from realize_core.config import MODELS
        from realize_core.memory.store import log_llm_usage

        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)

        # Pricing per 1M tokens
        pricing = {
            MODELS["claude_sonnet"]: (3.0, 15.0),
            MODELS["claude_opus"]: (15.0, 75.0),
        }
        in_rate, out_rate = pricing.get(model, (3.0, 15.0))
        cost = (input_tokens * in_rate / 1_000_000) + (output_tokens * out_rate / 1_000_000)

        log_llm_usage(model=model, input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost)
    except Exception as e:
        logger.debug(f"Usage logging failed: {e}")


async def call_claude_sonnet(system_prompt: str, messages: list[dict], **kwargs) -> str:
    """Convenience wrapper for Claude Sonnet (tier 2: reasoning, content, tools)."""
    from realize_core.config import MODELS
    return await call_claude(system_prompt, messages, model=MODELS["claude_sonnet"], **kwargs)


async def call_claude_opus(system_prompt: str, messages: list[dict], **kwargs) -> str:
    """Convenience wrapper for Claude Opus (tier 3: complex strategy)."""
    from realize_core.config import MODELS
    return await call_claude(system_prompt, messages, model=MODELS["claude_opus"], **kwargs)
