"""
Event Hooks Extension: Pub/sub event system for RealizeOS lifecycle events.

Provides a lightweight hook system that extensions and core components
can subscribe to. Hooks fire asynchronously and support:
  - Multiple subscribers per event
  - Priority ordering
  - Error isolation (one failing handler won't break others)

Built-in event types::

    on_message        — Fired when a new user message arrives
    on_venture_change — Fired when the active venture changes
    on_agent_complete — Fired when an agent completes its work
    on_skill_trigger  — Fired when a skill is triggered
    on_extension_load — Fired when an extension is loaded
    on_error          — Fired on unhandled errors

Usage::

    hooks = HooksExtension()
    await hooks.on_load()

    # Subscribe
    hooks.subscribe("on_message", my_handler, priority=10)

    # Fire event
    await hooks.emit("on_message", {"text": "hello", "user": "alice"})
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from realize_core.extensions.base import (
    ExtensionManifest,
    ExtensionType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventType(StrEnum):
    """Standard lifecycle events."""
    ON_MESSAGE = "on_message"
    ON_VENTURE_CHANGE = "on_venture_change"
    ON_AGENT_COMPLETE = "on_agent_complete"
    ON_SKILL_TRIGGER = "on_skill_trigger"
    ON_EXTENSION_LOAD = "on_extension_load"
    ON_ERROR = "on_error"


# ---------------------------------------------------------------------------
# Subscription record
# ---------------------------------------------------------------------------

@dataclass
class HookSubscription:
    """A single subscription to an event."""
    event: str
    handler: Callable[..., Any]
    priority: int = 0  # lower = fires first
    name: str = ""     # optional human label

    def __post_init__(self) -> None:
        if not self.name:
            self.name = getattr(self.handler, "__name__", str(self.handler))


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

HOOKS_MANIFEST = ExtensionManifest(
    name="hooks",
    version="1.0.0",
    extension_type=ExtensionType.HOOK,
    description="Event hooks for RealizeOS lifecycle events",
    author="RealizeOS",
    entry_point="realize_core.extensions.hooks.HooksExtension",
)


# ---------------------------------------------------------------------------
# HooksExtension
# ---------------------------------------------------------------------------

class HooksExtension:
    """
    Pub/sub event hook system for RealizeOS.

    Implements BaseExtension protocol. Handlers can be sync or async;
    sync handlers are wrapped in ``asyncio.to_thread()``.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, list[HookSubscription]] = {}
        self._loaded = False
        self._emit_count = 0

    # -- BaseExtension protocol ----------------------------------------

    @property
    def name(self) -> str:
        return "hooks"

    @property
    def extension_type(self) -> ExtensionType:
        return ExtensionType.HOOK

    @property
    def manifest(self) -> ExtensionManifest:
        return HOOKS_MANIFEST

    def is_available(self) -> bool:
        return True

    async def on_load(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the hooks system."""
        self._loaded = True
        logger.info("HooksExtension loaded")

    async def on_unload(self) -> None:
        """Clean up all subscriptions."""
        sub_count = sum(len(v) for v in self._subscriptions.values())
        self._subscriptions.clear()
        self._loaded = False
        self._emit_count = 0
        logger.info(
            "HooksExtension unloaded (%d subscriptions cleared)", sub_count,
        )

    # -- Public API ----------------------------------------------------

    def subscribe(
        self,
        event: str,
        handler: Callable[..., Any],
        priority: int = 0,
        name: str = "",
    ) -> HookSubscription:
        """
        Subscribe a handler to an event.

        Args:
            event: Event name (e.g. "on_message" or EventType member).
            handler: Sync or async callable. Receives ``(event_data: dict)``.
            priority: Lower values fire first (default 0).
            name: Optional human-readable handler name.

        Returns:
            The created subscription (can be used to unsubscribe).
        """
        sub = HookSubscription(
            event=event,
            handler=handler,
            priority=priority,
            name=name,
        )

        if event not in self._subscriptions:
            self._subscriptions[event] = []

        self._subscriptions[event].append(sub)
        # Keep sorted by priority
        self._subscriptions[event].sort(key=lambda s: s.priority)

        logger.debug(
            "Subscribed '%s' to event '%s' (priority=%d)",
            sub.name, event, priority,
        )
        return sub

    def unsubscribe(self, subscription: HookSubscription) -> bool:
        """
        Remove a subscription.

        Args:
            subscription: The subscription to remove.

        Returns:
            True if found and removed.
        """
        subs = self._subscriptions.get(subscription.event, [])
        try:
            subs.remove(subscription)
            return True
        except ValueError:
            return False

    def unsubscribe_all(self, event: str) -> int:
        """Remove all subscriptions for an event. Returns count removed."""
        subs = self._subscriptions.pop(event, [])
        return len(subs)

    async def emit(
        self,
        event: str,
        data: dict[str, Any] | None = None,
        fail_fast: bool = False,
    ) -> list[Any]:
        """
        Emit an event, calling all subscribed handlers.

        Handlers are called in priority order. Errors in one handler
        do not prevent subsequent handlers from running (unless
        ``fail_fast=True``).

        Args:
            event: Event name to emit.
            data: Event payload dict.
            fail_fast: If True, stop on first handler error.

        Returns:
            List of results from each handler (None for failed ones).
        """
        subs = self._subscriptions.get(event, [])
        self._emit_count += 1

        if not subs:
            return []

        data = data or {}
        results: list[Any] = []

        for sub in subs:
            try:
                result = await self._call_handler(sub.handler, data)
                results.append(result)
            except Exception as e:
                logger.error(
                    "Error in hook handler '%s' for event '%s': %s",
                    sub.name, event, e,
                )
                results.append(None)
                if fail_fast:
                    raise

        return results

    # -- Introspection -------------------------------------------------

    def get_subscriptions(self, event: str) -> list[HookSubscription]:
        """Get all subscriptions for an event."""
        return list(self._subscriptions.get(event, []))

    def get_events(self) -> list[str]:
        """Get all events that have subscribers."""
        return list(self._subscriptions.keys())

    @property
    def subscription_count(self) -> int:
        """Total number of active subscriptions across all events."""
        return sum(len(v) for v in self._subscriptions.values())

    @property
    def emit_count(self) -> int:
        """Number of events emitted since load."""
        return self._emit_count

    def status_summary(self) -> dict[str, Any]:
        """Return a summary for monitoring."""
        return {
            "loaded": self._loaded,
            "events": len(self._subscriptions),
            "total_subscriptions": self.subscription_count,
            "emit_count": self._emit_count,
            "by_event": {
                event: len(subs)
                for event, subs in self._subscriptions.items()
            },
        }

    # -- Internal ------------------------------------------------------

    @staticmethod
    async def _call_handler(
        handler: Callable[..., Any],
        data: dict[str, Any],
    ) -> Any:
        """Call a handler, wrapping sync handlers in to_thread."""
        if asyncio.iscoroutinefunction(handler):
            return await handler(data)
        return await asyncio.to_thread(handler, data)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_hooks: HooksExtension | None = None


def get_hooks() -> HooksExtension:
    """Get the global hooks extension singleton."""
    global _hooks
    if _hooks is None:
        _hooks = HooksExtension()
    return _hooks
