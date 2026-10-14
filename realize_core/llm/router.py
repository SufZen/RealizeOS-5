"""
Multi-LLM Router: Classifies task type and routes it to a tier of any provider.

Tiers (provider-neutral):
- fast: Simple Q&A, summaries, routing classification
- standard: Content creation, reasoning, financial analysis, tool use
- deep: Complex strategy, cross-system coordination

Each tier resolves to (provider, model): ``LLM_MODEL_FAST|STANDARD|DEEP`` (a
LiteLLM model string) when set, else the primary provider's own model for that
tier (``tier_models`` on the provider class). On failure the registry's
fallback chain is walked, each provider using its own model for the same tier.

Also:
- Benchmark-based model selection via BenchmarkCache (cost-benefit scoring)
- Routing strategies: balanced, cost_optimized, quality_first, speed_first
- Rate limit enforcement (sliding window, configurable per minute)
- Cost limit enforcement ($X/hour cap with automatic rejection)
"""

import logging
import time
from collections import deque

from realize_core.llm.base_provider import STOP_ERROR, BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate & Cost Limit Tracking (sliding window)
# ---------------------------------------------------------------------------

# Sliding window of request timestamps for rate limiting
_request_timestamps: deque[float] = deque()

# Sliding window of (timestamp, cost_usd) for cost tracking
_cost_window: deque[tuple[float, float]] = deque()


def _check_rate_limit() -> bool:
    """Check if we're within the rate limit. Returns True if request is allowed."""
    from realize_core.config import RATE_LIMIT_PER_MINUTE

    now = time.time()
    cutoff = now - 60.0

    # Evict old entries
    while _request_timestamps and _request_timestamps[0] < cutoff:
        _request_timestamps.popleft()

    if len(_request_timestamps) >= RATE_LIMIT_PER_MINUTE:
        logger.warning(
            f"Rate limit exceeded: {len(_request_timestamps)}/{RATE_LIMIT_PER_MINUTE} requests in the last 60s"
        )
        return False

    _request_timestamps.append(now)
    return True


def _check_cost_limit() -> bool:
    """Check if we're within the hourly cost limit. Returns True if request is allowed."""
    from realize_core.config import COST_LIMIT_PER_HOUR_USD

    now = time.time()
    cutoff = now - 3600.0

    # Evict old entries
    while _cost_window and _cost_window[0][0] < cutoff:
        _cost_window.popleft()

    hourly_cost = sum(cost for _, cost in _cost_window)
    if hourly_cost >= COST_LIMIT_PER_HOUR_USD:
        logger.warning(f"Cost limit exceeded: ${hourly_cost:.4f} >= ${COST_LIMIT_PER_HOUR_USD:.2f}/hour")
        return False

    return True


def _record_cost(cost_usd: float) -> None:
    """Record a cost entry for the hourly cost tracker."""
    if cost_usd > 0:
        _cost_window.append((time.time(), cost_usd))


def get_hourly_cost() -> float:
    """Get the total cost in the last hour (for dashboard reporting)."""
    now = time.time()
    cutoff = now - 3600.0
    while _cost_window and _cost_window[0][0] < cutoff:
        _cost_window.popleft()
    return sum(cost for _, cost in _cost_window)


def get_rate_count() -> int:
    """Get the number of requests in the last minute (for dashboard reporting)."""
    now = time.time()
    cutoff = now - 60.0
    while _request_timestamps and _request_timestamps[0] < cutoff:
        _request_timestamps.popleft()
    return len(_request_timestamps)


# Keywords that signal each task complexity level
COMPLEX_KEYWORDS = {
    "cross-system",
    "multi-system",
    "strategic analysis",
    "portfolio review",
    "ecosystem",
    "all ventures",
    "all systems",
}

FINANCIAL_KEYWORDS = {
    "deal",
    "roi",
    "irr",
    "investment",
    "financial",
    "budget",
    "capex",
    "revenue",
    "break-even",
    "cash flow",
    "modeling",
    "underwriting",
    "valuation",
    "invoice",
    "payment",
    "accounting",
    "vat",
    "tax",
    "variance",
}

REASONING_KEYWORDS = {
    "analyze",
    "evaluate",
    "compare",
    "assess",
    "contract",
    "draft",
    "legal",
    "compliance",
    "licensing",
    "permit",
    "strategy",
    "architecture",
    "sprint plan",
    "design",
    "sop",
}

CONTENT_KEYWORDS = {
    "write",
    "blog",
    "post",
    "linkedin",
    "newsletter",
    "article",
    "content",
    "copy",
    "headline",
    "caption",
    "thread",
}

SIMPLE_KEYWORDS = {
    "what is",
    "tell me",
    "explain",
    "summary",
    "summarize",
    "list",
    "show",
    "status",
    "help",
    "how does",
    "define",
    "remind",
    "remember",
    "feedback",
}

GOOGLE_KEYWORDS = {
    "email",
    "emails",
    "gmail",
    "send email",
    "draft email",
    "inbox",
    "mail",
    "unread",
    "send to my email",
    "email me",
    "calendar",
    "schedule",
    "meeting",
    "event",
    "appointment",
    "free time",
    "drive",
    "google drive",
    "google doc",
    "create doc",
    "save to drive",
    "create document",
}

WEB_RESEARCH_KEYWORDS = {
    "search",
    "find online",
    "look up",
    "lookup",
    "research",
    "latest news",
    "check online",
    "find me",
    "browse",
    "website",
    "web page",
    "url",
    "competitor",
    "market data",
    "search the web",
    "find information",
}

WEB_ACTION_KEYWORDS = {
    "post on linkedin",
    "publish online",
    "submit form",
    "fill out",
    "sign up on",
    "register on",
    "book online",
    "log in to",
    "navigate to",
    "go to the site",
    "open the page",
    "fill the form",
    "download from",
}


def classify_task(message: str, system_key: str | None = None) -> str:
    """
    Classify a user message into a task type for model selection.

    Args:
        message: The user's message text
        system_key: The target system key (optional, for system-specific defaults)

    Returns:
        Task type string: "simple", "content", "reasoning", "financial",
                          "complex", "google", "web_research", "web_action"
    """
    msg_lower = message.lower()

    # Check for Google Workspace tasks FIRST (highest priority for tool_use routing)
    if any(kw in msg_lower for kw in GOOGLE_KEYWORDS):
        return "google"

    # Check for web action tasks (browser automation needed)
    if any(kw in msg_lower for kw in WEB_ACTION_KEYWORDS):
        return "web_action"

    # Check for web research tasks (search + fetch)
    if any(kw in msg_lower for kw in WEB_RESEARCH_KEYWORDS):
        return "web_research"

    # Check for complex cross-system indicators
    if any(kw in msg_lower for kw in COMPLEX_KEYWORDS):
        return "complex"

    # Check for financial/deal tasks
    if any(kw in msg_lower for kw in FINANCIAL_KEYWORDS):
        return "financial"

    # Check for reasoning-heavy tasks
    if any(kw in msg_lower for kw in REASONING_KEYWORDS):
        return "reasoning"

    # Check for content creation
    if any(kw in msg_lower for kw in CONTENT_KEYWORDS):
        return "content"

    # Check for simple Q&A
    if any(kw in msg_lower for kw in SIMPLE_KEYWORDS):
        return "simple"

    # Default: use cheap model for unclassified
    return "simple"


def _get_quality_override(task_type: str) -> str | None:
    """
    Check if quality feedback suggests a tier override for this task type.
    Returns a tier ("standard" / "deep") if an override is warranted, None otherwise.

    Self-tuning: if users consistently give negative feedback on a task type,
    the system auto-upgrades it to a more capable tier.
    """
    try:
        from realize_core.memory.store import get_feedback_signals

        signals = get_feedback_signals(task_type, days=30)
        if not signals:
            return None

        positive = signals.get("positive", 0)
        negative = signals.get("negative", 0) + signals.get("correction", 0)
        resets = signals.get("reset", 0)

        # If many resets/negatives for simple tasks -> upgrade to the standard tier
        if task_type == "simple" and (negative + resets * 2) > positive and (negative + resets) >= 3:
            logger.info(f"Self-tuning: upgrading {task_type} from fast to standard (neg={negative}, resets={resets})")
            return "standard"

        # If content tasks have many negatives -> upgrade to the deep tier
        if task_type == "content" and resets >= 3 and resets > positive:
            logger.info(f"Self-tuning: upgrading {task_type} from standard to deep")
            return "deep"

    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Tiers
# ---------------------------------------------------------------------------

TIERS = ("fast", "standard", "deep")
DEFAULT_TIER = "fast"

# Task type -> tier. Unlisted task types use DEFAULT_TIER.
TASK_TIERS = {
    "simple": "fast",
    "content": "standard",
    "reasoning": "standard",
    "financial": "standard",
    "google": "standard",
    "web_research": "standard",
    "web_action": "standard",
    "complex": "deep",
}

# LiteLLM model-string prefix -> registered provider name (anything else -> "litellm").
# LiteLLM prefix -> (provider, the prefix that provider's own model ids carry).
_PREFIX_PROVIDERS = (
    ("anthropic/", "claude", ""),  # native Claude ids are bare
    ("gemini/", "gemini", "gemini/"),
    ("openai/", "openai", "openai/"),
    ("ollama_chat/", "ollama", "ollama_chat/"),
    ("ollama/", "ollama", "ollama_chat/"),
)

RATE_LIMIT_TEXT = "I'm currently handling too many requests. Please wait a moment and try again."
COST_LIMIT_TEXT = (
    "The hourly cost limit has been reached. Please wait or contact your administrator to adjust the limit."
)
ALL_FAILED_TEXT = "An error occurred processing your request. Please try again."


def select_model(task_type: str) -> str:
    """
    Select the routing tier for a task type, with self-tuning from quality feedback.

    Returns:
        Tier name: "fast", "standard" or "deep"
    """
    override = _get_quality_override(task_type)
    if override:
        return override
    return TASK_TIERS.get(task_type, DEFAULT_TIER)


def _check_tier(tier: str) -> None:
    if tier not in TIERS:
        raise ValueError(f"Unknown LLM tier {tier!r}; expected one of {', '.join(TIERS)}")


def parse_model_string(model: str) -> tuple[str, str]:
    """Map a LiteLLM model string to (provider name, model id for that provider).

    ``anthropic/`` is stripped for the native Claude provider and ``ollama/``
    becomes ``ollama_chat/``; other prefixes are kept (the adapters accept them).
    Unknown prefixes go to the generic ``litellm`` provider unchanged.
    """
    for prefix, name, native in _PREFIX_PROVIDERS:
        if model.startswith(prefix):
            return name, f"{native}{model[len(prefix) :]}"
    return "litellm", model


def _resolve_model(registry, model: str) -> tuple[str, str | None]:
    """(provider, model id) for an explicit model: a registry key, a LiteLLM string or a listed id."""
    provider = registry.get_provider(model)
    if provider:
        return provider.name, registry.resolve_model_id(model) or provider.default_model_id()
    if "/" not in model:
        for name in registry.list_all():
            candidate = registry.get_provider_by_name(name)
            try:
                if candidate and any(m.model_id == model for m in candidate.list_models()):
                    return name, model
            except Exception as e:
                logger.debug(f"Could not list models of {name}: {e}")
    return parse_model_string(model)


def _tier_model(registry, provider: BaseLLMProvider, tier: str) -> str | None:
    """The model ``provider`` uses for ``tier`` (its ``tier_models`` entry, else its default)."""
    key = provider.tier_models.get(tier)
    model_id = registry.resolve_model_id(key) if key else None
    return model_id or provider.default_model_id()


def _resolve_tier(registry, tier: str) -> tuple[str | None, str | None]:
    _check_tier(tier)
    from realize_core.config import llm_tier_model

    override = llm_tier_model(tier)
    if override:
        return _resolve_model(registry, override)
    name = registry.primary_provider_name() or next(iter(registry.fallback_chain()), None)
    provider = registry.get_provider_by_name(name) if name else None
    if not provider:
        return None, None
    return name, _tier_model(registry, provider, tier)


def resolve_tier(tier: str) -> tuple[str | None, str | None]:
    """Resolve a tier to (provider name, model id).

    ``LLM_MODEL_<TIER>`` wins when set (a LiteLLM model string such as
    ``gemini/gemini-2.5-pro``; registry keys like ``claude_opus`` also work).
    Otherwise the primary provider's own model for the tier is used.
    (None, None) when no provider is registered.
    """
    from realize_core.llm.registry import get_registry

    return _resolve_tier(get_registry(), tier)


def routing_table() -> dict:
    """Per tier: the task types routed to it and the resolved provider/model.

    Shape: ``{tier: {"task_types": [...], "provider": str | None,
    "model": str | None, "source": "env" | "default"}}`` for each of TIERS.
    Unlisted task types use DEFAULT_TIER.
    """
    from realize_core.config import llm_tier_model

    table = {}
    for tier in TIERS:
        provider, model = resolve_tier(tier)
        table[tier] = {
            "task_types": sorted(t for t, v in TASK_TIERS.items() if v == tier),
            "provider": provider,
            "model": model,
            "source": "env" if llm_tier_model(tier) else "default",
        }
    return table


def select_model_by_benchmark(
    task_type: str,
    strategy: str = "balanced",
    available_models: set[str] | None = None,
) -> str | None:
    """
    Select the optimal model using benchmark-based cost-benefit scoring.

    This is an alternative to the keyword+tier model selection. It uses
    multi-dimensional scoring (quality, cost, speed, task-fit) with
    configurable strategy weights to pick the best model.

    Args:
        task_type: Classified task type from classify_task()
        strategy: One of "balanced", "cost_optimized", "quality_first", "speed_first"
        available_models: Optional set of model_ids to consider

    Returns:
        Best model_id string, or None if benchmark cache is unavailable.
    """
    try:
        from realize_core.llm.benchmark_cache import get_benchmark_cache

        cache = get_benchmark_cache()
        best = cache.get_best_model(task_type, strategy, available_models)
        if best:
            logger.info(f"Benchmark routing: {best} for task_type={task_type} strategy={strategy}")
        return best
    except Exception as e:
        logger.debug(f"Benchmark-based selection unavailable: {e}")
        return None


# ---------------------------------------------------------------------------
# Completion routing
# ---------------------------------------------------------------------------


def _failure(text: str, error: str) -> LLMResponse:
    return LLMResponse(text=text, error=error, stop_reason=STOP_ERROR)


async def _call_provider(
    provider: BaseLLMProvider,
    model_id: str | None,
    system_prompt: str,
    messages: list[dict],
    extra: dict,
) -> LLMResponse | None:
    """One completion attempt. None when the model is known to be unusable."""
    if not provider.is_model_usable(model_id or ""):
        logger.info(f"Skipping {provider.name}: model {model_id} is unusable")
        return None
    try:
        return await provider.complete(system_prompt=system_prompt, messages=messages, model=model_id, **extra)
    except Exception as e:
        logger.warning(f"Provider {provider.name} exception: {e}")
        return LLMResponse(text="", model=model_id or "", provider=provider.name, error=str(e), stop_reason=STOP_ERROR)


async def route_completion(
    system_prompt: str,
    messages: list[dict],
    *,
    task_type: str | None = None,
    tier: str | None = None,
    model: str | None = None,
    system_key: str = "",
    response_schema: dict | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    max_retries: int = 3,
) -> LLMResponse:
    """
    Route a completion to the right provider and model, with fallback.

    The first attempt uses ``model`` (a LiteLLM model string or a registry key
    such as ``claude_opus``) when given, else ``tier``, else the tier of
    ``task_type`` (see ``select_model``). If it fails, the registry's fallback
    chain is walked (at most ``max_retries`` more providers), each provider
    using its own model for the same tier. A refusal is final and not retried.

    ``response_schema``, ``max_tokens`` and ``temperature`` are passed to the
    provider only when set.

    Returns:
        The provider's LLMResponse, or an error response (``ok`` False) whose
        text is a user-facing message when limits apply or every attempt failed.
    """
    if not _check_rate_limit():
        return _failure(RATE_LIMIT_TEXT, "rate_limited")
    if not _check_cost_limit():
        return _failure(COST_LIMIT_TEXT, "cost_limited")

    from realize_core.llm.registry import get_registry

    registry = get_registry()
    if tier is None:
        tier = select_model(task_type) if task_type else DEFAULT_TIER
    _check_tier(tier)

    name, model_id = _resolve_model(registry, model) if model else _resolve_tier(registry, tier)
    logger.info(f"Routing to {name}/{model_id} (tier={tier}, task_type={task_type}, system={system_key or '-'})")

    extra = {
        k: v
        for k, v in (("max_tokens", max_tokens), ("temperature", temperature), ("response_schema", response_schema))
        if v is not None
    }
    last_error = "no LLM provider available"

    def _accept(response: LLMResponse | None) -> bool:
        nonlocal last_error
        if response is None:
            return False
        if response.ok or response.refused:
            # A refusal is final: retrying it elsewhere would bypass the model's safety decision.
            _record_cost(response.cost_usd)
            return True
        logger.warning(f"Provider {response.provider or '?'} error: {response.error}")
        last_error = response.error or last_error
        return False

    tried: set[str] = set()
    if name:
        tried.add(name)
        provider = registry.get_provider_by_name(name)
        if provider and provider.is_available():
            response = await _call_provider(provider, model_id, system_prompt, messages, extra)
            if response is not None and _accept(response):
                return response

    attempts = 0
    for fallback_name in registry.fallback_chain():
        if attempts >= max_retries:
            break
        if fallback_name in tried:
            continue
        provider = registry.get_provider_by_name(fallback_name)
        if not provider or not provider.is_available():
            continue
        tried.add(fallback_name)
        attempts += 1
        logger.info(f"Fallback attempt {attempts}: trying {fallback_name}")
        response = await _call_provider(provider, _tier_model(registry, provider, tier), system_prompt, messages, extra)
        if response is not None and _accept(response):
            logger.info(f"Fallback answered with {fallback_name}")
            return response

    logger.error(f"All LLM providers failed (tier={tier}): {last_error}")
    return _failure(ALL_FAILED_TEXT, last_error)


def text_llm(tier: str, response_schema: dict | None = None):
    """An ``async fn(system_prompt, messages) -> str`` routed at ``tier``.

    For callers that take a plain text LLM callable. Returns None when no
    provider is available; the callable raises RuntimeError when every
    provider fails (or the model refuses).
    """
    from realize_core.llm.registry import get_registry

    _check_tier(tier)
    if not get_registry().list_available():
        return None

    async def _call(system_prompt: str, messages: list[dict], **_ignored) -> str:
        response = await route_completion(system_prompt, messages, tier=tier, response_schema=response_schema)
        if not response.ok:
            raise RuntimeError(response.error or "LLM call failed")
        return response.text

    return _call


async def route_to_llm(
    system_prompt: str,
    messages: list[dict],
    task_type: str,
    system_key: str = "",
    max_retries: int = 3,
    use_benchmark: bool = False,
    strategy: str = "balanced",
) -> str:
    """
    Route the request to the appropriate LLM based on task type.

    Thin text wrapper over ``route_completion``.

    Args:
        system_prompt: Assembled system prompt
        messages: Conversation history
        task_type: Classified task type from classify_task()
        system_key: Venture key (for logging)
        max_retries: Max fallback providers to try before giving up
        use_benchmark: If True, pick the model by benchmark cost-benefit scoring
        strategy: Routing strategy when use_benchmark=True

    Returns:
        LLM response text (a user-facing error message when every provider failed)
    """
    model = select_model_by_benchmark(task_type, strategy) if use_benchmark else None
    response = await route_completion(
        system_prompt,
        messages,
        task_type=task_type,
        model=model,
        system_key=system_key,
        max_retries=max_retries,
    )
    return response.text
