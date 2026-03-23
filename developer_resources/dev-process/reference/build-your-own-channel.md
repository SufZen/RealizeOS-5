# Build Your Own Channel Adapter

> **Time:** 15 minutes | **Prerequisites:** Python 3.11+, realize_core installed

## How Channels Work

A channel is a communication interface that connects users to the RealizeOS engine. Every channel follows the same flow:

```
User sends message → Channel receives → IncomingMessage → Engine processes → OutgoingMessage → Channel sends
```

## Step 1: Create Your Channel

Create a new file in `realize_core/channels/`:

```python
# realize_core/channels/discord.py
"""Discord channel adapter for RealizeOS."""
import logging
from realize_core.channels.base import BaseChannel, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


class DiscordChannel(BaseChannel):
    """Discord bot channel using discord.py."""

    def __init__(self, bot_token: str, system_key: str = ""):
        super().__init__("discord")
        self.bot_token = bot_token
        self.system_key = system_key
        self._client = None

    async def start(self):
        """Start the Discord bot."""
        try:
            import discord
            from discord.ext import commands

            intents = discord.Intents.default()
            intents.message_content = True
            self._client = commands.Bot(command_prefix="!", intents=intents)

            @self._client.event
            async def on_message(msg):
                if msg.author == self._client.user:
                    return
                await self._handle_message(msg)

            # Run in background (non-blocking)
            import asyncio
            asyncio.create_task(self._client.start(self.bot_token))
            self.logger.info("Discord channel starting")

        except ImportError:
            self.logger.error("discord.py not installed. Run: pip install discord.py")

    async def stop(self):
        """Stop the Discord bot."""
        if self._client:
            await self._client.close()
            self.logger.info("Discord channel stopped")

    async def send_message(self, message: OutgoingMessage):
        """Send a message to a Discord channel."""
        channel_id = message.metadata.get("channel_id")
        if self._client and channel_id:
            channel = self._client.get_channel(int(channel_id))
            if channel:
                # Split long messages (Discord limit: 2000 chars)
                text = message.text
                while text:
                    await channel.send(text[:2000])
                    text = text[2000:]

    def format_instructions(self) -> str:
        """Discord-specific formatting."""
        return (
            "Format for Discord. Use **bold** and *italic*. "
            "Use code blocks with ```language for code. "
            "Keep messages under 2000 characters. "
            "Use emojis sparingly for engagement."
        )

    async def _handle_message(self, msg):
        """Process an incoming Discord message."""
        message = IncomingMessage(
            user_id=str(msg.author.id),
            text=msg.content,
            system_key=self.system_key,
            channel="discord",
            metadata={
                "channel_id": msg.channel.id,
                "guild_id": getattr(msg.guild, "id", None),
                "author_name": str(msg.author),
            },
        )

        response = await self.handle_incoming(message)

        # Send response in the same channel
        text = response.text
        while text:
            await msg.channel.send(text[:2000])
            text = text[2000:]
```

## Step 2: Understand the Interface

Every channel must implement 4 methods:

| Method | Purpose |
| ------ | ------- |
| `start()` | Begin listening for messages |
| `stop()` | Stop gracefully |
| `send_message(msg)` | Send a response to the user |
| `format_instructions()` | Tell the LLM how to format for this channel |

### IncomingMessage

The standardized message format that channels produce:

```python
@dataclass
class IncomingMessage:
    user_id: str          # Who sent the message
    text: str             # The message text
    system_key: str       # Which system to route to
    channel: str          # Channel identifier
    topic_id: str         # Thread/topic (optional)
    image_data: bytes     # Attached image (optional)
    metadata: dict        # Channel-specific data
```

### OutgoingMessage

The standardized response format:

```python
@dataclass
class OutgoingMessage:
    text: str             # Response text
    user_id: str          # Who to send to
    channel: str          # Which channel
    metadata: dict        # Channel-specific routing data
    files: list           # Attached files
```

## Step 3: Register Your Channel

In your application startup:

```python
from realize_core.channels.discord import DiscordChannel

channel = DiscordChannel(bot_token="your-token", system_key="my-business")
await channel.start()
```

## Step 4: The Magic Method — handle_incoming()

You rarely need to override `handle_incoming()`. The base class does everything:

1. Takes your `IncomingMessage`
2. Routes through `engine.process_message()`
3. Returns an `OutgoingMessage`

Your channel just needs to convert platform-specific data to/from these formats.

## Existing Adapters

| Channel | File | Transport |
| ------- | ---- | --------- |
| Telegram | `telegram.py` | Polling / Webhook |
| WhatsApp | `whatsapp.py` | Webhook (Cloud API) |
| Web | `web.py` | REST + WebSocket |
| REST API | `api.py` | HTTP request/response |
| Webhook | `webhooks.py` | Inbound webhooks |
| Cron | `scheduler.py` | Timed execution |

## Tips

- **Keep channels thin** — all intelligence lives in the engine
- **Handle auth in the channel** — check user permissions before routing
- **Test with IncomingMessage** — you can unit-test by constructing messages directly
- **format_instructions() matters** — the LLM uses it to tailor responses
