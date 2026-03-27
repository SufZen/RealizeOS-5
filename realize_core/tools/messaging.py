"""
Agent-to-Agent Messaging Bus — Inter-agent communication system.

Provides a ``MessageTool`` that enables agents to:
- Send messages to other agents, humans, or channels
- Read messages from their inbox
- List conversations
- Create named channels for broadcast

Messages addressed to offline agents are queued and delivered
at their next session start. Human-targeted messages appear in
the dashboard as approval requests.

Targeting syntax:
- ``agent:<slug>`` — direct message to an agent
- ``human:default`` — message to the human operator
- ``channel:<name>`` — broadcast to a named channel
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from realize_core.tools.base_tool import (
    BaseTool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)

logger = logging.getLogger(__name__)


class MessageTarget(StrEnum):
    """Types of message targets."""

    AGENT = "agent"
    HUMAN = "human"
    CHANNEL = "channel"


class MessageStatus(StrEnum):
    """Message delivery status."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    QUEUED = "queued"  # Recipient offline
    FAILED = "failed"


class Message:
    """Represents an inter-agent message."""

    def __init__(
        self,
        sender: str,
        target: str,
        content: str,
        system_key: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        self.id = str(uuid.uuid4())
        self.sender = sender
        self.target = target
        self.target_type, self.target_id = self._parse_target(target)
        self.content = content
        self.system_key = system_key
        self.status = MessageStatus.SENT
        self.created_at = datetime.now(UTC)
        self.delivered_at: datetime | None = None
        self.read_at: datetime | None = None
        self.metadata = metadata or {}

    @staticmethod
    def _parse_target(target: str) -> tuple[MessageTarget, str]:
        """Parse 'agent:writer' into (MessageTarget.AGENT, 'writer')."""
        if ":" not in target:
            return MessageTarget.AGENT, target

        prefix, identifier = target.split(":", 1)
        try:
            return MessageTarget(prefix.lower()), identifier
        except ValueError:
            return MessageTarget.AGENT, target

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "target": self.target,
            "target_type": self.target_type.value,
            "target_id": self.target_id,
            "content": self.content,
            "system_key": self.system_key,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        msg = cls(
            sender=data["sender"],
            target=data["target"],
            content=data["content"],
            system_key=data.get("system_key", ""),
        )
        msg.id = data["id"]
        msg.status = MessageStatus(data.get("status", "sent"))
        msg.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("delivered_at"):
            msg.delivered_at = datetime.fromisoformat(data["delivered_at"])
        if data.get("read_at"):
            msg.read_at = datetime.fromisoformat(data["read_at"])
        msg.metadata = data.get("metadata", {})
        return msg


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------


class Channel:
    """Named broadcast channel that multiple agents can subscribe to."""

    def __init__(self, name: str, system_key: str, created_by: str):
        self.id = str(uuid.uuid4())
        self.name = name
        self.system_key = system_key
        self.created_by = created_by
        self.subscribers: set[str] = {created_by}
        self.created_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "system_key": self.system_key,
            "created_by": self.created_by,
            "subscribers": list(self.subscribers),
            "created_at": self.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Message Store
# ---------------------------------------------------------------------------


class MessageStore:
    """In-memory message store with optional DB persistence."""

    def __init__(self):
        self._messages: list[Message] = []
        self._channels: dict[str, Channel] = {}
        self._queues: dict[str, list[Message]] = {}  # agent_key → queued msgs

    def send(self, message: Message) -> Message:
        """Store a message and queue if recipient is offline."""
        self._messages.append(message)

        if message.target_type == MessageTarget.CHANNEL:
            # Broadcast to channel subscribers
            channel = self._channels.get(message.target_id)
            if channel:
                for subscriber in channel.subscribers:
                    if subscriber != message.sender:
                        self._queue_for_agent(subscriber, message)
            message.status = MessageStatus.DELIVERED
        elif message.target_type == MessageTarget.AGENT:
            self._queue_for_agent(message.target_id, message)
            message.status = MessageStatus.QUEUED
        elif message.target_type == MessageTarget.HUMAN:
            message.status = MessageStatus.DELIVERED

        return message

    def _queue_for_agent(self, agent_key: str, message: Message):
        """Queue a message for an agent."""
        if agent_key not in self._queues:
            self._queues[agent_key] = []
        self._queues[agent_key].append(message)

    def get_inbox(
        self,
        agent_key: str,
        limit: int = 20,
        unread_only: bool = False,
    ) -> list[Message]:
        """Get messages for an agent (direct + channel subscriptions)."""
        msgs = []
        for msg in self._messages:
            is_direct = (
                msg.target_type == MessageTarget.AGENT
                and msg.target_id == agent_key
            )
            is_subscriber = False
            if msg.target_type == MessageTarget.CHANNEL:
                # Find channel by name (keys are "system_key:name")
                for channel in self._channels.values():
                    if channel.name == msg.target_id and agent_key in channel.subscribers:
                        is_subscriber = True
                        break

            if (is_direct or is_subscriber) and msg.sender != agent_key:
                if unread_only and msg.read_at is not None:
                    continue
                msgs.append(msg)

        return sorted(msgs, key=lambda m: m.created_at, reverse=True)[:limit]

    def mark_read(self, message_id: str) -> bool:
        """Mark a message as read."""
        for msg in self._messages:
            if msg.id == message_id and msg.read_at is None:
                msg.read_at = datetime.now(UTC)
                msg.status = MessageStatus.READ
                return True
        return False

    def get_queued_messages(self, agent_key: str) -> list[Message]:
        """Get and flush queued messages for an agent."""
        queued = self._queues.pop(agent_key, [])
        for msg in queued:
            msg.status = MessageStatus.DELIVERED
            msg.delivered_at = datetime.now(UTC)
        return queued

    def create_channel(
        self, name: str, system_key: str, created_by: str,
    ) -> Channel:
        """Create a named channel."""
        channel_key = f"{system_key}:{name}"
        if channel_key in self._channels:
            return self._channels[channel_key]
        channel = Channel(name=name, system_key=system_key, created_by=created_by)
        self._channels[channel_key] = channel
        return channel

    def subscribe_to_channel(self, channel_name: str, system_key: str, agent_key: str) -> bool:
        """Subscribe an agent to a channel."""
        channel_key = f"{system_key}:{channel_name}"
        channel = self._channels.get(channel_key)
        if channel:
            channel.subscribers.add(agent_key)
            return True
        return False

    def get_conversations(self, agent_key: str) -> list[dict[str, Any]]:
        """Get a list of conversations (unique senders) for an agent."""
        conversations: dict[str, dict[str, Any]] = {}
        for msg in self._messages:
            is_direct = (
                msg.target_type == MessageTarget.AGENT
                and msg.target_id == agent_key
            )
            if is_direct:
                key = msg.sender
                if key not in conversations:
                    conversations[key] = {
                        "with": key,
                        "type": "direct",
                        "last_message": msg.content[:100],
                        "last_at": msg.created_at.isoformat(),
                        "count": 0,
                    }
                conversations[key]["count"] += 1
                conversations[key]["last_message"] = msg.content[:100]
                conversations[key]["last_at"] = msg.created_at.isoformat()
        return list(conversations.values())


# ---------------------------------------------------------------------------
# MessageTool (BaseTool implementation)
# ---------------------------------------------------------------------------


class MessageTool(BaseTool):
    """
    Tool for inter-agent communication.

    Enables agents to send messages, read inbox, list conversations,
    and create channels for broadcast communication.
    """

    def __init__(self, store: MessageStore | None = None):
        self._store = store or MessageStore()

    @property
    def name(self) -> str:
        return "messaging"

    @property
    def description(self) -> str:
        return "Send and receive messages between agents and to humans"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.COMMUNICATION

    def is_available(self) -> bool:
        return True

    def get_schemas(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="send_message",
                description=(
                    "Send a message to another agent, a human operator, or a channel. "
                    "Target format: 'agent:<slug>', 'human:default', or 'channel:<name>'."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Message target (e.g. 'agent:writer', 'human:default')",
                        },
                        "content": {
                            "type": "string",
                            "description": "Message content",
                        },
                    },
                    "required": ["target", "content"],
                },
                category=ToolCategory.COMMUNICATION,
                is_destructive=True,
            ),
            ToolSchema(
                name="read_messages",
                description="Read messages from your inbox.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum messages to return (default: 10)",
                            "default": 10,
                        },
                        "unread_only": {
                            "type": "boolean",
                            "description": "Only return unread messages",
                            "default": False,
                        },
                    },
                },
                category=ToolCategory.COMMUNICATION,
                is_destructive=False,
            ),
            ToolSchema(
                name="list_conversations",
                description="List all conversations you have with other agents.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                category=ToolCategory.COMMUNICATION,
                is_destructive=False,
            ),
            ToolSchema(
                name="create_channel",
                description="Create a named broadcast channel that agents can subscribe to.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Channel name",
                        },
                    },
                    "required": ["name"],
                },
                category=ToolCategory.COMMUNICATION,
                is_destructive=True,
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        """Execute a messaging action."""
        if action == "send_message":
            return self._send_message(params)
        elif action == "read_messages":
            return self._read_messages(params)
        elif action == "list_conversations":
            return self._list_conversations(params)
        elif action == "create_channel":
            return self._create_channel(params)
        else:
            return ToolResult.fail(f"Unknown messaging action: {action}")

    def _send_message(self, params: dict[str, Any]) -> ToolResult:
        target = params.get("target", "")
        content = params.get("content", "")
        if not target or not content:
            return ToolResult.fail("Both 'target' and 'content' are required")

        message = Message(
            sender=params.get("agent_key", "unknown"),
            target=target,
            content=content,
            system_key=params.get("system_key", "default"),
        )
        self._store.send(message)

        logger.info("Message sent: %s → %s", message.sender, message.target)
        return ToolResult.ok(
            output=f"✉️ Message sent to {target} (ID: {message.id})",
            data=message.to_dict(),
        )

    def _read_messages(self, params: dict[str, Any]) -> ToolResult:
        agent_key = params.get("agent_key", "unknown")
        limit = params.get("limit", 10)
        unread_only = params.get("unread_only", False)

        messages = self._store.get_inbox(agent_key, limit=limit, unread_only=unread_only)

        # Mark as read
        for msg in messages:
            self._store.mark_read(msg.id)

        return ToolResult.ok(
            output=f"📬 {len(messages)} message(s) in inbox",
            data=[m.to_dict() for m in messages],
        )

    def _list_conversations(self, params: dict[str, Any]) -> ToolResult:
        agent_key = params.get("agent_key", "unknown")
        conversations = self._store.get_conversations(agent_key)
        return ToolResult.ok(
            output=f"💬 {len(conversations)} conversation(s)",
            data=conversations,
        )

    def _create_channel(self, params: dict[str, Any]) -> ToolResult:
        name = params.get("name", "")
        if not name:
            return ToolResult.fail("Channel 'name' is required")

        channel = self._store.create_channel(
            name=name,
            system_key=params.get("system_key", "default"),
            created_by=params.get("agent_key", "unknown"),
        )
        return ToolResult.ok(
            output=f"📢 Channel '{name}' created (ID: {channel.id})",
            data=channel.to_dict(),
        )

    @property
    def store(self) -> MessageStore:
        return self._store


def get_tool() -> MessageTool:
    """Factory function for auto-discovery."""
    return MessageTool()
