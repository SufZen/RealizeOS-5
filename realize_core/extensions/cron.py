"""
Cron Extension: Scheduled task execution via APScheduler.

Wraps APScheduler (if available) to provide cron-like scheduling as
a first-class extension. When APScheduler is not installed, the extension
gracefully degrades to a no-op scheduler.

Usage::

    cron = CronExtension()
    await cron.on_load(config={
        "jobs": [
            {
                "id": "daily-report",
                "trigger": "cron",
                "hour": 9,
                "minute": 0,
                "func": "realize_core.tasks.daily_report",
            }
        ]
    })

Jobs can also be added dynamically::

    cron.add_job("my-job", func=my_coroutine, trigger="interval", minutes=30)
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import Any

from realize_core.extensions.base import (
    ExtensionManifest,
    ExtensionType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

CRON_MANIFEST = ExtensionManifest(
    name="cron",
    version="1.0.0",
    extension_type=ExtensionType.INTEGRATION,
    description="Cron-like scheduled task execution via APScheduler",
    author="RealizeOS",
    entry_point="realize_core.extensions.cron.CronExtension",
)


# ---------------------------------------------------------------------------
# Scheduler abstraction
# ---------------------------------------------------------------------------


class _NoOpScheduler:
    """Fallback when APScheduler is not installed."""

    def __init__(self) -> None:
        self._running = False

    def start(self) -> None:
        self._running = True
        logger.warning(
            "APScheduler not installed — cron jobs will NOT execute. Install with: pip install apscheduler",
        )

    def shutdown(self, wait: bool = True) -> None:
        self._running = False

    def add_job(self, func: Any, **kwargs: Any) -> Any:
        job_id = kwargs.get("id", "unknown")
        logger.warning(
            "NoOpScheduler: ignoring add_job('%s') — install apscheduler for real scheduling",
            job_id,
        )
        return None

    def remove_job(self, job_id: str) -> None:
        pass

    def get_jobs(self) -> list:
        return []

    @property
    def running(self) -> bool:
        return self._running


def _create_scheduler() -> Any:
    """Create an APScheduler or fallback to NoOp."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        return AsyncIOScheduler()
    except ImportError:
        return _NoOpScheduler()


# ---------------------------------------------------------------------------
# CronExtension
# ---------------------------------------------------------------------------


class CronExtension:
    """
    Cron-like scheduled task runner.

    Implements BaseExtension protocol. Uses APScheduler's AsyncIOScheduler
    when available; falls back to _NoOpScheduler with warning logs.
    """

    def __init__(self) -> None:
        self._scheduler: Any = None
        self._jobs: dict[str, dict[str, Any]] = {}
        self._loaded = False

    # -- BaseExtension protocol ----------------------------------------

    @property
    def name(self) -> str:
        return "cron"

    @property
    def extension_type(self) -> ExtensionType:
        return ExtensionType.INTEGRATION

    @property
    def manifest(self) -> ExtensionManifest:
        return CRON_MANIFEST

    def is_available(self) -> bool:
        return True  # always available (NoOp fallback)

    async def on_load(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize the scheduler and register any jobs from config.

        Config format::

            {
                "timezone": "UTC",
                "jobs": [
                    {
                        "id": "daily-report",
                        "trigger": "cron",      # cron | interval | date
                        "hour": 9,
                        "func": "module.path.to_function",
                    }
                ]
            }
        """
        config = config or {}
        self._scheduler = _create_scheduler()
        self._scheduler.start()
        self._loaded = True

        # Register jobs from config
        jobs = config.get("jobs", [])
        for job_spec in jobs:
            if not isinstance(job_spec, dict) or "id" not in job_spec:
                continue
            self._register_job_from_spec(job_spec)

        logger.info(
            "CronExtension loaded with %d job(s)",
            len(self._jobs),
        )

    async def on_unload(self) -> None:
        """Shut down the scheduler."""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        self._jobs.clear()
        self._loaded = False
        logger.info("CronExtension unloaded")

    # -- Public API ----------------------------------------------------

    def add_job(
        self,
        job_id: str,
        func: Callable[..., Any],
        trigger: str = "interval",
        replace_existing: bool = True,
        **trigger_args: Any,
    ) -> bool:
        """
        Add a scheduled job dynamically.

        Args:
            job_id: Unique job identifier.
            func: Callable to schedule (can be async).
            trigger: APScheduler trigger type: "cron", "interval", "date".
            replace_existing: Replace if job_id already exists.
            **trigger_args: Trigger-specific args (hour, minute, seconds, etc.).

        Returns:
            True if the job was added.
        """
        if not self._scheduler:
            logger.error("Scheduler not initialized — call on_load() first")
            return False

        try:
            self._scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                replace_existing=replace_existing,
                **trigger_args,
            )
            self._jobs[job_id] = {
                "trigger": trigger,
                "func": str(func),
                **trigger_args,
            }
            logger.info("Added cron job '%s' (trigger=%s)", job_id, trigger)
            return True
        except Exception as e:
            logger.error("Failed to add job '%s': %s", job_id, e)
            return False

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job by ID."""
        if not self._scheduler:
            return False
        try:
            self._scheduler.remove_job(job_id)
            self._jobs.pop(job_id, None)
            logger.info("Removed cron job '%s'", job_id)
            return True
        except Exception as e:
            logger.warning("Failed to remove job '%s': %s", job_id, e)
            return False

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all registered jobs."""
        return [{"id": job_id, **spec} for job_id, spec in self._jobs.items()]

    @property
    def job_count(self) -> int:
        """Number of registered jobs."""
        return len(self._jobs)

    @property
    def is_running(self) -> bool:
        """Whether the scheduler is active."""
        if self._scheduler and hasattr(self._scheduler, "running"):
            return self._scheduler.running
        return False

    # -- Internal ------------------------------------------------------

    def _register_job_from_spec(self, spec: dict[str, Any]) -> None:
        """Register a job from a config spec dict."""
        job_id = spec["id"]
        func_path = spec.get("func", "")

        # Resolve function from dotted path
        func = self._resolve_func(func_path)
        if func is None:
            logger.warning(
                "Cannot resolve func '%s' for job '%s'",
                func_path,
                job_id,
            )
            return

        trigger = spec.get("trigger", "interval")
        trigger_args = {k: v for k, v in spec.items() if k not in ("id", "func", "trigger")}

        self.add_job(job_id, func, trigger=trigger, **trigger_args)

    @staticmethod
    def _resolve_func(dotted_path: str) -> Callable[..., Any] | None:
        """Resolve a dotted path to a callable."""
        if not dotted_path:
            return None

        parts = dotted_path.rsplit(".", 1)
        if len(parts) != 2:
            return None

        module_path, func_name = parts
        try:
            module = importlib.import_module(module_path)
            func = getattr(module, func_name, None)
            if callable(func):
                return func
            return None
        except ImportError:
            return None
