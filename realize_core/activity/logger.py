"""
Activity Event Logger: fire-and-forget event recording.

Emits events to both SQLite (persistence) and an in-memory bus (for SSE streaming).
All logging is non-blocking — failures are logged but never propagate to the caller.
"""

import logging
import uuid
from datetime import UTC, datetime

from realize_core.activity.bus import publish_event

logger = logging.getLogger(__name__)


def log_event(
    venture_key: str,
    actor_type: str,
    actor_id: str,
    action: str,
    entity_type: str = None,
    entity_id: str = None,
    details: str = None,
) -> str | None:
    """
    Log an activity event (fire-and-forget).

    Returns the event ID on success, None on failure.
    Never raises — all errors are swallowed and logged.
    """
    event_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    event = {
        "id": event_id,
        "venture_key": venture_key,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details,
        "created_at": created_at,
    }

    # Persist to SQLite
    try:
        from realize_core.db.schema import get_connection

        conn = get_connection()
        conn.execute(
            """INSERT INTO activity_events
               (id, venture_key, actor_type, actor_id, action, entity_type, entity_id, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, venture_key, actor_type, actor_id, action, entity_type, entity_id, details, created_at),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to persist activity event: {e}")

    # Publish to in-memory bus (for SSE)
    try:
        publish_event(event)
    except Exception as e:
        logger.debug(f"Failed to publish event to bus: {e}")

    return event_id
