"""
LLM Configuration and Usage API routes.
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

#: Providers a user may name as primary or in the fallback order, and the canonical name of each.
_PROVIDER_NAMES = {
    "claude": "claude",
    "anthropic": "claude",
    "gemini": "gemini",
    "google": "gemini",
    "openai": "openai",
    "ollama": "ollama",
    "litellm": "litellm",
}
_TIER_KEYS = ("fast", "standard", "deep")
_BODY_KEYS = {"primary", "tiers", "fallback"}
#: A LiteLLM model string such as ``gemini/gemini-2.5-pro`` or ``ollama_chat/qwen3:8b``.
_MODEL_RE = re.compile(r"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.:\-]+)*$")
_MAX_MODEL_LEN = 200

_TASK_DESCRIPTIONS = {
    "simple": "Quick answers, FAQs, status checks",
    "content": "Writing, content creation, analysis",
    "reasoning": "Deep analysis, decision-making",
    "financial": "Financial questions and figures",
    "google": "Google Workspace tasks",
    "web_research": "Researching on the web",
    "web_action": "Acting on web pages",
    "complex": "Strategy, complex reasoning, multi-step",
}


def _routing_payload() -> dict[str, Any]:
    """Build the GET /llm/routing payload from the router and the live registry."""
    from realize_core.config import llm_fallback, llm_primary, llm_tier_model
    from realize_core.llm.registry import get_registry
    from realize_core.llm.router import routing_table

    table = routing_table()
    routing_rules: dict[str, dict[str, Any]] = {}
    tiers: dict[str, dict[str, Any]] = {}
    for tier, row in table.items():
        tiers[tier] = {"provider": row["provider"], "model": row["model"], "source": row["source"]}
        for task_type in row["task_types"]:
            routing_rules[task_type] = {
                "tier": tier,
                "provider": row["provider"],
                "model": row["model"],
                "description": _TASK_DESCRIPTIONS.get(task_type, ""),
            }

    providers: list[dict[str, Any]] = []
    primary = None
    fallback: list[str] = []
    try:
        registry = get_registry()
        primary = registry.primary_provider_name()
        fallback = registry.fallback_chain()
        for name, available in registry.list_all().items():
            provider = registry.get_provider_by_name(name)
            providers.append(
                {
                    "name": name,
                    "available": available,
                    "models": provider.list_models() if provider and available else [],
                    "model_errors": provider.model_errors() if provider else {},
                }
            )
    except Exception as exc:
        logger.debug("LLM provider lookup failed: %s", exc)

    return {
        "routing_rules": routing_rules,
        "tiers": tiers,
        "providers": providers,
        "primary": primary,
        "fallback": fallback,
        "settings": {
            "primary": llm_primary(),
            "tiers": {t: llm_tier_model(t) for t in _TIER_KEYS},
            "fallback": llm_fallback(),
        },
    }


@router.get("/llm/routing")
async def get_llm_routing():
    """Task routing rules, per-tier models, providers and the configured primary/fallback."""
    return _routing_payload()


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _validate_provider(value: Any, field: str) -> str:
    """Canonical provider name, or a 400 naming the bad value."""
    name = value.strip().lower() if isinstance(value, str) else ""
    if name not in _PROVIDER_NAMES:
        raise _bad(f"{field}: unknown provider {value!r}; expected one of {', '.join(sorted(_PROVIDER_NAMES))}")
    return name


def _validate_updates(body: dict[str, Any]) -> dict[str, str]:
    """Turn the PUT body into ``{ENV_KEY: value}`` or raise a 400. Writes nothing."""
    unknown = set(body) - _BODY_KEYS
    if unknown:
        raise _bad(f"Unknown field(s): {', '.join(sorted(unknown))}")
    updates: dict[str, str] = {}

    if "primary" in body:
        primary = body["primary"]
        updates["LLM_PRIMARY"] = "" if primary in ("", None) else _validate_provider(primary, "primary")

    if "tiers" in body:
        tiers = body["tiers"]
        if not isinstance(tiers, dict):
            raise _bad("tiers must be an object")
        unknown_tiers = set(tiers) - set(_TIER_KEYS)
        if unknown_tiers:
            raise _bad(f"Unknown tier(s): {', '.join(sorted(map(str, unknown_tiers)))}")
        for tier, model in tiers.items():
            model = "" if model is None else model
            if not isinstance(model, str):
                raise _bad(f"tiers.{tier} must be a string")
            model = model.strip()
            if model and (len(model) > _MAX_MODEL_LEN or not _MODEL_RE.fullmatch(model)):
                raise _bad(f"tiers.{tier}: invalid model string {model[:60]!r}")
            updates[f"LLM_MODEL_{tier.upper()}"] = model

    if "fallback" in body:
        fallback = body["fallback"]
        if not isinstance(fallback, list):
            raise _bad("fallback must be a list of provider names")
        names = [_validate_provider(v, "fallback") for v in fallback]
        canonical = [_PROVIDER_NAMES[n] for n in names]
        if len(set(canonical)) != len(canonical):
            raise _bad("fallback must not repeat a provider")
        updates["LLM_FALLBACK"] = ",".join(names)

    return updates


@router.put("/llm/routing")
async def update_llm_routing(body: dict[str, Any] = Body(...)):
    """Set the primary provider, per-tier models and fallback order; applies immediately.

    Values are stored in .env through Setup's writer, then the provider registry is
    rebuilt so the next request routes with the new settings (no restart).
    """
    from realize_core.llm.registry import get_registry, reset_registry

    from realize_api.routes.setup import _ALLOWED_ENV_KEYS, _has_line_break, _write_env_value

    updates = _validate_updates(body)
    for key, value in updates.items():
        if key not in _ALLOWED_ENV_KEYS:  # keep this route inside Setup's allow-list
            raise _bad(f"{key} is not configurable")
        if _has_line_break(value):  # incl. U+2028 etc.; checked before any key is written
            raise _bad(f"{key}: the value must not contain a line break")
    try:
        for key, value in updates.items():
            _write_env_value(key, value)
    except ValueError as e:  # a line break: _validate_updates should already have refused it
        raise _bad(str(e)) from None
    except Exception:
        logger.error("Failed to save LLM routing settings", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    reset_registry()
    get_registry()  # re-run auto-registration with the new environment
    return _routing_payload()


@router.get("/llm/usage")
async def get_llm_usage():
    """Get LLM usage statistics."""
    try:
        from realize_core.memory.store import get_usage_stats

        stats = get_usage_stats()
        return {"usage": stats}
    except Exception:
        logger.warning("LLM usage stats failed", exc_info=True)
        return {"usage": {}, "error": "Usage statistics unavailable"}
