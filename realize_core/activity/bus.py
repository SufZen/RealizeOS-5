"""
In-memory event bus for real-time activity streaming (SSE).

Subscribers register a callback; new events are pushed to all subscribers.
Thread-safe via a simple list + copy-on-iterate pattern.
"""
import logging
from collections import deque
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Subscribers: list of callback functions
_subscribers: list[Callable[[dict], None]] = []

# Recent events buffer (for new SSE connections to get recent history)
_recent_events: deque[dict] = deque(maxlen=100)


def publish_event(event: dict):
    """Publish an event to all subscribers and the recent buffer."""
    _recent_events.append(event)
    for callback in list(_subscribers):
        try:
            callback(event)
        except Exception as e:
            logger.debug(f"Event subscriber error: {e}")


def subscribe(callback: Callable[[dict], None]):
    """Register a callback to receive new events."""
    _subscribers.append(callback)


def unsubscribe(callback: Callable[[dict], None]):
    """Remove a subscriber callback."""
    try:
        _subscribers.remove(callback)
    except ValueError:
        pass


def get_recent_events(limit: int = 50) -> list[dict]:
    """Get recent events from the buffer (newest first)."""
    return list(reversed(list(_recent_events)))[:limit]
