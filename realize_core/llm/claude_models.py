"""
Claude model facts that don't need the SDK: pricing, which request
parameters a model accepts, and how to read its responses.

Kept apart from claude_client so callers (and tests) can use them without
creating an API client.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Price per 1M tokens (input, output), by model ID prefix. Longest prefix wins.
CLAUDE_PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
}
_DEFAULT_PRICE = (3.0, 15.0)

# Models from before adaptive thinking was on by default. Only these still
# accept `temperature`; newer ones (Opus 4.7+, Sonnet 5+, Haiku 5+, Fable)
# reject it with a 400 and think by default, so they need max_tokens headroom.
_LEGACY_MODEL = re.compile(r"^claude-(?:3[-.].*|instant.*|(?:opus|sonnet|haiku)-4(?:-[0-6])?(?:-\d{8})?)$")

# Floor for max_tokens on thinking-by-default models: it covers thinking + reply.
THINKING_MIN_MAX_TOKENS = 16000


def claude_price(model: str) -> tuple[float, float]:
    """Return (input, output) USD per 1M tokens for a Claude model ID."""
    matches = [prefix for prefix in CLAUDE_PRICING if model.startswith(prefix)]
    return CLAUDE_PRICING[max(matches, key=len)] if matches else _DEFAULT_PRICE


def is_legacy_model(model: str) -> bool:
    """True for Claude models that accept sampling params and don't think by default."""
    return bool(_LEGACY_MODEL.match(model))


def request_params(model: str, max_tokens: int, temperature: float | None) -> dict[str, Any]:
    """Model-dependent request parameters.

    Legacy models get ``temperature``; newer ones reject it (400) and get a
    larger ``max_tokens`` because their adaptive thinking counts against it.
    """
    if is_legacy_model(model):
        params: dict[str, Any] = {"max_tokens": max_tokens}
        if temperature is not None:
            params["temperature"] = temperature
        return params
    return {"max_tokens": max(max_tokens, THINKING_MIN_MAX_TOKENS)}


def response_text(response: Any) -> str:
    """Join the text blocks of a Message; thinking and tool blocks are skipped."""
    return "".join(
        str(getattr(block, "text", "")) for block in response.content if getattr(block, "type", "") == "text"
    )


def is_refusal(response: Any) -> bool:
    """True when the model declined the request (stop_reason == "refusal"); logs the category."""
    if getattr(response, "stop_reason", None) != "refusal":
        return False
    details = getattr(response, "stop_details", None)
    logger.info("Claude declined the request (category=%s)", getattr(details, "category", None))
    return True
