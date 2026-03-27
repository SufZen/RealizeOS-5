"""
WhatsApp channel adapter for RealizeOS.

Uses the WhatsApp Cloud API (Meta Business Platform) to receive and send messages.
Requires WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN.
"""

import hashlib
import hmac
import logging
import os
import time
from collections import OrderedDict
from typing import Any

from realize_core.channels.base import BaseChannel, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)

# Maximum number of message IDs to remember for deduplication
_DEDUP_MAX_SIZE = 10_000
# How long (seconds) to keep a message ID for dedup
_DEDUP_TTL = 600  # 10 minutes


class _BoundedTTLSet:
    """A bounded set with TTL-based expiry for message deduplication."""

    def __init__(self, max_size: int = _DEDUP_MAX_SIZE, ttl: float = _DEDUP_TTL):
        self._data: OrderedDict[str, float] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def add(self, key: str) -> bool:
        """Add key. Returns True if it was new (not a duplicate)."""
        now = time.time()
        self._evict(now)
        if key in self._data:
            return False  # Duplicate
        self._data[key] = now
        if len(self._data) > self._max_size:
            self._data.popitem(last=False)
        return True

    def _evict(self, now: float):
        while self._data:
            oldest_key, oldest_ts = next(iter(self._data.items()))
            if now - oldest_ts > self._ttl:
                self._data.popitem(last=False)
            else:
                break

    def __len__(self) -> int:
        return len(self._data)


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
        self._seen_messages = _BoundedTTLSet()

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
                    self._handle_api_error(e.response.status_code, e.response.text[:300])
                except Exception as e:
                    self.logger.error(f"WhatsApp send error: {e}")

    def _handle_api_error(self, status_code: int, body: str):
        """Map WhatsApp API error codes to actionable log messages."""
        if "131047" in body:
            self.logger.error("WhatsApp rate limit exceeded — throttle outbound messages")
        elif "131026" in body:
            self.logger.error("WhatsApp recipient not registered on WhatsApp")
        elif "131051" in body:
            self.logger.error("WhatsApp media upload failed")
        elif status_code == 401:
            self.logger.error("WhatsApp access token invalid or expired — refresh required")
        else:
            self.logger.error(f"WhatsApp API error {status_code}: {body}")

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

    def health_check(self) -> dict:
        """Return WhatsApp channel health status."""
        configured = bool(self.phone_number_id and self.access_token)
        return {
            "name": self.channel_name,
            "healthy": configured,
            "details": {
                "configured": configured,
                "has_app_secret": bool(self.app_secret),
                "dedup_cache_size": len(self._seen_messages),
            },
        }

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
        Automatically deduplicates messages by their WhatsApp message ID.
        """
        messages: list[IncomingMessage] = []

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                if "messages" not in value:
                    continue

                contacts = {c["wa_id"]: c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}

                for msg in value.get("messages", []):
                    msg_id = msg.get("id", "")
                    msg_type = msg.get("type", "")
                    wa_id = msg.get("from", "")

                    # Deduplicate: skip if we've already seen this message
                    if msg_id and not self._seen_messages.add(msg_id):
                        self.logger.debug(f"Skipping duplicate WhatsApp message: {msg_id}")
                        continue

                    if msg_type == "text":
                        messages.append(
                            IncomingMessage(
                                user_id=wa_id,
                                text=msg.get("text", {}).get("body", ""),
                                system_key=self.system_key,
                                channel="whatsapp",
                                metadata={
                                    "wa_id": wa_id,
                                    "message_id": msg_id,
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
                                    "message_id": msg_id,
                                    "media_id": image_info.get("id", ""),
                                    "contact_name": contacts.get(wa_id, ""),
                                },
                            )
                        )
                    # Other types (audio, document, etc.) can be added later

        return messages

    async def download_media(self, media_id: str) -> bytes | None:
        """
        Download media from WhatsApp by media ID.

        Returns raw bytes of the media file, or None on failure.
        """
        import httpx

        if not media_id or not self.access_token:
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Step 1: Get the media URL
                meta_resp = await client.get(
                    f"{self.GRAPH_API_URL}/{media_id}",
                    headers=headers,
                )
                meta_resp.raise_for_status()
                media_url = meta_resp.json().get("url")
                if not media_url:
                    return None

                # Step 2: Download the actual file
                file_resp = await client.get(media_url, headers=headers)
                file_resp.raise_for_status()
                return file_resp.content
        except Exception as e:
            self.logger.error(f"Failed to download WhatsApp media {media_id}: {e}")
            return None


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

