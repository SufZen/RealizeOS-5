"""
WhatsApp Channel Plugin for RealizeOS.

This plugin enables WhatsApp Business API integration. It wraps the core
``realize_core.channels.whatsapp.WhatsAppChannel`` adapter as a
discoverable plugin.

Requirements:
    - ``WHATSAPP_API_TOKEN`` environment variable
    - ``WHATSAPP_PHONE_ID`` environment variable
    - WhatsApp Business API access

Configuration (in ``realize-os.yaml``):
    ```yaml
    channels:
      whatsapp:
        enabled: true
        api_token: ${WHATSAPP_API_TOKEN}
        phone_id: ${WHATSAPP_PHONE_ID}
    ```

Status: Experimental — requires WhatsApp Business API setup.
"""

from realize_core.channels.whatsapp import WhatsAppChannel

__all__ = ["WhatsAppChannel"]

# Plugin manifest (used by ROS5-25 Plugin Discovery)
PLUGIN_NAME = "whatsapp"
PLUGIN_TYPE = "channel"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "WhatsApp Business channel for messaging"
PLUGIN_ENTRY = WhatsAppChannel
