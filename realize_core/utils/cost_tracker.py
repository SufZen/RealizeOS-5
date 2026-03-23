"""
LLM usage and cost tracking for RealizeOS.

Tracks API calls, token counts, and costs per tenant and model.
Used for billing, analytics, and rate limiting.
"""

import logging

logger = logging.getLogger(__name__)


def log_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    tenant_id: str = "default",
    task_type: str = "",
    system_key: str = "",
) -> None:
    """
    Log an LLM API call for cost tracking.

    Args:
        model: Model identifier (e.g., "claude-sonnet-4-6-20260217")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cost_usd: Estimated cost in USD
        tenant_id: Tenant identifier for billing isolation
        task_type: Task classification (simple, content, reasoning, etc.)
        system_key: Which system the request was for
    """
    try:
        from realize_core.memory.store import log_llm_usage

        log_llm_usage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            tenant_id=tenant_id,
        )
    except Exception as e:
        logger.debug(f"Cost tracking failed: {e}")


def get_usage_summary(tenant_id: str = "default", days: int = 30) -> dict:
    """
    Get usage summary for a tenant over the specified period.

    Returns:
        Dictionary with total_calls, total_tokens, total_cost, by_model breakdown.
    """
    try:
        from realize_core.memory.store import get_usage_stats

        return get_usage_stats(tenant_id=tenant_id, days=days)
    except Exception:
        return {
            "total_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "by_model": {},
        }
