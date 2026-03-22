"""
Heartbeat Scheduler: triggers agent runs on configured schedules.

Uses APScheduler (if available) for cron/interval scheduling.
Falls back to a simple polling loop if APScheduler is not installed.

Each heartbeat:
1. Reads scheduled agents from agent_states table
2. Skips paused/running agents
3. Invokes base_handler.process_message() with a system heartbeat message
4. Logs results to activity_events
"""
import asyncio
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_scheduler = None
_running = False


async def _run_heartbeat(agent_key: str, venture_key: str, config: dict):
    """Execute a single agent heartbeat."""
    from realize_core.activity.logger import log_event
    from realize_core.scheduler.lifecycle import (
        get_agent_status,
        mark_error,
        mark_idle,
        mark_running,
    )

    # Check if agent should run
    state = get_agent_status(agent_key, venture_key)
    if state and state.get("status") in ("paused", "running"):
        logger.debug(f"Skipping heartbeat for {agent_key}@{venture_key}: status={state.get('status')}")
        log_event(
            venture_key=venture_key, actor_type="system", actor_id=agent_key,
            action="heartbeat_skipped", entity_type="agent", entity_id=agent_key,
            details=f'{{"reason": "agent_{state.get("status")}"}}',
        )
        return

    logger.info(f"Running heartbeat for {agent_key}@{venture_key}")
    mark_running(agent_key, venture_key)

    try:
        from realize_core.base_handler import process_message

        heartbeat_message = (
            f"[HEARTBEAT] Scheduled check-in for agent {agent_key}. "
            f"Review pending tasks, check for updates, and report status."
        )

        await process_message(
            system_key=venture_key,
            user_id=f"scheduler:{agent_key}",
            message=heartbeat_message,
            system_config=config.get("system_config"),
            shared_config=config.get("shared_config"),
            kb_path=config.get("kb_path"),
            channel="scheduler",
            features=config.get("features", {}),
        )

        mark_idle(agent_key, venture_key)
        log_event(
            venture_key=venture_key, actor_type="system", actor_id=agent_key,
            action="heartbeat_completed", entity_type="agent", entity_id=agent_key,
        )
        logger.info(f"Heartbeat completed for {agent_key}@{venture_key}")

    except Exception as e:
        mark_error(agent_key, venture_key, f"Heartbeat failed: {str(e)[:300]}")
        log_event(
            venture_key=venture_key, actor_type="system", actor_id=agent_key,
            action="heartbeat_failed", entity_type="agent", entity_id=agent_key,
            details=f'{{"error": "{str(e)[:200]}"}}',
        )
        logger.error(f"Heartbeat failed for {agent_key}@{venture_key}: {e}")


def _get_scheduled_agents(db_path=None) -> list[dict]:
    """Get all agents with a schedule configured."""
    from realize_core.db.schema import get_connection
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT agent_key, venture_key, schedule_cron, schedule_interval_sec, next_run_at
               FROM agent_states
               WHERE (schedule_cron IS NOT NULL OR schedule_interval_sec IS NOT NULL)
               AND status != 'paused'"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _update_next_run(agent_key: str, venture_key: str, interval_sec: int, db_path=None):
    """Update the next_run_at timestamp for an interval-scheduled agent."""
    from datetime import timedelta

    from realize_core.db.schema import get_connection
    next_run = (datetime.now(UTC) + timedelta(seconds=interval_sec)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE agent_states SET next_run_at = ? WHERE agent_key = ? AND venture_key = ?",
            (next_run, agent_key, venture_key),
        )
        conn.commit()
    finally:
        conn.close()


async def start_scheduler(app_config: dict = None):
    """
    Start the heartbeat scheduler.

    Tries APScheduler first; falls back to a simple asyncio loop.
    """
    global _scheduler, _running
    app_config = app_config or {}

    if not app_config.get("features", {}).get("heartbeats"):
        logger.debug("Heartbeat scheduler disabled (features.heartbeats not set)")
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        _scheduler = AsyncIOScheduler()

        scheduled_agents = _get_scheduled_agents()
        for agent in scheduled_agents:
            job_id = f"heartbeat:{agent['agent_key']}@{agent['venture_key']}"

            if agent.get("schedule_cron"):
                trigger = CronTrigger.from_crontab(agent["schedule_cron"])
            elif agent.get("schedule_interval_sec"):
                trigger = IntervalTrigger(seconds=agent["schedule_interval_sec"])
            else:
                continue

            _scheduler.add_job(
                _run_heartbeat,
                trigger=trigger,
                args=[agent["agent_key"], agent["venture_key"], app_config],
                id=job_id,
                replace_existing=True,
            )
            logger.info(f"Scheduled heartbeat: {job_id}")

        _scheduler.start()
        _running = True
        logger.info(f"Heartbeat scheduler started with {len(scheduled_agents)} agent(s)")

    except ImportError:
        logger.info("APScheduler not installed — using simple polling fallback")
        _running = True
        asyncio.create_task(_polling_fallback(app_config))


async def _polling_fallback(app_config: dict):
    """Simple fallback: check every 60s for agents whose next_run_at has passed."""
    global _running
    while _running:
        try:
            await asyncio.sleep(60)
            now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            agents = _get_scheduled_agents()

            for agent in agents:
                next_run = agent.get("next_run_at")
                interval = agent.get("schedule_interval_sec")

                if next_run and next_run <= now:
                    await _run_heartbeat(agent["agent_key"], agent["venture_key"], app_config)
                    if interval:
                        _update_next_run(agent["agent_key"], agent["venture_key"], interval)
                elif not next_run and interval:
                    # First run — set next_run_at
                    _update_next_run(agent["agent_key"], agent["venture_key"], interval)

        except Exception as e:
            logger.error(f"Polling scheduler error: {e}")


async def stop_scheduler():
    """Stop the heartbeat scheduler."""
    global _scheduler, _running
    _running = False
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Heartbeat scheduler stopped")


def reload_schedules(app_config: dict = None):
    """Reload schedules from DB (call after schedule changes)."""
    global _scheduler
    if _scheduler:
        try:
            _scheduler.remove_all_jobs()
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger

            for agent in _get_scheduled_agents():
                job_id = f"heartbeat:{agent['agent_key']}@{agent['venture_key']}"
                if agent.get("schedule_cron"):
                    trigger = CronTrigger.from_crontab(agent["schedule_cron"])
                elif agent.get("schedule_interval_sec"):
                    trigger = IntervalTrigger(seconds=agent["schedule_interval_sec"])
                else:
                    continue

                _scheduler.add_job(
                    _run_heartbeat, trigger=trigger,
                    args=[agent["agent_key"], agent["venture_key"], app_config or {}],
                    id=job_id, replace_existing=True,
                )
        except Exception as e:
            logger.error(f"Failed to reload schedules: {e}")
