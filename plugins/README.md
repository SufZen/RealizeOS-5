# Plugins Directory

This directory contains optional, community-contributed plugins for RealizeOS.

## Structure

```
plugins/
├── channels/          # Optional channel adapters (Telegram, WhatsApp, etc.)
│   ├── __init__.py
│   ├── telegram_plugin.py
│   ├── whatsapp_plugin.py
│   └── webhooks_plugin.py
└── README.md
```

## Channel Plugins

Channel plugins extend RealizeOS with additional messaging interfaces. Each channel
inherits from `realize_core.channels.base.BaseChannel` and can be loaded via the
plugin discovery system (ROS5-25).

### Available Channels

| Channel | File | Requires |
|---------|------|----------|
| Telegram | `telegram_plugin.py` | `TELEGRAM_BOT_TOKEN`, `python-telegram-bot` package |
| WhatsApp | `whatsapp_plugin.py` | `WHATSAPP_API_TOKEN`, WhatsApp Business API |
| Webhooks | `webhooks_plugin.py` | Webhook endpoint configuration |

### Usage

1. Install the required dependencies for your channel
2. Set the required environment variables
3. The plugin will be auto-discovered on startup if the `plugins/` directory is scanned

### Creating Custom Channels

See `realize_core/channels/base.py` for the `BaseChannel` abstract class.
Your custom channel must implement:

- `start()` — Initialize and begin listening
- `stop()` — Clean shutdown
- `send_message(message)` — Send an outgoing message
- `format_instructions()` — Return formatting rules for the LLM
