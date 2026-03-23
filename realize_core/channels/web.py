"""
Web channel adapter for RealizeOS with WebSocket support.

Extends APIChannel with real-time WebSocket streaming and connection management.
This is the primary channel for the web frontend.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from realize_core.channels.base import BaseChannel, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


@dataclass
class WebSocketClient:
    """Represents a connected WebSocket client."""

    client_id: str
    user_id: str
    connected_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class WebChannel(BaseChannel):
    """
    Web channel with REST + WebSocket support.

    - REST: Synchronous request/response via process_chat() (inherits from APIChannel pattern)
    - WebSocket: Real-time bidirectional communication for streaming responses
    """

    def __init__(self, system_key: str = ""):
        super().__init__("web")
        self.system_key = system_key
        self._ws_clients: dict[str, WebSocketClient] = {}
        self._ws_send_callbacks: dict[str, Any] = {}  # client_id → send function

    async def start(self):
        """Web channel is driven by HTTP server, start just logs."""
        self.logger.info("Web channel ready (REST + WebSocket)")

    async def stop(self):
        """Clean up WebSocket connections."""
        self._ws_clients.clear()
        self._ws_send_callbacks.clear()
        self.logger.info("Web channel stopped")

    async def send_message(self, message: OutgoingMessage):
        """Send message to a specific user via WebSocket if connected."""
        target_id = message.metadata.get("client_id")
        if target_id and target_id in self._ws_send_callbacks:
            send_fn = self._ws_send_callbacks[target_id]
            try:
                await send_fn(
                    json.dumps(
                        {
                            "type": "message",
                            "text": message.text,
                            "metadata": message.metadata,
                        }
                    )
                )
            except Exception as e:
                self.logger.error(f"WebSocket send error for {target_id}: {e}")
                await self.disconnect_client(target_id)

    def format_instructions(self) -> str:
        """Web channel: rich markdown output."""
        return (
            "Format your response as clean, readable markdown. "
            "Use headers (## ###) for organization. "
            "Use bullet points and numbered lists. "
            "Use **bold** and *italic* for emphasis. "
            "Use code blocks with language tags for code. "
            "Tables are supported. Keep responses well-structured."
        )

    # -----------------------------------------------------------------------
    # REST endpoint (same pattern as APIChannel)
    # -----------------------------------------------------------------------

    async def process_chat(
        self,
        user_id: str,
        text: str,
        system_key: str = "",
        topic_id: str = "",
        image_data: bytes = b"",
        image_media_type: str = "",
    ) -> str:
        """Process a chat message via REST and return the response text."""
        message = IncomingMessage(
            user_id=user_id,
            text=text,
            system_key=system_key or self.system_key,
            channel="web",
            topic_id=topic_id,
            image_data=image_data,
            image_media_type=image_media_type,
        )

        response = await self.handle_incoming(message)
        return response.text

    # -----------------------------------------------------------------------
    # WebSocket connection management
    # -----------------------------------------------------------------------

    async def connect_client(
        self,
        user_id: str,
        send_callback: Any,
        client_id: str = "",
    ) -> str:
        """
        Register a WebSocket client.

        Args:
            user_id: Authenticated user identifier
            send_callback: Async function to send messages to this client
            client_id: Optional client ID (generated if not provided)

        Returns:
            The client ID
        """
        cid = client_id or str(uuid.uuid4())[:12]
        self._ws_clients[cid] = WebSocketClient(
            client_id=cid,
            user_id=user_id,
        )
        self._ws_send_callbacks[cid] = send_callback
        self.logger.info(f"WebSocket client connected: {cid} (user={user_id})")
        return cid

    async def disconnect_client(self, client_id: str):
        """Remove a WebSocket client."""
        self._ws_clients.pop(client_id, None)
        self._ws_send_callbacks.pop(client_id, None)
        self.logger.info(f"WebSocket client disconnected: {client_id}")

    async def handle_ws_message(self, client_id: str, raw_data: str) -> str | None:
        """
        Handle an incoming WebSocket message.

        Expected format:
            {"type": "chat", "text": "Hello", "system_key": "my-business"}

        Returns response text or None if async (response sent via send_callback).
        """
        client = self._ws_clients.get(client_id)
        if not client:
            return json.dumps({"type": "error", "error": "Unknown client"})

        client.last_active = time.time()

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            return json.dumps({"type": "error", "error": "Invalid JSON"})

        msg_type = data.get("type", "chat")

        if msg_type == "ping":
            return json.dumps({"type": "pong"})

        if msg_type == "chat":
            message = IncomingMessage(
                user_id=client.user_id,
                text=data.get("text", ""),
                system_key=data.get("system_key", self.system_key),
                channel="web",
                metadata={"client_id": client_id},
            )

            response = await self.handle_incoming(message)

            # Send via callback
            send_fn = self._ws_send_callbacks.get(client_id)
            if send_fn:
                await send_fn(
                    json.dumps(
                        {
                            "type": "message",
                            "text": response.text,
                        }
                    )
                )
                return None  # Already sent

            return json.dumps({"type": "message", "text": response.text})

        return json.dumps({"type": "error", "error": f"Unknown message type: {msg_type}"})

    @property
    def connected_clients(self) -> int:
        return len(self._ws_clients)

    def get_client_info(self, client_id: str) -> dict | None:
        """Get info about a connected WebSocket client."""
        client = self._ws_clients.get(client_id)
        if not client:
            return None
        return {
            "client_id": client.client_id,
            "user_id": client.user_id,
            "connected_at": client.connected_at,
            "last_active": client.last_active,
        }
