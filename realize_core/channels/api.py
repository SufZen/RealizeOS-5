"""
REST API channel adapter for RealizeOS.

Exposes the engine as a FastAPI-compatible endpoint. This is the primary
channel for the web frontend and programmatic access.
"""

import logging

from realize_core.channels.base import BaseChannel, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


class APIChannel(BaseChannel):
    """
    REST API channel. Unlike Telegram or Slack, this channel doesn't
    actively listen — it's called by the FastAPI routes.
    """

    def __init__(self):
        super().__init__("api")

    async def start(self):
        """No-op for API channel — it's driven by HTTP requests."""
        self.logger.info("API channel ready")

    async def stop(self):
        """No-op for API channel."""
        self.logger.info("API channel stopped")

    async def send_message(self, message: OutgoingMessage):
        """API channel returns messages directly, no push mechanism."""
        # In the API context, messages are returned as HTTP responses
        # This method is here for interface compliance
        pass

    def format_instructions(self) -> str:
        """API channel: clean text output, no platform-specific formatting."""
        return (
            "Format your response as clean, readable text. "
            "You may use markdown for structure (headers, lists, bold, italic). "
            "Keep responses focused and well-organized."
        )

    async def process_chat(
        self,
        user_id: str,
        text: str,
        system_key: str = "",
        topic_id: str = "",
        image_data: bytes = b"",
        image_media_type: str = "",
    ) -> str:
        """
        Process a chat message and return the response text.

        This is the method called by FastAPI routes.
        """
        message = IncomingMessage(
            user_id=user_id,
            text=text,
            system_key=system_key,
            channel="api",
            topic_id=topic_id,
            image_data=image_data,
            image_media_type=image_media_type,
        )

        response = await self.handle_incoming(message)
        return response.text
