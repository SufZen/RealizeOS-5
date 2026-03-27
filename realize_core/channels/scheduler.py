"""
Cron Scheduler: Executes scheduled tasks at defined intervals.

Supports:
- YAML-defined scheduled jobs
- Cron-expression-like scheduling (simplified)
- Task routing through the channel system
- Circuit breaker for repeatedly failing jobs
- State persistence across restarts
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Maximum consecutive failures before auto-disabling a job
_MAX_CONSECUTIVE_FAILURES = 5


@dataclass
class ScheduledJob:
    """A job scheduled to run at regular intervals."""

    name: str
    system_key: str
    message: str  # The prompt/command to execute
    interval_seconds: int  # How often to run
    enabled: bool = True
    last_run: float = 0.0
    run_count: int = 0
    consecutive_failures: int = 0
    last_error: str = ""
    user_id: str = "scheduler"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_due(self) -> bool:
        """Check if the job is due to run."""
        if not self.enabled:
            return False
        return (time.time() - self.last_run) >= self.interval_seconds

    @property
    def next_run_in(self) -> float:
        """Seconds until next run."""
        elapsed = time.time() - self.last_run
        remaining = self.interval_seconds - elapsed
        return max(0, remaining)


# ---------------------------------------------------------------------------
# Interval parsing helpers
# ---------------------------------------------------------------------------

_INTERVAL_SHORTCUTS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "daily": 86400,
    "weekly": 604800,
}


def parse_interval(interval: str) -> int:
    """
    Parse a human-friendly interval string into seconds.

    Supports: "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "daily", "weekly"
    Also accepts raw seconds as a string (e.g., "300").
    """
    interval = interval.strip().lower()
    if interval in _INTERVAL_SHORTCUTS:
        return _INTERVAL_SHORTCUTS[interval]
    try:
        return int(interval)
    except ValueError:
        logger.warning(f"Unknown interval '{interval}', defaulting to 1h")
        return 3600


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class CronScheduler:
    """
    Simple interval-based scheduler for RealizeOS.

    Runs jobs at defined intervals, routing them through the engine
    as if a user had sent the message.

    Features:
    - Circuit breaker: auto-disables jobs after consecutive failures
    - State persistence: save/load job state for restart recovery
    """

    def __init__(self):
        self._jobs: dict[str, ScheduledJob] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._handler: Callable[..., Coroutine] | None = None

    def set_handler(self, handler: Callable[..., Coroutine]):
        """
        Set the message handler function.

        The handler should accept (user_id, text, system_key, channel) and
        return a response string. Typically this is engine.process_message.
        """
        self._handler = handler

    def add_job(self, job: ScheduledJob):
        """Add a scheduled job."""
        self._jobs[job.name] = job
        logger.info(f"Scheduled job '{job.name}': every {job.interval_seconds}s (enabled={job.enabled})")

    def remove_job(self, name: str) -> bool:
        """Remove a scheduled job."""
        return self._jobs.pop(name, None) is not None

    def enable_job(self, name: str) -> bool:
        """Enable a job and reset its failure counter."""
        job = self._jobs.get(name)
        if job:
            job.enabled = True
            job.consecutive_failures = 0
            job.last_error = ""
            return True
        return False

    def disable_job(self, name: str) -> bool:
        """Disable a job without removing it."""
        job = self._jobs.get(name)
        if job:
            job.enabled = False
            return True
        return False

    def load_from_yaml(self, yaml_path: str | Path):
        """
        Load scheduled jobs from a YAML config file.

        Format:
        ```yaml
        schedules:
          weekly_review:
            system_key: my-business
            message: "Run my weekly review"
            interval: weekly
            enabled: true

          daily_status:
            system_key: my-business
            message: "Generate a daily status summary"
            interval: daily
            enabled: true
        ```
        """
        path = Path(yaml_path)
        if not path.exists():
            logger.info(f"Schedule config not found: {path}")
            return

        try:
            import yaml
        except ImportError:
            logger.warning("pyyaml not installed, cannot load schedules")
            return

        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        for name, cfg in config.get("schedules", {}).items():
            interval_str = cfg.get("interval", "daily")
            self.add_job(
                ScheduledJob(
                    name=name,
                    system_key=cfg.get("system_key", ""),
                    message=cfg.get("message", ""),
                    interval_seconds=parse_interval(interval_str),
                    enabled=cfg.get("enabled", True),
                    user_id=cfg.get("user_id", "scheduler"),
                    metadata=cfg.get("metadata", {}),
                )
            )

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Scheduler started with {len(self._jobs)} jobs")

    async def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Scheduler stopped")

    async def _run_loop(self):
        """Main scheduler loop — checks and executes due jobs."""
        while self._running:
            for job in list(self._jobs.values()):
                if job.is_due:
                    await self._execute_job(job)

            # Sleep for a short interval to check again
            await asyncio.sleep(10)

    async def _execute_job(self, job: ScheduledJob):
        """Execute a single scheduled job with circuit breaker logic."""
        if not self._handler:
            logger.warning(f"No handler set, skipping job '{job.name}'")
            return

        job.last_run = time.time()
        job.run_count += 1
        logger.info(f"Executing scheduled job '{job.name}' (run #{job.run_count})")

        try:
            await self._handler(
                user_id=job.user_id,
                text=job.message,
                system_key=job.system_key,
                channel="scheduler",
            )
            # Reset failure counter on success
            job.consecutive_failures = 0
            job.last_error = ""
        except Exception as e:
            job.consecutive_failures += 1
            job.last_error = str(e)[:200]
            logger.error(
                f"Scheduled job '{job.name}' failed "
                f"({job.consecutive_failures}/{_MAX_CONSECUTIVE_FAILURES}): {e}",
                exc_info=True,
            )

            # Circuit breaker: auto-disable after too many failures
            if job.consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                job.enabled = False
                logger.error(
                    f"Circuit breaker: auto-disabled job '{job.name}' "
                    f"after {_MAX_CONSECUTIVE_FAILURES} consecutive failures"
                )

    # -----------------------------------------------------------------------
    # State persistence
    # -----------------------------------------------------------------------

    def save_state(self, path: str | Path):
        """Save scheduler state to a JSON file for restart recovery."""
        state = {}
        for name, job in self._jobs.items():
            state[name] = {
                "last_run": job.last_run,
                "run_count": job.run_count,
                "consecutive_failures": job.consecutive_failures,
                "last_error": job.last_error,
                "enabled": job.enabled,
            }

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2), encoding="utf-8")
        logger.info(f"Scheduler state saved to {path}")

    def load_state(self, path: str | Path):
        """Load scheduler state from a JSON file."""
        p = Path(path)
        if not p.exists():
            return

        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load scheduler state: {e}")
            return

        for name, data in state.items():
            job = self._jobs.get(name)
            if job:
                job.last_run = data.get("last_run", 0.0)
                job.run_count = data.get("run_count", 0)
                job.consecutive_failures = data.get("consecutive_failures", 0)
                job.last_error = data.get("last_error", "")
                # Only restore disabled state from persistence (don't re-enable)
                if not data.get("enabled", True):
                    job.enabled = False

        logger.info(f"Scheduler state loaded from {path}")

    # -----------------------------------------------------------------------
    # Health & status
    # -----------------------------------------------------------------------

    @property
    def job_count(self) -> int:
        return len(self._jobs)

    def health_check(self) -> dict:
        """Return scheduler health status."""
        failing_jobs = [
            name for name, job in self._jobs.items()
            if job.consecutive_failures > 0
        ]
        return {
            "name": "scheduler",
            "healthy": self._running,
            "details": {
                "running": self._running,
                "total_jobs": self.job_count,
                "failing_jobs": failing_jobs,
            },
        }

    def status_summary(self) -> dict:
        """Get status of all scheduled jobs."""
        return {
            "running": self._running,
            "total_jobs": self.job_count,
            "jobs": {
                name: {
                    "enabled": job.enabled,
                    "interval_seconds": job.interval_seconds,
                    "run_count": job.run_count,
                    "is_due": job.is_due,
                    "next_run_in": round(job.next_run_in),
                    "consecutive_failures": job.consecutive_failures,
                    "last_error": job.last_error,
                }
                for name, job in self._jobs.items()
            },
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_scheduler: CronScheduler | None = None


def get_scheduler() -> CronScheduler:
    """Get the global scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler

