"""
Unified wall-clock scheduler for background Dreaming jobs.

Replaces the previous interval-based scheduling (``parse_interval("daily")`` =
every 24h from process start) with a single APScheduler ``AsyncIOScheduler``
driven by true ``CronTrigger`` wall-clock times:

- **Digest** fires at ``hour:00`` in the configured timezone, on workdays
  (``mon-fri``) when ``workdays_only`` is true, otherwise every day.
- **Curator** runs daily at ``hour:00`` in the configured timezone.
- **Reflex** runs every ``reflex_interval_minutes`` (default 60), enriching
  recently-modified FABRIC entities with low-risk proposals.

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
REFLEX_JOB_ID = "dreaming_reflex"

# Safety cap: never run Reflex over more than this many entities per pass.
REFLEX_MAX_ENTITIES = 200
# Buffer added to the lookback window so entities changed right at a tick
# boundary are not missed between runs.
_REFLEX_WINDOW_BUFFER_MINUTES = 5


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


def make_reflex_trigger(dreaming_cfg: dict[str, Any]) -> Any:
    """Build the Reflex ``IntervalTrigger`` from the dreaming config.

    Fires every ``reflex_interval_minutes`` (default 60). Imports APScheduler
    lazily so callers/tests can guard on availability.
    """
    from apscheduler.triggers.interval import IntervalTrigger

    minutes = int(dreaming_cfg.get("reflex_interval_minutes", 60))
    return IntervalTrigger(minutes=minutes)


def build_dream_scheduler(
    config: dict[str, Any],
    *,
    dream_inbox: Any,
    synapse: Any,
    systems: dict[str, Any],
    event_log: Any | None = None,
    digest_callback: Callable[..., Awaitable[Any]] | None = None,
    curator_callback: Callable[..., Awaitable[Any]] | None = None,
    reflex_callback: Callable[..., Awaitable[Any]] | None = None,
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
    want_reflex = bool(features.get("dreaming_reflex"))
    if not (want_digest or want_curator or want_reflex):
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
            default_policy = getattr(dream_inbox, "_policy", None)
            venture_keys = list(systems.keys())

            async def _run_curator() -> None:
                from pathlib import Path

                from realize_core.config import KB_PATH
                from realize_core.dreaming.curator import CuratorCycle
                from realize_core.dreaming.policy import TrustPolicy

                kb_path = Path(KB_PATH)

                for venture_key in venture_keys:
                    try:
                        # Each venture gets its OWN effective Trust Policy:
                        # systems/<venture>/trust-policy.yaml merged over
                        # shared/trust-policy.yaml merged over built-in defaults.
                        # Fall back to the inbox's default policy on any failure.
                        try:
                            venture_policy = TrustPolicy.load_for_venture(kb_path, venture_key)
                        except Exception as policy_exc:
                            logger.warning(
                                "Per-venture policy load failed for '%s' (using default): %s",
                                venture_key,
                                policy_exc,
                            )
                            venture_policy = default_policy

                        proposals = CuratorCycle(synapse=synapse, policy=venture_policy).run(venture=venture_key)
                        dream_inbox.submit_batch(proposals, policy=venture_policy)
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

    # --- Reflex job ------------------------------------------------------
    # Runs the Reflex enrichment cycle over recently-modified FABRIC entities
    # on a frequent interval, per venture. Low-risk enrichment proposals
    # (add_tag/add_ref/annotate_entity) land in the Dream Inbox for review.
    if want_reflex and synapse is not None and dream_inbox is not None:
        dreaming_cfg = get_dreaming_config(config)
        interval_minutes = int(dreaming_cfg.get("reflex_interval_minutes", 60))
        callback = reflex_callback
        if callback is None:
            default_policy = getattr(dream_inbox, "_policy", None)
            venture_keys = list(systems.keys())

            async def _run_reflex() -> None:
                from datetime import datetime, timedelta
                from pathlib import Path

                from realize_core.config import KB_PATH
                from realize_core.dreaming.policy import TrustPolicy
                from realize_core.dreaming.reflex import ReflexCycle
                from realize_core.fabric.crud import scan_venture

                kb_path = Path(KB_PATH)
                # Look back one interval plus a small buffer so entities changed
                # near a tick boundary are not skipped between runs.
                since = datetime.now() - timedelta(minutes=interval_minutes + _REFLEX_WINDOW_BUFFER_MINUTES)

                for venture_key in venture_keys:
                    try:
                        # Per-venture effective Trust Policy (same resolution as
                        # the Curator); fall back to the inbox default on failure.
                        try:
                            venture_policy = TrustPolicy.load_for_venture(kb_path, venture_key)
                        except Exception as policy_exc:
                            logger.warning(
                                "Per-venture policy load failed for '%s' (using default): %s",
                                venture_key,
                                policy_exc,
                            )
                            venture_policy = default_policy

                        # Prefer synapse.touched_since when available; otherwise
                        # scan the venture dir and filter by last_modified_at.
                        touched_since = getattr(synapse, "touched_since", None)
                        if callable(touched_since):
                            entities = list(touched_since(since, scope=venture_key))
                        else:
                            venture_dir = kb_path / "systems" / venture_key
                            entities = [
                                e
                                for e in scan_venture(venture_dir, venture=venture_key)
                                if e.last_modified_at is not None and e.last_modified_at >= since
                            ]

                        # Cap the workload per run.
                        entities = entities[:REFLEX_MAX_ENTITIES]

                        reflex = ReflexCycle(policy=venture_policy)
                        proposals: list[Any] = []
                        for entity in entities:
                            proposals.extend(reflex.analyze(entity))

                        if proposals:
                            dream_inbox.submit_batch(proposals, policy=venture_policy)
                    except Exception as exc:  # never crash the scheduler
                        logger.warning("Scheduled Reflex failed for venture '%s': %s", venture_key, exc)

            callback = _run_reflex

        scheduler.add_job(
            callback,
            trigger=make_reflex_trigger(dreaming_cfg),
            id=REFLEX_JOB_ID,
            replace_existing=True,
        )
        registered += 1
        logger.info(
            "Dream scheduler: reflex job registered (interval_minutes=%s)",
            interval_minutes,
        )

    if registered == 0:
        return None
    return scheduler
