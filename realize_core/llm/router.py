"""
Multi-LLM Router: Classifies task type and selects the optimal model.

Strategy:
- Tier 1 (cheap/free): Simple Q&A, summaries, routing classification
- Tier 2 (mid): Content creation, reasoning, financial analysis, tool use
- Tier 3 (premium): Complex strategy, cross-system coordination

V5 additions:
- Benchmark-based model selection via BenchmarkCache (cost-benefit scoring)
- LiteLLM fallback: 50+ providers available when primary providers fail
- Routing strategies: balanced, cost_optimized, quality_first, speed_first
- Rate limit enforcement (sliding window, configurable per minute)
- Cost limit enforcement ($X/hour cap with automatic rejection)
"""

import logging
import time
from collections import deque

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
            f"Rate limit exceeded: {len(_request_timestamps)}/{RATE_LIMIT_PER_MINUTE} "
            f"requests in the last 60s"
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
        logger.warning(
            f"Cost limit exceeded: ${hourly_cost:.4f} >= ${COST_LIMIT_PER_HOUR_USD:.2f}/hour"
        )
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


def classify_task(message: str, system_key: str = None) -> str:
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
    Check if quality feedback suggests a model override for this task type.
    Returns a model key if override warranted, None otherwise.

    Self-tuning: if users consistently give negative feedback on a task type,
    the system auto-upgrades to a more capable model.
    """
    try:
        from realize_core.memory.store import get_feedback_signals

        signals = get_feedback_signals(task_type, days=30)
        if not signals:
            return None

        positive = signals.get("positive", 0)
        negative = signals.get("negative", 0) + signals.get("correction", 0)
        resets = signals.get("reset", 0)

        # If many resets/negatives for simple tasks -> upgrade to tier 2
        if task_type == "simple" and (negative + resets * 2) > positive and (negative + resets) >= 3:
            logger.info(f"Self-tuning: upgrading {task_type} from tier1 to tier2 (neg={negative}, resets={resets})")
            return "claude_sonnet"

        # If content tasks have many negatives -> upgrade to tier 3
        if task_type == "content" and resets >= 3 and resets > positive:
            logger.info(f"Self-tuning: upgrading {task_type} from tier2 to tier3")
            return "claude_opus"

    except Exception:
        pass

    return None


def select_model(task_type: str) -> str:
    """
    Select the LLM model based on task type, with self-tuning from quality feedback.

    Returns:
        Model identifier string: "gemini_flash", "claude_sonnet", or "claude_opus"
    """
    # Check for quality-based overrides
    override = _get_quality_override(task_type)
    if override:
        return override

    model_map = {
        "simple": "gemini_flash",
        "content": "claude_sonnet",
        "reasoning": "claude_sonnet",
        "financial": "claude_sonnet",
        "complex": "claude_opus",
        "google": "claude_sonnet",  # Tool use requires Claude
        "web_research": "claude_sonnet",
        "web_action": "claude_sonnet",
    }
    return model_map.get(task_type, "gemini_flash")


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

    Uses the ProviderRegistry with full fallback chain — if the primary
    provider fails, walks the entire fallback chain trying each available
    provider until one succeeds.

    V5 additions:
    - use_benchmark=True enables benchmark-based model selection
    - LiteLLM provider as additional fallback (50+ providers)

    Args:
        system_prompt: Assembled system prompt
        messages: Conversation history
        task_type: Classified task type from classify_task()
        system_key: Venture key (for logging)
        max_retries: Max providers to try before giving up
        use_benchmark: If True, use benchmark-based cost-benefit scoring
        strategy: Routing strategy when use_benchmark=True

    Returns:
        LLM response text
    """
    # ── Rate & Cost limit enforcement ──────────────────────────────
    if not _check_rate_limit():
        return (
            "I'm currently handling too many requests. "
            "Please wait a moment and try again."
        )

    if not _check_cost_limit():
        return (
            "The hourly cost limit has been reached. "
            "Please wait or contact your administrator to adjust the limit."
        )

    # Optionally use benchmark-based selection
    if use_benchmark:
        benchmark_model = select_model_by_benchmark(task_type, strategy)
        if benchmark_model:
            result = await _try_litellm_completion(system_prompt, messages, benchmark_model)
            if result is not None:
                return result
            logger.info("Benchmark model failed, falling back to standard routing")

    model_key = select_model(task_type)
    logger.info(f"Routing to {model_key} for task_type={task_type}")

    # Try registry-based routing with full fallback chain
    try:
        from realize_core.llm.registry import get_registry

        registry = get_registry()
        provider = registry.get_provider(model_key)

        # Attempt 1: Primary provider
        if provider and provider.is_available():
            model_id = registry.resolve_model_id(model_key)
            try:
                response = await provider.complete(
                    system_prompt=system_prompt,
                    messages=messages,
                    model=model_id,
                )
                if response.ok:
                    _record_cost(response.cost_usd)
                    return response.text
                logger.warning(f"Provider {provider.name} error: {response.error}")
            except Exception as e:
                logger.warning(f"Provider {provider.name} exception: {e}")

        # Attempt 2+: Walk the full fallback chain
        primary_name = registry._model_map.get(model_key, "")
        tried = {primary_name} if primary_name else set()
        attempts = 0

        for fallback_name in registry._fallback_chain:
            if fallback_name in tried or attempts >= max_retries:
                break
            fb_provider = registry.get_provider_by_name(fallback_name)
            if not fb_provider or not fb_provider.is_available():
                continue

            tried.add(fallback_name)
            attempts += 1
            logger.info(f"Fallback attempt {attempts}: trying {fallback_name}")

            try:
                fb_response = await fb_provider.complete(
                    system_prompt=system_prompt,
                    messages=messages,
                )
                if fb_response.ok:
                    _record_cost(fb_response.cost_usd)
                    logger.info(f"Fallback succeeded with {fallback_name}")
                    return fb_response.text
                logger.warning(f"Fallback {fallback_name} error: {fb_response.error}")
            except Exception as e:
                logger.warning(f"Fallback {fallback_name} exception: {e}")

        # Attempt 3: Try LiteLLM as extended fallback (50+ providers)
        if "litellm" not in tried:
            litellm_result = await _try_litellm_completion(system_prompt, messages)
            if litellm_result is not None:
                logger.info("LiteLLM fallback succeeded")
                return litellm_result

    except Exception as e:
        logger.debug(f"Registry routing failed, falling back to direct calls: {e}")

    # Last resort: direct client import (backward compatibility)
    from realize_core.llm.claude_client import call_claude_opus, call_claude_sonnet
    from realize_core.llm.gemini_client import call_gemini_flash

    if model_key == "gemini_flash":
        return await call_gemini_flash(system_prompt, messages)
    elif model_key == "claude_sonnet":
        return await call_claude_sonnet(system_prompt, messages)
    elif model_key == "claude_opus":
        return await call_claude_opus(system_prompt, messages)
    else:
        return await call_gemini_flash(system_prompt, messages)


# Module-level LiteLLM provider singleton (avoids creating new instances per call)
_litellm_provider = None


def _get_litellm_provider():
    """Get or create the LiteLLM provider singleton."""
    global _litellm_provider
    if _litellm_provider is None:
        from realize_core.llm.litellm_provider import LiteLLMProvider
        _litellm_provider = LiteLLMProvider()
    return _litellm_provider


async def _try_litellm_completion(
    system_prompt: str,
    messages: list[dict],
    model: str | None = None,
) -> str | None:
    """
    Try a completion via the LiteLLM provider.

    Returns the response text on success, or None on failure.
    This is a soft fallback — callers can continue to other providers.
    """
    try:
        provider = _get_litellm_provider()
        if not provider.is_available():
            return None

        response = await provider.complete(
            system_prompt=system_prompt,
            messages=messages,
            model=model,
        )
        if response.ok:
            _record_cost(response.cost_usd)
            return response.text
        logger.warning(f"LiteLLM completion error: {response.error}")
        return None

    except Exception as e:
        logger.debug(f"LiteLLM not available: {e}")
        return None
