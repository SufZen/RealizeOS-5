"""
Agent Lifecycle Manager: tracks agent status transitions.

Status model: idle → running → idle (normal flow)
                         → error (on exception)
              paused (manual, skips routing)

All transitions are persisted in the agent_states table and logged as activity events.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

VALID_STATUSES = {"idle", "running", "paused", "error"}


def get_agent_status(agent_key: str, venture_key: str, db_path=None) -> dict | None:
    """Get the current status record for an agent."""
    from realize_core.db.schema import get_connection
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM agent_states WHERE agent_key = ? AND venture_key = ?",
            (agent_key, venture_key),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_agent_status(
    agent_key: str,
    venture_key: str,
    status: str,
    error_message: str = None,
    db_path=None,
):
    """
    Set an agent's status. Creates the record if it doesn't exist.

    Also logs the transition as an activity event when activity_log is enabled.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATUSES}")

    from realize_core.db.schema import get_connection
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn = get_connection(db_path)

    try:
        existing = conn.execute(
            "SELECT status FROM agent_states WHERE agent_key = ? AND venture_key = ?",
            (agent_key, venture_key),
        ).fetchone()

        if existing:
            fields = ["status = ?", "updated_at = ?"]
            params = [status, now]
            if status == "running":
                fields.append("last_run_at = ?")
                params.append(now)
            if status == "error" and error_message:
                fields.append("last_error = ?")
                params.append(error_message)
            elif status != "error":
                fields.append("last_error = NULL")

            params.extend([agent_key, venture_key])
            conn.execute(
                f"UPDATE agent_states SET {', '.join(fields)} WHERE agent_key = ? AND venture_key = ?",
                params,
            )
        else:
            conn.execute(
                """INSERT INTO agent_states (agent_key, venture_key, status, updated_at, last_run_at, last_error)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (agent_key, venture_key, status, now,
                 now if status == "running" else None,
                 error_message if status == "error" else None),
            )
        conn.commit()
    finally:
        conn.close()

    # Log transition as activity event (fire-and-forget)
    try:
        from realize_core.activity.logger import log_event
        log_event(
            venture_key=venture_key,
            actor_type="system",
            actor_id=agent_key,
            action="status_changed",
            entity_type="agent",
            entity_id=agent_key,
            details=f'{{"status": "{status}"}}',
        )
    except Exception:
        pass


def mark_running(agent_key: str, venture_key: str, db_path=None):
    """Convenience: mark agent as running."""
    set_agent_status(agent_key, venture_key, "running", db_path=db_path)


def mark_idle(agent_key: str, venture_key: str, db_path=None):
    """Convenience: mark agent as idle (completed successfully)."""
    set_agent_status(agent_key, venture_key, "idle", db_path=db_path)


def mark_error(agent_key: str, venture_key: str, error_message: str, db_path=None):
    """Convenience: mark agent as error."""
    set_agent_status(agent_key, venture_key, "error", error_message=error_message, db_path=db_path)


def is_paused(agent_key: str, venture_key: str, db_path=None) -> bool:
    """Check if an agent is paused (should skip routing)."""
    state = get_agent_status(agent_key, venture_key, db_path)
    return state is not None and state.get("status") == "paused"
