"""
Abstract base class for RealizeOS channels.

A channel is a communication interface (Telegram, REST API, Slack, Discord, CLI, etc.)
that receives messages from users and sends responses back. Each channel handles its
own formatting, authentication, and transport — but delegates all intelligence to the core engine.
"""

import abc
import logging
import re
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# XSS sanitisation — strip dangerous HTML from outbound text
# ---------------------------------------------------------------------------

_DANGEROUS_TAG_RE = re.compile(
    r"<\s*/?\s*(script|iframe|object|embed|form|base|link|meta|style)\b[^>]*>",
    re.IGNORECASE,
)
_EVENT_HANDLER_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
_JAVASCRIPT_URI_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


def _sanitize_text(text: str) -> str:
    """Strip script/iframe tags, event handlers, and javascript: URIs."""
    text = _DANGEROUS_TAG_RE.sub("", text)
    text = _EVENT_HANDLER_RE.sub("", text)
    text = _JAVASCRIPT_URI_RE.sub("", text)
    return text


def _generate_message_id() -> str:
    """Generate a short unique message ID."""
    return uuid.uuid4().hex[:16]


@dataclass
class IncomingMessage:
    """Standardized incoming message from any channel."""

    user_id: str
    text: str
    message_id: str = ""  # Auto-generated if empty
    system_key: str = ""  # Which system to route to (if known)
    channel: str = "api"  # Channel identifier (telegram, api, slack, etc.)
    topic_id: str = ""  # Thread/topic ID (for forums, groups)
    image_data: bytes = b""  # Attached image bytes (if any)
    image_media_type: str = ""  # MIME type of attached image
    file_data: bytes = b""  # Attached file bytes (if any)
    file_name: str = ""  # Attached file name
    metadata: dict = field(default_factory=dict)  # Channel-specific metadata

    def __post_init__(self):
        if not self.message_id:
            self.message_id = _generate_message_id()


@dataclass
class OutgoingMessage:
    """Standardized outgoing response to any channel."""

    text: str
    user_id: str
    message_id: str = ""  # Auto-generated if empty
    channel: str = "api"
    metadata: dict = field(default_factory=dict)  # Channel-specific metadata
    files: list = field(default_factory=list)  # Attached files to send back

    def __post_init__(self):
        if not self.message_id:
            self.message_id = _generate_message_id()


class BaseChannel(abc.ABC):
    """
    Abstract base class for all RealizeOS channels.

    Subclasses must implement:
    - start(): Begin listening for messages
    - stop(): Stop listening
    - send_message(): Send a response back to the user
    - format_instructions(): Return channel-specific formatting rules for prompt builder
    """

    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        self.logger = logging.getLogger(f"realize.channel.{channel_name}")

    @abc.abstractmethod
    async def start(self):
        """Start the channel (begin listening for messages)."""
        ...

    @abc.abstractmethod
    async def stop(self):
        """Stop the channel gracefully."""
        ...

    @abc.abstractmethod
    async def send_message(self, message: OutgoingMessage):
        """Send a response back to the user through this channel."""
        ...

    def format_instructions(self) -> str:
        """
        Return channel-specific formatting instructions to include in the system prompt.

        Override in subclasses to customize how agents format their responses
        for this particular channel (e.g., Telegram has markdown limitations,
        Slack uses mrkdwn, API returns raw text).
        """
        return ""

    def health_check(self) -> dict:
        """
        Return channel health status.

        Override in subclasses to add channel-specific health indicators.
        Returns dict with at minimum: {"name": str, "healthy": bool, "details": dict}
        """
        return {
            "name": self.channel_name,
            "healthy": True,
            "details": {},
        }

    async def handle_incoming(self, message: IncomingMessage) -> OutgoingMessage:
        """
        Process an incoming message through the RealizeOS engine.

        This is the main entry point that channels call when they receive a message.
        It routes through the core engine and returns a formatted response.

        Override this method to add channel-specific pre/post processing.
        """
        from realize_core.engine import process_message

        response_text = await process_message(
            user_id=message.user_id,
            text=message.text,
            system_key=message.system_key,
            channel=self.channel_name,
            topic_id=message.topic_id,
            image_data=message.image_data,
            image_media_type=message.image_media_type,
        )

        return OutgoingMessage(
            text=_sanitize_text(response_text),
            user_id=message.user_id,
            channel=self.channel_name,
        )
