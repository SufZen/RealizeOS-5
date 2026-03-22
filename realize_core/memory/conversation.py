"""
Conversation History Manager for RealizeOS.

Maintains per-user, per-system conversation buffers with cross-system context sharing.
Uses SQLite write-through with in-memory cache for persistence across restarts.
Supports thread/topic scoping via optional topic_id parameter.
"""
import logging
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

# Default max conversation history length
MAX_CONVERSATION_HISTORY = 20

# In-memory cache: {(system_key, user_id, topic_id): [{"role": ..., "content": ...}]}
_conversations: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

# Track which keys have been hydrated from SQLite
_hydrated: set[tuple[str, str, str]] = set()


def _db_ctx():
    """Get a SQLite connection context manager from memory store."""
    from realize_core.memory.store import db_connection
    return db_connection()


def _hydrate_if_needed(system_key: str, user_id: str, topic_id: str = ""):
    """Lazy-load conversation history from SQLite if not already in cache."""
    key = (system_key, user_id, topic_id)
    if key in _hydrated:
        return

    try:
        with _db_ctx() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM conversations "
                "WHERE bot_name = ? AND user_id = ? AND COALESCE(topic_id, '') = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (system_key, user_id, topic_id, MAX_CONVERSATION_HISTORY),
            ).fetchall()

        if rows:
            _conversations[key] = [
                {"role": r["role"], "content": r["content"], "created_at": r["created_at"]}
                for r in reversed(rows)
            ]
            logger.info(f"Hydrated {len(rows)} messages for {system_key}:{user_id}:{topic_id}")
    except Exception as e:
        logger.warning(f"Failed to hydrate conversation for {system_key}:{user_id}: {e}")

    _hydrated.add(key)


def get_history(system_key: str, user_id: str, topic_id: str = "") -> list[dict]:
    """
    Get conversation history for a specific user and system.

    Args:
        system_key: System identifier
        user_id: User identifier
        topic_id: Thread/topic ID (empty string for regular chats)

    Returns:
        List of message dicts: [{"role": "user"/"assistant", "content": "..."}]
    """
    _hydrate_if_needed(system_key, user_id, topic_id)
    key = (system_key, user_id, topic_id)
    return list(_conversations[key])


def add_message(system_key: str, user_id: str, role: str, content: str, topic_id: str = ""):
    """
    Add a message to the conversation history.
    Writes to both in-memory cache and SQLite.
    """
    _hydrate_if_needed(system_key, user_id, topic_id)
    key = (system_key, user_id, topic_id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _conversations[key].append({"role": role, "content": content, "created_at": now})

    # Trim to max history length
    if len(_conversations[key]) > MAX_CONVERSATION_HISTORY:
        _conversations[key] = _conversations[key][-MAX_CONVERSATION_HISTORY:]

    # Write-through to SQLite
    try:
        with _db_ctx() as conn:
            conn.execute(
                "INSERT INTO conversations (bot_name, user_id, role, content, topic_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (system_key, user_id, role, content, topic_id, now),
            )
    except Exception as e:
        logger.warning(f"Failed to persist message for {system_key}:{user_id}: {e}")


def clear_history(system_key: str, user_id: str, topic_id: str = ""):
    """Clear conversation history for a specific user and system."""
    key = (system_key, user_id, topic_id)
    _conversations[key] = []
    _hydrated.discard(key)

    try:
        with _db_ctx() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE bot_name = ? AND user_id = ?",
                (system_key, user_id),
            )
    except Exception as e:
        logger.warning(f"Failed to clear persisted history: {e}")

    logger.info(f"Cleared history for {system_key}:{user_id}:{topic_id}")


def clear_all():
    """Clear all conversation histories."""
    _conversations.clear()
    _hydrated.clear()

    try:
        with _db_ctx() as conn:
            conn.execute("DELETE FROM conversations")
    except Exception as e:
        logger.warning(f"Failed to clear all persisted conversations: {e}")


def get_cross_system_context(
    user_id: str,
    system_keys: list[str],
    exclude_system: str = None,
) -> list[dict]:
    """
    Get recent conversation context from other systems for cross-system awareness.

    Args:
        user_id: User identifier
        system_keys: List of all system keys to check
        exclude_system: System to exclude (the currently active one)

    Returns:
        List of the most recent messages from other systems.
    """
    cross_context = []
    for sys_key in system_keys:
        if sys_key == exclude_system:
            continue
        history = get_history(sys_key, user_id)
        if history:
            recent = history[-2:]
            for msg in recent:
                cross_context.append({
                    "role": msg["role"],
                    "content": f"[From {sys_key}] {msg['content'][:500]}",
                })
    return cross_context


def get_history_with_timestamps(system_key: str, user_id: str, topic_id: str = "") -> list[dict]:
    """Get conversation history with timestamp prefixes for temporal awareness."""
    _hydrate_if_needed(system_key, user_id, topic_id)
    key = (system_key, user_id, topic_id)
    result = []
    for msg in _conversations[key]:
        ts = msg.get("created_at", "")
        content = msg["content"]
        if ts:
            content = f"[{ts}] {content}"
        result.append({"role": msg["role"], "content": content})
    return result


def get_last_assistant_message(system_key: str, user_id: str) -> str | None:
    """Get the most recent assistant message for a user in a system."""
    history = get_history(system_key, user_id)
    for msg in reversed(history):
        if msg["role"] == "assistant":
            return msg["content"]
    return None
