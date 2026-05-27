"""
Runtime Registry — manages registered agent runtimes.

Handles registration, health polling, capability discovery,
and runtime selection for the Mission Engine.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from realize_core.runtimes.contract import (
    AgentRuntime,
    CapabilitySet,
    HealthStatus,
    Task,
)

logger = logging.getLogger(__name__)

# Health polling config
HEALTH_POLL_INTERVAL = 30  # seconds
HEALTH_FAIL_THRESHOLD = 3  # consecutive failures before marking degraded
HEALTH_OFFLINE_TIMEOUT = 300  # seconds before marking offline


class RuntimeEntry:
    """Internal registry entry for a registered runtime."""

    def __init__(self, runtime: AgentRuntime):
        self.runtime = runtime
        self.capabilities: CapabilitySet | None = None
        self.health: HealthStatus = HealthStatus(ready=False)
        self.consecutive_failures: int = 0
        self.registered_at: datetime = datetime.now()
        self.last_used: datetime | None = None
        self.invocation_count: int = 0
        self.total_cost_eur: float = 0.0
        self.status: str = "initializing"  # initializing, ready, degraded, offline

    @property
    def runtime_id(self) -> str:
        return self.runtime.runtime_id


class RuntimeRegistry:
    """
    Central registry for all agent runtimes in RealizeOS.

    The Mission Engine uses the registry to discover runtimes,
    check their health, and match tasks to the best runtime
    based on capabilities and cost.
    """

    def __init__(self):
        self._runtimes: dict[str, RuntimeEntry] = {}
        self._polling_task: asyncio.Task | None = None

    @property
    def runtime_ids(self) -> list[str]:
        """List all registered runtime IDs."""
        return list(self._runtimes.keys())

    @property
    def active_runtimes(self) -> list[str]:
        """List runtime IDs that are ready or degraded."""
        return [rid for rid, entry in self._runtimes.items() if entry.status in ("ready", "degraded")]

    def get(self, runtime_id: str) -> RuntimeEntry | None:
        """Get a runtime entry by ID."""
        return self._runtimes.get(runtime_id)

    async def register(self, runtime: AgentRuntime) -> bool:
        """
        Register a new runtime.

        Calls health_check() and capabilities() during registration.
        Returns True if registration succeeded.
        """
        rid = runtime.runtime_id

        if rid in self._runtimes:
            logger.warning(f"Runtime '{rid}' already registered, replacing")

        entry = RuntimeEntry(runtime)

        # Health check (must succeed within 5s)
        try:
            entry.health = await asyncio.wait_for(
                runtime.health_check(),
                timeout=5.0,
            )
        except (TimeoutError, Exception) as e:
            logger.error(f"Health check failed for runtime '{rid}': {e}")
            entry.health = HealthStatus(ready=False, error=str(e))
            entry.status = "offline"
            self._runtimes[rid] = entry
            return False

        # Capabilities
        try:
            entry.capabilities = runtime.capabilities()
        except Exception as e:
            logger.error(f"Capabilities check failed for runtime '{rid}': {e}")
            entry.capabilities = CapabilitySet()

        if entry.health.ready:
            entry.status = "ready"
            logger.info(
                f"Registered runtime '{rid}' v{runtime.version} ({len(entry.capabilities.capabilities)} capabilities)"
            )
        else:
            entry.status = "degraded" if entry.health.degraded else "offline"

        self._runtimes[rid] = entry
        return entry.health.ready

    async def deregister(self, runtime_id: str) -> None:
        """Remove a runtime from the registry."""
        entry = self._runtimes.pop(runtime_id, None)
        if entry:
            try:
                await entry.runtime.shutdown()
            except Exception as e:
                logger.warning(f"Shutdown error for '{runtime_id}': {e}")
            logger.info(f"Deregistered runtime '{runtime_id}'")

    async def health_check(self, runtime_id: str) -> HealthStatus:
        """Run a health check on a specific runtime."""
        entry = self._runtimes.get(runtime_id)
        if not entry:
            return HealthStatus(ready=False, error="Not registered")

        try:
            entry.health = await asyncio.wait_for(
                entry.runtime.health_check(),
                timeout=5.0,
            )
            entry.consecutive_failures = 0
            entry.status = "ready" if entry.health.ready else "degraded"
        except (TimeoutError, Exception) as e:
            entry.consecutive_failures += 1
            entry.health = HealthStatus(ready=False, error=str(e))

            if entry.consecutive_failures >= HEALTH_FAIL_THRESHOLD:
                entry.status = "offline"
            else:
                entry.status = "degraded"

        return entry.health

    def match_runtimes(self, task: Task) -> list[tuple[str, float]]:
        """
        Find runtimes that can handle a task, ranked by match score.

        Returns list of (runtime_id, score) sorted by score descending.
        """
        matches: list[tuple[str, float]] = []

        for rid, entry in self._runtimes.items():
            if entry.status not in ("ready", "degraded"):
                continue

            if entry.capabilities is None:
                continue

            score = self._compute_match_score(task, entry)
            if score > 0:
                matches.append((rid, score))

        # Sort by score descending, then by name for stability
        matches.sort(key=lambda x: (-x[1], x[0]))
        return matches

    def _compute_match_score(self, task: Task, entry: RuntimeEntry) -> float:
        """
        Compute how well a runtime matches a task.

        Scoring:
        - Required capabilities: 0 if any missing, +1.0 per matched
        - Preferred capabilities: +0.5 per matched
        - Language match: +0.5
        - Modality match: +0.5
        - Ready (vs degraded): +0.5
        - Cost preference: cheaper = higher score
        """
        caps = entry.capabilities
        if caps is None:
            return 0.0

        cap_names = {c.name: c for c in caps.capabilities}
        score = 0.0

        # Required capabilities — all must be present
        for req in task.required_capabilities:
            if req not in cap_names:
                return 0.0
            score += cap_names[req].confidence

        # Preferred capabilities
        for pref in task.preferred_capabilities:
            if pref in cap_names:
                score += 0.5 * cap_names[pref].confidence

        # Language match
        if task.language and task.language in caps.languages:
            score += 0.5

        # Modality match
        if task.modality in caps.modalities:
            score += 0.5

        # Health bonus
        if entry.status == "ready":
            score += 0.5

        # If no required/preferred were specified, give a base score
        if not task.required_capabilities and not task.preferred_capabilities:
            score = 1.0 + (0.5 if entry.status == "ready" else 0)

        return score

    def status_summary(self) -> list[dict]:
        """Get a summary of all registered runtimes and their status."""
        summary = []
        for rid, entry in self._runtimes.items():
            summary.append(
                {
                    "runtime_id": rid,
                    "display_name": entry.runtime.display_name,
                    "version": entry.runtime.version,
                    "status": entry.status,
                    "capabilities_count": len(entry.capabilities.capabilities) if entry.capabilities else 0,
                    "invocation_count": entry.invocation_count,
                    "total_cost_eur": entry.total_cost_eur,
                    "registered_at": entry.registered_at.isoformat(),
                    "last_used": entry.last_used.isoformat() if entry.last_used else None,
                    "health_error": entry.health.error,
                }
            )
        return summary
