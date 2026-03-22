"""
Semantic skill matching — LLM-based fallback for skill detection.

When keyword-based matching fails to find a relevant skill,
the semantic matcher asks an LLM to evaluate whether any available
skill is a good fit for the user's message.

The module is designed to be:
- **Async** and non-blocking
- **Provider-agnostic** — works with any LLM callable
- **Gracefully degrading** — returns no-match if LLM is unavailable
- **Cacheable** — results are deterministic for the same (message, skills) pair

Usage::

    from realize_core.skills.semantic import semantic_match

    result = await semantic_match(
        message="How should I position my brand?",
        skill_summaries=[
            {"key": "content_pipeline", "description": "Content creation with review"},
            {"key": "strategy_session", "description": "Strategic analysis with review"},
        ],
    )
    if result and result.is_match:
        print(f"Matched: {result.skill_key} (score={result.score})")
"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

from realize_core.skills.base import SkillTriggerResult, TriggerMethod

logger = logging.getLogger(__name__)

# Type for the LLM completion callable
LLMCallable = Callable[..., Awaitable[str]]


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SEMANTIC_MATCH_PROMPT = """You are a skill-matching engine. Given a user message and a list of available skills, determine which skill (if any) best matches the user's intent.

## Available Skills
{skills_list}

## User Message
"{message}"

## Instructions
1. Analyse the user's intent from their message.
2. Compare against each skill's description and determine the best match.
3. If no skill is a good fit, respond with "NO_MATCH".
4. Respond ONLY with a JSON object in this exact format:

{{"skill_key": "<key of best matching skill or null>", "score": <0.0 to 1.0>, "reason": "<brief explanation>"}}

Rules:
- Score 0.8-1.0: Strong semantic match — the skill clearly handles this request
- Score 0.5-0.79: Moderate match — the skill could handle this but isn't perfect
- Score 0.0-0.49: Weak match — unlikely to be the right skill
- Respond with null skill_key and score 0.0 if nothing matches
- Be conservative — only return high scores for clear matches"""


# ---------------------------------------------------------------------------
# Core matching function
# ---------------------------------------------------------------------------

async def semantic_match(
    message: str,
    skill_summaries: list[dict[str, str]],
    llm_fn: LLMCallable | None = None,
    threshold: float = 0.6,
) -> SkillTriggerResult | None:
    """
    Use an LLM to semantically match a user message to available skills.

    Args:
        message: The user's input message.
        skill_summaries: List of dicts with ``key`` and ``description`` fields.
        llm_fn: Async callable for LLM completion. Signature:
                ``async def fn(system_prompt: str, messages: list) -> str``.
                If ``None``, attempts to use the default Claude client.
        threshold: Minimum score to consider a match (0.0–1.0).

    Returns:
        ``SkillTriggerResult`` if a match is found above threshold,
        ``None`` otherwise.
    """
    if not skill_summaries:
        return None

    if not message or not message.strip():
        return None

    # Build the skills list for the prompt
    skills_text = "\n".join(
        f"- **{s['key']}**: {s.get('description', '(no description)')}"
        for s in skill_summaries
    )

    prompt = _SEMANTIC_MATCH_PROMPT.format(
        skills_list=skills_text,
        message=message,
    )

    # Resolve the LLM callable
    if llm_fn is None:
        llm_fn = _get_default_llm()
        if llm_fn is None:
            logger.debug("No LLM available for semantic matching — skipping")
            return None

    # Call the LLM
    try:
        response = await llm_fn(
            system_prompt=prompt,
            messages=[{"role": "user", "content": "Match the skill."}],
        )
    except Exception as exc:
        logger.warning("Semantic match LLM call failed: %s", exc)
        return None

    # Parse the response
    return _parse_semantic_response(response, threshold)


# ---------------------------------------------------------------------------
# Batch matching
# ---------------------------------------------------------------------------

async def semantic_match_batch(
    message: str,
    skill_summaries: list[dict[str, str]],
    llm_fn: LLMCallable | None = None,
    top_k: int = 3,
    threshold: float = 0.4,
) -> list[SkillTriggerResult]:
    """
    Return the top-K semantically matched skills above threshold.

    Useful for presenting multiple options to the user when the best
    match isn't clear-cut.

    Args:
        message: The user's input message.
        skill_summaries: Skill dicts with ``key`` and ``description``.
        llm_fn: LLM callable (see ``semantic_match``).
        top_k: Maximum number of matches to return.
        threshold: Minimum score for inclusion.

    Returns:
        List of ``SkillTriggerResult`` sorted by descending score.
    """
    if not skill_summaries or not message:
        return []

    # For batch, we run single match for now (could optimise with
    # a batch prompt in the future)
    result = await semantic_match(
        message=message,
        skill_summaries=skill_summaries,
        llm_fn=llm_fn,
        threshold=threshold,
    )

    if result:
        return [result]
    return []


# ---------------------------------------------------------------------------
# Default LLM resolution
# ---------------------------------------------------------------------------

def _get_default_llm() -> LLMCallable | None:
    """Attempt to import the default LLM client."""
    try:
        from realize_core.llm.claude_client import call_claude
        return call_claude
    except ImportError:
        pass

    try:
        from realize_core.llm.gemini_client import call_gemini
        return call_gemini
    except ImportError:
        pass

    return None


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_semantic_response(
    response: str,
    threshold: float,
) -> SkillTriggerResult | None:
    """
    Parse the LLM's JSON response into a ``SkillTriggerResult``.

    Handles:
    - Clean JSON responses
    - JSON wrapped in markdown code blocks
    - "NO_MATCH" text responses
    """
    if not response:
        return None

    text = response.strip()

    # Handle explicit no-match
    if "NO_MATCH" in text.upper():
        return None

    # Extract JSON from markdown code blocks if present
    json_match = _extract_json(text)
    if json_match is None:
        logger.debug("Could not extract JSON from semantic match response")
        return None

    try:
        data = json.loads(json_match)
    except json.JSONDecodeError as exc:
        logger.debug("Failed to parse semantic match JSON: %s", exc)
        return None

    skill_key = data.get("skill_key")
    score = float(data.get("score", 0.0))
    reason = str(data.get("reason", ""))

    if not skill_key or score < threshold:
        return None

    return SkillTriggerResult(
        skill_key=str(skill_key),
        score=score,
        trigger_method=TriggerMethod.SEMANTIC,
        confidence_reason=reason,
    )


def _extract_json(text: str) -> str | None:
    """Extract a JSON object from text, handling code blocks."""
    # Try direct JSON parse first
    text = text.strip()
    if text.startswith("{"):
        return text

    # Try extracting from ```json ... ``` blocks
    import re
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()

    # Try finding a JSON object anywhere in the text
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        return text[brace_start:brace_end + 1]

    return None
