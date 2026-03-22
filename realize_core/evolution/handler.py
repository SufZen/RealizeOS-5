"""
Evolution Handler — Detects and orchestrates KB evolution from conversations.

When a user's message implies they want to save, update, or evolve the system,
this handler coordinates the analysis, builds a confirmation preview,
and executes the write after user approval.
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

# Fast keyword-based pre-filter (avoid LLM call for every message)
EVOLUTION_TRIGGERS = re.compile(
    r'(?:'
    r'save\s+(?:this|that|it)|'
    r'write\s+(?:this|that|it)\s+(?:to|in|down)|'
    r'add\s+(?:this|a\s+new|an?)\s+(?:sop|process|skill|note|rule|method)|'
    r'create\s+(?:a\s+new|an?)\s+(?:sop|process|document|file|note|skill|template)|'
    r'update\s+(?:the\s+)?(?:state\s*map|agent|skill|sop|process|definition)|'
    r'(?:the\s+)?(?:agent|bot|system)\s+should\s+(?:also|now|start|stop|learn|know|handle)|'
    r'remember\s+(?:this|that)\s+(?:as|for)|'
    r'evolve|improve\s+the\s+(?:system|agent)|'
    r'add\s+(?:this\s+)?(?:to|as)\s+(?:the\s+)?(?:kb|knowledge|brain|memory)|'
    r'save\s+(?:to|in)\s+(?:the\s+)?(?:kb|knowledge|brain)|'
    r'log\s+(?:this|that)\s+(?:decision|change|update)|'
    r'document\s+this|'
    r'make\s+(?:this|it)\s+(?:a\s+)?(?:standard|permanent|official|template)'
    r')',
    re.IGNORECASE,
)

STRONG_SIGNALS = re.compile(
    r'(?:'
    r'save\s+(?:this|it)\s+(?:to|in|as)|'
    r'create\s+(?:a\s+)?new\s+(?:sop|agent|skill)|'
    r'update\s+the\s+(?:state\s*map|agent\s+definition)|'
    r'add\s+(?:this\s+)?skill\s+to'
    r')',
    re.IGNORECASE,
)


def has_evolution_intent(message: str) -> bool:
    """Quick check if a message might contain an evolution intent."""
    return bool(EVOLUTION_TRIGGERS.search(message))


def has_strong_evolution_intent(message: str) -> bool:
    """Check for strong evolution signals (explicit requests)."""
    return bool(STRONG_SIGNALS.search(message))


EVOLUTION_ANALYSIS_PROMPT = """You are an evolution analyzer for a knowledge management system.
Your job is to determine if a user message is requesting a change to the knowledge base or agent system.

ANALYZE the user message and determine:
1. Is this an evolution request?
2. What action type? One of: create_file, update_file, update_agent, update_state_map, add_skill, none
3. What system key?
4. Where specifically? (subfolder path or file path)
5. What content should be written?
6. A clear title/name for the change

IMPORTANT:
- Only classify as evolution if the user is EXPLICITLY asking to save, create, update, or evolve
- Normal questions or requests for content are NOT evolution requests
- If "none", respond with just: {{"action": "none"}}

Respond with ONLY valid JSON (no markdown):
{{
    "action": "create_file|update_file|update_agent|update_state_map|add_skill|none",
    "system_key": "system_key_here",
    "subfolder": "B-brain/SOPs",
    "title": "Title of new content",
    "content": "The content to write (full markdown)",
    "reason": "Brief explanation of what will happen"
}}
"""


async def analyze_evolution_intent(
    message: str,
    system_key: str,
    conversation_context: str = "",
) -> dict | None:
    """
    Use LLM to analyze if a message is an evolution request.

    Returns evolution action dict, or None if not an evolution request.
    """
    from realize_core.llm.gemini_client import call_gemini

    system_prompt = EVOLUTION_ANALYSIS_PROMPT
    user_content = f"Current system: {system_key}\n\n"
    if conversation_context:
        user_content += f"Recent conversation:\n{conversation_context}\n\n"
    user_content += f"User message: {message}"

    try:
        response = await call_gemini(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        result = _parse_json_response(response)
        if not result or result.get("action") == "none":
            return None
        logger.info(f"Evolution intent detected: {result.get('action')}")
        return result
    except Exception as e:
        logger.error(f"Evolution analysis failed: {e}", exc_info=True)
        return None


def _parse_json_response(text: str) -> dict | None:
    """Extract JSON from an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None
