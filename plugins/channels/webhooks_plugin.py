"""
Webhooks Channel Plugin for RealizeOS.

This plugin enables generic webhook integration. It wraps the core
``realize_core.channels.webhooks.WebhookChannel`` adapter as a
discoverable plugin, supporting both incoming and outgoing webhooks.

Requirements:
    - Webhook endpoint configuration

Configuration (in ``realize-os.yaml``):
    ```yaml
    channels:
      webhooks:
        enabled: true
        endpoints:
          - url: https://example.com/hook
            events: [skill_completed, agent_error]
    ```

Status: Experimental — API may change.
"""

from realize_core.channels.webhooks import WebhookChannel

__all__ = ["WebhookChannel"]

# Plugin manifest (used by ROS5-25 Plugin Discovery)
PLUGIN_NAME = "webhooks"
PLUGIN_TYPE = "channel"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "Generic webhook channel for integrations"
PLUGIN_ENTRY = WebhookChannel
