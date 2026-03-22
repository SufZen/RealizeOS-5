"""
Google Gemini API client wrapper.
Uses Gemini Flash for routine tasks (cheap/free tier).
"""
import logging

logger = logging.getLogger(__name__)

# Lazy-initialized client
_client = None


def _get_client(api_key: str = None):
    """Get or create the Gemini client."""
    global _client
    if _client is None:
        from google import genai
        from realize_core.config import GOOGLE_AI_API_KEY
        key = api_key or GOOGLE_AI_API_KEY
        if not key:
            raise RuntimeError("Google AI API key not configured. Set GOOGLE_AI_API_KEY.")
        _client = genai.Client(api_key=key)
    return _client


async def call_gemini(
    system_prompt: str,
    messages: list[dict],
    model: str = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """
    Send a request to Gemini API (async).

    Args:
        system_prompt: The assembled system prompt
        messages: Conversation history [{"role": "user"/"assistant", "content": "..."}]
        model: Model name. Defaults to Gemini Flash.
        max_tokens: Maximum response tokens.
        temperature: Creativity level.

    Returns:
        The assistant's response text.
    """
    from google import genai
    from realize_core.config import MODELS

    client = _get_client()
    model = model or MODELS["gemini_flash"]

    try:
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(
                genai.types.Content(
                    role=role,
                    parts=[genai.types.Part(text=msg["content"])]
                )
            )

        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        # Log usage for cost tracking
        try:
            from realize_core.memory.store import log_llm_usage
            usage_meta = getattr(response, "usage_metadata", None)
            input_tokens = getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0
            output_tokens = getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0
            cost = (input_tokens * 0.15 / 1_000_000) + (output_tokens * 0.60 / 1_000_000)
            log_llm_usage(model=model, input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost)
        except Exception:
            pass

        return response.text or "Empty response from Gemini."

    except Exception as e:
        logger.error(f"Gemini API error: {e}", exc_info=True)
        return "An error occurred processing your request. Please try again."


async def call_gemini_vision(
    system_prompt: str,
    messages: list[dict],
    image_data: bytes,
    media_type: str = "image/jpeg",
    model: str = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """Send a request to Gemini API with an image for vision analysis."""
    from google import genai
    from realize_core.config import MODELS

    client = _get_client()
    model = model or MODELS["gemini_flash"]

    try:
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            if msg["role"] == "user" and msg is messages[-1]:
                parts = [
                    genai.types.Part.from_bytes(data=image_data, mime_type=media_type),
                ]
                text = msg.get("content") or "Please analyze this image."
                parts.append(genai.types.Part(text=text))
                contents.append(genai.types.Content(role=role, parts=parts))
            else:
                contents.append(
                    genai.types.Content(
                        role=role,
                        parts=[genai.types.Part(text=msg["content"])]
                    )
                )

        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        return response.text or "Empty response from Gemini."

    except Exception as e:
        logger.error(f"Gemini vision API error: {e}", exc_info=True)
        return "An error occurred processing your image. Please try again."


async def call_gemini_flash(system_prompt: str, messages: list[dict], **kwargs) -> str:
    """Convenience wrapper for Gemini Flash (tier 1: routine tasks, Q&A)."""
    from realize_core.config import MODELS
    return await call_gemini(system_prompt, messages, model=MODELS["gemini_flash"], **kwargs)
