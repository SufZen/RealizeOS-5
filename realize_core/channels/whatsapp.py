"""
WhatsApp channel adapter for RealizeOS.

Uses the WhatsApp Cloud API (Meta Business Platform) to receive and send messages.
Requires WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN.
"""

import hashlib
import hmac
import logging
import os
from typing import Any

from realize_core.channels.base import BaseChannel, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


class WhatsAppChannel(BaseChannel):
    """
    WhatsApp Business Cloud API channel.

    Receives messages via webhook (configured in Meta Business dashboard),
    sends responses via the Cloud API.

    Environment variables:
        WHATSAPP_PHONE_NUMBER_ID: Your WhatsApp phone number ID
        WHATSAPP_ACCESS_TOKEN: Permanent access token from Meta
        WHATSAPP_VERIFY_TOKEN: Webhook verification token (you choose)
        WHATSAPP_APP_SECRET: App secret for signature verification (optional)
    """

    GRAPH_API_VERSION = "v19.0"
    GRAPH_API_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    def __init__(
        self,
        phone_number_id: str = "",
        access_token: str = "",
        verify_token: str = "",
        app_secret: str = "",
        system_key: str = "",
    ):
        super().__init__("whatsapp")
        self.phone_number_id = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.access_token = access_token or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        self.verify_token = verify_token or os.getenv("WHATSAPP_VERIFY_TOKEN", "realize-os")
        self.app_secret = app_secret or os.getenv("WHATSAPP_APP_SECRET", "")
        self.system_key = system_key

    async def start(self):
        """WhatsApp channel is webhook-driven, start just validates config."""
        if not self.phone_number_id or not self.access_token:
            self.logger.warning("WhatsApp not configured: set WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN")
            return
        self.logger.info("WhatsApp channel ready (webhook mode)")

    async def stop(self):
        """No active connections to close for webhook mode."""
        self.logger.info("WhatsApp channel stopped")

    async def send_message(self, message: OutgoingMessage):
        """Send a message back via WhatsApp Cloud API."""
        import httpx

        recipient = message.metadata.get("wa_id") or message.user_id
        if not recipient:
            self.logger.error("No recipient for WhatsApp message")
            return

        url = f"{self.GRAPH_API_URL}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        # Split long messages (WhatsApp has a 4096 char limit)
        text = message.text
        chunks = _split_message(text, max_len=4096)

        async with httpx.AsyncClient(timeout=15) as client:
            for chunk in chunks:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "text",
                    "text": {"body": chunk},
                }
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    self.logger.error(f"WhatsApp send error: {e.response.status_code} {e.response.text[:200]}")
                except Exception as e:
                    self.logger.error(f"WhatsApp send error: {e}")

    def format_instructions(self) -> str:
        """WhatsApp-specific formatting rules."""
        return (
            "Format for WhatsApp messaging. Keep it conversational and concise. "
            "Use short paragraphs separated by blank lines. "
            "Use *bold* and _italic_ for emphasis. "
            "Use numbered lists (1. 2. 3.) for steps. "
            "Avoid markdown headers, tables, or code blocks — WhatsApp doesn't support them. "
            "Maximum 4096 characters per message."
        )

    # -----------------------------------------------------------------------
    # Webhook handling
    # -----------------------------------------------------------------------

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str | None:
        """
        Handle WhatsApp webhook verification (GET request from Meta).

        Returns challenge string if verified, None otherwise.
        """
        if mode == "subscribe" and token == self.verify_token:
            self.logger.info("WhatsApp webhook verified")
            return challenge
        self.logger.warning(f"WhatsApp webhook verification failed: mode={mode}")
        return None

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """
        Verify webhook payload signature using app secret.

        Meta sends X-Hub-Signature-256 header with each webhook.
        """
        if not self.app_secret:
            return True  # Skip verification if secret not configured

        expected = "sha256=" + hmac.new(self.app_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook(self, payload: dict[str, Any]) -> list[IncomingMessage]:
        """
        Parse a WhatsApp webhook payload into IncomingMessage objects.

        A single webhook can contain multiple messages.
        """
        messages: list[IncomingMessage] = []

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                if "messages" not in value:
                    continue

                contacts = {c["wa_id"]: c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}

                for msg in value.get("messages", []):
                    msg_type = msg.get("type", "")
                    wa_id = msg.get("from", "")

                    if msg_type == "text":
                        messages.append(
                            IncomingMessage(
                                user_id=wa_id,
                                text=msg.get("text", {}).get("body", ""),
                                system_key=self.system_key,
                                channel="whatsapp",
                                metadata={
                                    "wa_id": wa_id,
                                    "message_id": msg.get("id", ""),
                                    "timestamp": msg.get("timestamp", ""),
                                    "contact_name": contacts.get(wa_id, ""),
                                },
                            )
                        )
                    elif msg_type == "image":
                        # Image messages — store media ID for later download
                        image_info = msg.get("image", {})
                        caption = image_info.get("caption", "")
                        messages.append(
                            IncomingMessage(
                                user_id=wa_id,
                                text=caption or "[Image received]",
                                system_key=self.system_key,
                                channel="whatsapp",
                                image_media_type=image_info.get("mime_type", "image/jpeg"),
                                metadata={
                                    "wa_id": wa_id,
                                    "message_id": msg.get("id", ""),
                                    "media_id": image_info.get("id", ""),
                                    "contact_name": contacts.get(wa_id, ""),
                                },
                            )
                        )
                    # Other types (audio, document, etc.) can be added later

        return messages


def _split_message(text: str, max_len: int = 4096) -> list[str]:
    """Split a long message into chunks that fit WhatsApp's limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Try to break at a newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            # No good newline break, split at last space
            split_at = text.rfind(" ", 0, max_len)
        if split_at < max_len // 2:
            # No good space break, hard split
            split_at = max_len

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()

    return chunks
