"""
FABRIC Event Log.

JSONL append-only event log with SSE streaming support.
Every action, decision, mission state change, channel event, and dream
proposal is recorded here. Powers replay, audit, forensics, and dreaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Callable

from realize_core.fabric.event_types import Event

logger = logging.getLogger(__name__)


class EventLog:
    """
    Append-only JSONL event log.

    Features:
    - Append events to a JSONL file
    - Query events by category, actor, venture, time range
    - SSE streaming for live consumers
    - Tail mode for watching new events
    """

    def __init__(self, log_path: Path | str):
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._subscribers: list[asyncio.Queue] = []

    @property
    def log_path(self) -> Path:
        return self._log_path

    def append(self, event: Event) -> str:
        """
        Append an event to the log.

        Returns the event_id of the written event.
        """
        line = json.dumps(event.to_dict(), ensure_ascii=False)

        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

        # Notify subscribers
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Drop if subscriber is too slow

        logger.debug(f"Event logged: {event.category}.{event.action} [{event.event_id}]")
        return event.event_id

    def query(
        self,
        category: str = "",
        action: str = "",
        actor: str = "",
        venture: str = "",
        mission_id: str = "",
        entity_id: str = "",
        since: str = "",
        until: str = "",
        limit: int = 100,
    ) -> list[Event]:
        """
        Query events from the log.

        All filters are optional and combined with AND logic.
        """
        if not self._log_path.exists():
            return []

        results: list[Event] = []

        with self._log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Apply filters
                if category and data.get("category") != category:
                    continue
                if action and data.get("action") != action:
                    continue
                if actor and data.get("actor") != actor:
                    continue
                if venture and data.get("venture") != venture:
                    continue
                if mission_id and data.get("mission_id") != mission_id:
                    continue
                if entity_id and data.get("entity_id") != entity_id:
                    continue
                if since and data.get("timestamp", "") < since:
                    continue
                if until and data.get("timestamp", "") > until:
                    continue

                results.append(Event.from_dict(data))

        # Return most recent first, limited
        results.reverse()
        return results[:limit]

    def count(self, category: str = "", venture: str = "") -> int:
        """Count events matching filters."""
        if not self._log_path.exists():
            return 0

        count = 0
        with self._log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if category and data.get("category") != category:
                    continue
                if venture and data.get("venture") != venture:
                    continue
                count += 1
        return count

    def tail(self, n: int = 20) -> list[Event]:
        """Get the last N events."""
        if not self._log_path.exists():
            return []

        # Read all lines (for small logs) or seek from end (for large logs)
        lines: list[str] = []
        with self._log_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        results = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                results.append(Event.from_dict(data))
            except json.JSONDecodeError:
                continue

        return results

    def subscribe(self) -> asyncio.Queue:
        """
        Subscribe to new events via an async queue.

        Returns a queue that will receive Event objects as they are appended.
        Caller is responsible for calling unsubscribe() when done.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def stream_sse(
        self,
        category: str = "",
        venture: str = "",
    ) -> AsyncIterator[str]:
        """
        Yield SSE-formatted events as they are appended.

        This is an async generator for use with FastAPI's StreamingResponse.
        """
        queue = self.subscribe()
        try:
            while True:
                event = await queue.get()
                # Apply filters
                if category and event.category != category:
                    continue
                if venture and event.venture != venture:
                    continue

                data = json.dumps(event.to_dict(), ensure_ascii=False)
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(queue)

    def clear(self) -> None:
        """Clear the event log. USE WITH CAUTION."""
        if self._log_path.exists():
            self._log_path.unlink()
        logger.warning("Event log cleared")
