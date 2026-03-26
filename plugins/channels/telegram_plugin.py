"""
Telegram Channel Plugin for RealizeOS.

This plugin enables Telegram bot integration. It wraps the core
``realize_core.channels.telegram.TelegramChannel`` adapter as a
discoverable plugin.

Requirements:
    - ``python-telegram-bot`` package: ``pip install python-telegram-bot``
    - ``TELEGRAM_BOT_TOKEN`` environment variable

Configuration (in ``realize-os.yaml``):
    ```yaml
    channels:
      telegram:
        enabled: true
        bot_token: ${TELEGRAM_BOT_TOKEN}
        authorized_users: [123456789]
    ```
"""

from realize_core.channels.telegram import TelegramChannel

__all__ = ["TelegramChannel"]

# Plugin manifest (used by ROS5-25 Plugin Discovery)
PLUGIN_NAME = "telegram"
PLUGIN_TYPE = "channel"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Telegram bot channel for messaging"
PLUGIN_ENTRY = TelegramChannel
