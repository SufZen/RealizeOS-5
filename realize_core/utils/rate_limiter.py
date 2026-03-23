"""
Rate limiter for RealizeOS.

Implements per-tenant rate limiting based on requests per minute
and cost per hour thresholds.
"""

import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter with per-tenant tracking."""

    def __init__(self, requests_per_minute: int = 30, cost_per_hour_usd: float = 5.0):
        self.requests_per_minute = requests_per_minute
        self.cost_per_hour_usd = cost_per_hour_usd
        self._request_timestamps: dict[str, list[float]] = defaultdict(list)
        self._cost_accumulator: dict[str, list[tuple[float, float]]] = defaultdict(list)

    def check_rate_limit(self, tenant_id: str = "default") -> bool:
        """
        Check if the tenant is within rate limits.

        Returns:
            True if allowed, False if rate limited.
        """
        now = time.time()
        window_start = now - 60  # 1-minute window

        # Clean old timestamps
        self._request_timestamps[tenant_id] = [ts for ts in self._request_timestamps[tenant_id] if ts > window_start]

        # Check request count
        if len(self._request_timestamps[tenant_id]) >= self.requests_per_minute:
            logger.warning(
                f"Rate limit exceeded for tenant {tenant_id}: "
                f"{len(self._request_timestamps[tenant_id])}/{self.requests_per_minute} per minute"
            )
            return False

        return True

    def record_request(self, tenant_id: str = "default"):
        """Record a request for rate limiting."""
        self._request_timestamps[tenant_id].append(time.time())

    def check_cost_limit(self, tenant_id: str = "default") -> bool:
        """
        Check if the tenant is within the hourly cost limit.

        Returns:
            True if allowed, False if cost limited.
        """
        now = time.time()
        hour_start = now - 3600  # 1-hour window

        # Clean old entries
        self._cost_accumulator[tenant_id] = [
            (ts, cost) for ts, cost in self._cost_accumulator[tenant_id] if ts > hour_start
        ]

        # Sum costs in the window
        total_cost = sum(cost for _, cost in self._cost_accumulator[tenant_id])

        if total_cost >= self.cost_per_hour_usd:
            logger.warning(
                f"Cost limit exceeded for tenant {tenant_id}: ${total_cost:.4f}/${self.cost_per_hour_usd} per hour"
            )
            return False

        return True

    def record_cost(self, cost_usd: float, tenant_id: str = "default"):
        """Record a cost for cost limiting."""
        self._cost_accumulator[tenant_id].append((time.time(), cost_usd))


# Global rate limiter instance
_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _limiter
    if _limiter is None:
        from realize_core.config import COST_LIMIT_PER_HOUR_USD, RATE_LIMIT_PER_MINUTE

        _limiter = RateLimiter(
            requests_per_minute=RATE_LIMIT_PER_MINUTE,
            cost_per_hour_usd=COST_LIMIT_PER_HOUR_USD,
        )
    return _limiter
