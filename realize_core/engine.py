"""
Channel-facing engine entry point.

Channel adapters (``realize_core/channels/*``) speak in terms of an incoming
message — user, text, optional venture key, attachments. This module turns
that into a call to :func:`realize_core.base_handler.process_message`,
loading the same configuration the API server loads at startup
(``realize-os.yaml``, systems dict, shared config, feature flags).

Configuration is read on every call so edits made through the dashboard's
settings pages take effect for channels without a restart.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DEFAULT_SHARED = {
    "identity": "shared/identity.md",
    "preferences": "shared/user-preferences.md",
}


def _resolve_system_key(requested: str, systems: dict) -> str | None:
    """Pick the venture for a channel message.

    Uses the requested key when configured; otherwise falls back to the only
    configured venture (single-venture installs) and ``None`` when ambiguous.
    """
    if requested and requested in systems:
        return requested
    if len(systems) == 1:
        return next(iter(systems))
    return None


async def process_message(
    user_id: str,
    text: str,
    system_key: str = "",
    channel: str = "api",
    topic_id: str = "",
    image_data: bytes = b"",
    image_media_type: str = "",
) -> str:
    """Process a channel message through the full RealizeOS pipeline.

    Args:
        user_id: Channel-scoped user identifier.
        text: Message text.
        system_key: Venture to route to; optional on single-venture installs.
        channel: Channel name (telegram, web, webhook, ...).
        topic_id: Thread/topic identifier (currently informational).
        image_data: Attached image bytes (not yet supported by the pipeline).
        image_media_type: MIME type of ``image_data``.

    Returns:
        The response text to send back on the channel.
    """
    from realize_core.base_handler import process_message as _process
    from realize_core.config import KB_PATH, build_systems_dict, get_features, load_config

    config = load_config()
    systems = build_systems_dict(config, KB_PATH)
    resolved = _resolve_system_key(system_key, systems)
    if resolved is None:
        if not systems:
            return "RealizeOS has no ventures configured yet. Run setup first."
        return f"Please choose a venture: {', '.join(sorted(systems))}."

    if image_data:
        logger.info("Channel %s sent an image; image input is not supported yet and was ignored", channel)
    if topic_id:
        logger.debug("Channel %s message in topic %s", channel, topic_id)

    return await _process(
        system_key=resolved,
        user_id=user_id,
        message=text,
        kb_path=KB_PATH,
        system_config=systems[resolved],
        shared_config=config.get("shared", _DEFAULT_SHARED),
        channel=channel,
        features=get_features(config),
        all_systems=systems,
    )
