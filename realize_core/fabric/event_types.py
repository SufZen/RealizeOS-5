"""
FABRIC Event Types.

Typed event definitions for the RealizeOS event log.
Every action, decision, mission state change, channel event, and dream
proposal is recorded as a typed event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventCategory(str, Enum):
    """Top-level event categories."""

    MESSAGE = "message"
    MISSION = "mission"
    KNOWLEDGE = "knowledge"
    CHANNEL = "channel"
    DREAMING = "dreaming"
    SYSTEM = "system"
    APPROVAL = "approval"
    AGENT = "agent"
    RUNTIME = "runtime"
    ERROR = "error"


@dataclass
class Event:
    """
    A single event in the RealizeOS event log.

    Every event has a category, action, actor, and optional structured payload.
    Events are append-only and immutable once written.
    """

    # Identity
    event_id: str = ""
    timestamp: str = ""  # ISO 8601; auto-set if empty

    # Classification
    category: str = ""  # EventCategory value
    action: str = ""  # Specific action within the category

    # Actor
    actor: str = ""  # Who caused this event (user-*, agent-*, system, dream-*)
    actor_type: str = ""  # "user" | "agent" | "system" | "runtime"

    # Scope
    venture: str = ""  # Venture this event belongs to
    mission_id: str = ""  # Mission context if applicable
    entity_id: str = ""  # Entity context if applicable

    # Payload
    payload: dict = field(default_factory=dict)

    # Audit
    channel: str = ""  # Which channel (api, telegram, web, cli, etc.)
    session_id: str = ""  # Session identifier for grouping

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.event_id:
            import uuid
            self.event_id = uuid.uuid4().hex[:16]

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "category": self.category,
            "action": self.action,
            "actor": self.actor,
            "actor_type": self.actor_type,
            "venture": self.venture,
            "mission_id": self.mission_id,
            "entity_id": self.entity_id,
            "payload": self.payload,
            "channel": self.channel,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        """Deserialize from dict."""
        return cls(
            event_id=data.get("event_id", ""),
            timestamp=data.get("timestamp", ""),
            category=data.get("category", ""),
            action=data.get("action", ""),
            actor=data.get("actor", ""),
            actor_type=data.get("actor_type", ""),
            venture=data.get("venture", ""),
            mission_id=data.get("mission_id", ""),
            entity_id=data.get("entity_id", ""),
            payload=data.get("payload", {}),
            channel=data.get("channel", ""),
            session_id=data.get("session_id", ""),
        )


# ─── Convenience constructors ────────────────────────────────────────────────

def message_event(
    actor: str,
    venture: str = "",
    channel: str = "api",
    text: str = "",
    agent: str = "",
    direction: str = "inbound",
) -> Event:
    """Create a message event (user→agent or agent→user)."""
    return Event(
        category=EventCategory.MESSAGE,
        action=f"message.{direction}",
        actor=actor,
        actor_type="user" if actor.startswith("user-") else "agent",
        venture=venture,
        channel=channel,
        payload={"text": text[:500], "agent": agent, "direction": direction},
    )


def mission_event(
    mission_id: str,
    action: str,
    actor: str = "system",
    venture: str = "",
    **payload,
) -> Event:
    """Create a mission lifecycle event."""
    return Event(
        category=EventCategory.MISSION,
        action=f"mission.{action}",
        actor=actor,
        actor_type="system",
        venture=venture,
        mission_id=mission_id,
        payload=payload,
    )


def knowledge_event(
    entity_id: str,
    action: str,
    actor: str = "",
    venture: str = "",
    **payload,
) -> Event:
    """Create a knowledge/FABRIC event."""
    return Event(
        category=EventCategory.KNOWLEDGE,
        action=f"knowledge.{action}",
        actor=actor,
        actor_type="agent" if actor.startswith("agent-") else "user",
        venture=venture,
        entity_id=entity_id,
        payload=payload,
    )


def dream_event(
    action: str,
    cycle_type: str = "",
    actor: str = "system",
    venture: str = "",
    **payload,
) -> Event:
    """Create a dreaming subsystem event."""
    return Event(
        category=EventCategory.DREAMING,
        action=f"dreaming.{action}",
        actor=actor,
        actor_type="system",
        venture=venture,
        payload={"cycle_type": cycle_type, **payload},
    )


def runtime_event(
    runtime_id: str,
    action: str,
    **payload,
) -> Event:
    """Create a runtime lifecycle event."""
    return Event(
        category=EventCategory.RUNTIME,
        action=f"runtime.{action}",
        actor=f"runtime-{runtime_id}",
        actor_type="runtime",
        payload={"runtime_id": runtime_id, **payload},
    )
