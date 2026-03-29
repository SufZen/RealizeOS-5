"""
Telegram channel adapter for RealizeOS.

Wraps python-telegram-bot to receive and send messages via Telegram.
This is an optional channel — requires TELEGRAM_BOT_TOKEN.
"""

import logging

from realize_core.channels.base import BaseChannel, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)

# Telegram's maximum message length
_TELEGRAM_MAX_LENGTH = 4096


def _split_telegram_message(text: str, max_len: int = _TELEGRAM_MAX_LENGTH) -> list[str]:
    """Split a long message into chunks that fit Telegram's limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = text.rfind(" ", 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()

    return chunks


class TelegramChannel(BaseChannel):
    """
    Telegram bot channel using python-telegram-bot library.

    Supports polling mode (for development) and webhook mode (for production).
    """

    def __init__(self, bot_token: str, system_key: str = "", authorized_users: set = None):
        super().__init__("telegram")
        self.bot_token = bot_token
        self.system_key = system_key
        self.authorized_users = authorized_users or set()
        self._application = None
        self._started = False  # Guard against double-polling

    async def start(self):
        """Start the Telegram bot in polling mode."""
        if self._started:
            self.logger.warning("Telegram bot already started — ignoring duplicate start()")
            return

        try:
            from telegram.ext import ApplicationBuilder, MessageHandler, filters

            self._application = ApplicationBuilder().token(self.bot_token).build()

            # Register message handler
            self._application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_telegram_message)
            )

            self.logger.info("Telegram channel starting (polling mode)")
            await self._application.initialize()
            await self._application.start()
            await self._application.updater.start_polling()
            self._started = True

        except ImportError:
            self.logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
        except Exception as e:
            self.logger.error(f"Failed to start Telegram bot: {e}")

    async def stop(self):
        """Stop the Telegram bot."""
        if self._application and self._started:
            try:
                await self._application.updater.stop()
                await self._application.stop()
                await self._application.shutdown()
            except Exception as e:
                self.logger.error(f"Error stopping Telegram bot: {e}")
            finally:
                self._started = False
            self.logger.info("Telegram channel stopped")

    async def send_message(self, message: OutgoingMessage):
        """Send a message back via Telegram, splitting if necessary."""
        if not self._application or not message.metadata.get("chat_id"):
            return

        chat_id = message.metadata["chat_id"]
        chunks = _split_telegram_message(message.text)

        for chunk in chunks:
            try:
                await self._application.bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode="Markdown",
                )
            except Exception:
                # Retry without parse_mode if Markdown fails
                try:
                    await self._application.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                    )
                except Exception as retry_e:
                    self.logger.error(f"Telegram send error for chat {chat_id}: {retry_e}")

    def format_instructions(self) -> str:
        """Telegram-specific formatting rules."""
        return (
            "Format your response for Telegram messaging. Keep it conversational. "
            "Use short paragraphs. Avoid markdown headers (# ##). "
            "Use *bold* and _italic_ sparingly. "
            "Use bullet points (- ) for lists. Keep responses under 4000 characters."
        )

    def health_check(self) -> dict:
        """Return Telegram channel health status."""
        return {
            "name": self.channel_name,
            "healthy": self._started,
            "details": {
                "started": self._started,
                "has_application": self._application is not None,
            },
        }

    async def _handle_telegram_message(self, update, context):
        """Handle an incoming Telegram message."""
        if not update.message or not update.message.text:
            return

        user_id = str(update.message.from_user.id)

        # Authorization check
        if self.authorized_users and int(user_id) not in self.authorized_users:
            await update.message.reply_text("Unauthorized. Contact the system administrator.")
            return

        message = IncomingMessage(
            user_id=user_id,
            text=update.message.text,
            system_key=self.system_key,
            channel="telegram",
            topic_id=str(update.message.message_thread_id or ""),
            metadata={"chat_id": update.message.chat_id},
        )

        response = await self.handle_incoming(message)

        # Split and send response
        chunks = _split_telegram_message(response.text)
        for chunk in chunks:
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except Exception:
                # Fallback without parse_mode
                try:
                    await update.message.reply_text(chunk)
                except Exception as e:
                    self.logger.error(f"Telegram reply failed: {e}")
