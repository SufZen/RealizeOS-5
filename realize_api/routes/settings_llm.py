"""
LLM Configuration and Usage API routes.
"""

import logging

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/llm/routing")
async def get_llm_routing():
    """Get task classification rules and model assignments."""
    routing_rules = {
        "simple": {"model": "gemini_flash", "description": "Quick answers, FAQs, status checks"},
        "content": {"model": "claude_sonnet", "description": "Writing, content creation, analysis"},
        "complex": {"model": "claude_opus", "description": "Strategy, complex reasoning, multi-step"},
        "creative": {"model": "claude_sonnet", "description": "Creative writing, brainstorming"},
        "code": {"model": "claude_sonnet", "description": "Code generation, technical tasks"},
        "reasoning": {"model": "claude_opus", "description": "Deep analysis, decision-making"},
    }

    providers = []
    try:
        from realize_core.llm.registry import get_registry

        registry = get_registry()
        for name, provider in registry._providers.items():
            avail = provider.is_available()
            providers.append(
                {
                    "name": name,
                    "available": avail,
                    "models": provider.list_models() if avail else [],
                }
            )
    except Exception as exc:
        logger.debug("LLM provider lookup failed: %s", exc)

    return {"routing_rules": routing_rules, "providers": providers}


@router.get("/llm/usage")
async def get_llm_usage():
    """Get LLM usage statistics."""
    try:
        from realize_core.memory.store import get_usage_stats

        stats = get_usage_stats()
        return {"usage": stats}
    except Exception as e:
        return {"usage": {}, "error": str(e)}
