"""
Unified wall-clock scheduler for background Dreaming jobs.

Replaces the previous interval-based scheduling (``parse_interval("daily")`` =
every 24h from process start) with a single APScheduler ``AsyncIOScheduler``
driven by true ``CronTrigger`` wall-clock times:

- **Digest** fires at ``hour:00`` in the configured timezone, on workdays
  (``mon-fri``) when ``workdays_only`` is true, otherwise every day.
- **Curator** runs daily at ``hour:00`` in the configured timezone.

Everything stays behind the existing feature flags and is fully optional: if
APScheduler is not installed the builder returns ``None`` and the caller simply
runs without scheduled Dreaming jobs (manual CLI triggers are unaffected).

This module deliberately contains no FastAPI imports so it can be unit-tested in
isolation. ``main.py`` constructs the dependencies (inbox, synapse, ...) and
calls :func:`build_dream_scheduler`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

DIGEST_JOB_ID = "dream_email_digest"
CURATOR_JOB_ID = "dreaming_curator"


def _digest_day_of_week(workdays_only: bool) -> str:
    """``mon-fri`` when restricted to workdays, otherwise every day."""
    return "mon-fri" if workdays_only else "mon-sun"


def make_digest_trigger(digest_cfg: dict[str, Any]) -> Any:
    """Build the digest ``CronTrigger`` from the email-digest config.

    Imports APScheduler lazily so callers/tests can guard on availability.
    """
    from apscheduler.triggers.cron import CronTrigger

    hour = int(digest_cfg.get("hour", 8))
    timezone = str(digest_cfg.get("timezone", "Europe/Lisbon"))
    workdays_only = bool(digest_cfg.get("workdays_only", True))
    return CronTrigger(
        hour=hour,
        minute=0,
        day_of_week=_digest_day_of_week(workdays_only),
        timezone=timezone,
    )


def make_curator_trigger(dreaming_cfg: dict[str, Any]) -> Any:
    """Build the Curator ``CronTrigger`` from the dreaming config."""
    from apscheduler.triggers.cron import CronTrigger

    hour = int(dreaming_cfg.get("hour", 3))
    timezone = str(dreaming_cfg.get("timezone", "Europe/Lisbon"))
    return CronTrigger(hour=hour, minute=0, timezone=timezone)


def build_dream_scheduler(
    config: dict[str, Any],
    *,
    dream_inbox: Any,
    synapse: Any,
    systems: dict[str, Any],
    event_log: Any | None = None,
    digest_callback: Callable[..., Awaitable[Any]] | None = None,
    curator_callback: Callable[..., Awaitable[Any]] | None = None,
) -> Any | None:
    """Construct (but do NOT start) the unified Dream scheduler.

    Registers the digest job when ``features.email_digest`` is true and a
    recipient is configured, and the Curator job when
    ``features.dreaming_curator`` is true. Returns the ``AsyncIOScheduler`` with
    its jobs already added, or ``None`` when neither job is enabled / APScheduler
    is unavailable.

    The ``*_callback`` parameters exist for tests to inject no-op coroutines;
    production code leaves them unset and the real handlers are built here.
    """
    from realize_core.config import (
        get_dreaming_config,
        get_email_digest_config,
        get_features,
    )

    features = get_features(config)
    want_digest = bool(features.get("email_digest"))
    want_curator = bool(features.get("dreaming_curator"))
    if not (want_digest or want_curator):
        return None

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:
        logger.warning("APScheduler not installed — Dream scheduler disabled. Install with: pip install apscheduler")
        return None

    scheduler = AsyncIOScheduler()
    registered = 0

    # --- Digest job ------------------------------------------------------
    if want_digest and dream_inbox is not None:
        digest_cfg = get_email_digest_config(config)
        recipient = str(digest_cfg.get("recipient", "")).strip()
        if not recipient:
            logger.warning("Email digest enabled but no recipient configured — digest job not registered")
        else:
            callback = digest_callback
            if callback is None:
                base_url = str(digest_cfg.get("base_url", ""))

                async def _run_digest() -> None:
                    from realize_core.channels.email import send_dream_digest

                    await send_dream_digest(
                        dream_inbox,
                        recipient=recipient,
                        base_url=base_url,
                        event_log=event_log,
                    )

                callback = _run_digest

            scheduler.add_job(
                callback,
                trigger=make_digest_trigger(digest_cfg),
                id=DIGEST_JOB_ID,
                replace_existing=True,
            )
            registered += 1
            logger.info(
                "Dream scheduler: digest job registered (hour=%s, tz=%s, workdays_only=%s)",
                digest_cfg.get("hour", 8),
                digest_cfg.get("timezone", "Europe/Lisbon"),
                digest_cfg.get("workdays_only", True),
            )

    # --- Curator job -----------------------------------------------------
    if want_curator and synapse is not None and dream_inbox is not None:
        dreaming_cfg = get_dreaming_config(config)
        callback = curator_callback
        if callback is None:
            policy = getattr(dream_inbox, "_policy", None)
            venture_keys = list(systems.keys())

            async def _run_curator() -> None:
                from realize_core.dreaming.curator import CuratorCycle

                for venture_key in venture_keys:
                    try:
                        proposals = CuratorCycle(synapse=synapse, policy=policy).run(venture=venture_key)
                        dream_inbox.submit_batch(proposals)
                    except Exception as exc:  # never crash the scheduler
                        logger.warning("Scheduled Curator failed for venture '%s': %s", venture_key, exc)

            callback = _run_curator

        scheduler.add_job(
            callback,
            trigger=make_curator_trigger(dreaming_cfg),
            id=CURATOR_JOB_ID,
            replace_existing=True,
        )
        registered += 1
        logger.info(
            "Dream scheduler: curator job registered (hour=%s, tz=%s)",
            dreaming_cfg.get("hour", 3),
            dreaming_cfg.get("timezone", "Europe/Lisbon"),
        )

    if registered == 0:
        return None
    return scheduler
