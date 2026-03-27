"""
Webhook Ingestion: Receives and routes inbound webhooks.

Supports:
- Webhook registration with optional secret-based verification
- Payload transformation to IncomingMessage
- Routing webhooks through the engine as system messages
- Outgoing webhook delivery with retry logic
"""

import hashlib
import hmac
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from realize_core.channels.base import BaseChannel, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)

# Replay attack prevention settings
_TIMESTAMP_TOLERANCE = 300  # 5 minutes
_NONCE_MAX_SIZE = 10_000


class _BoundedNonceSet:
    """Bounded set to track seen nonces for replay-attack prevention."""

    def __init__(self, max_size: int = _NONCE_MAX_SIZE):
        self._data: OrderedDict[str, float] = OrderedDict()
        self._max_size = max_size

    def check_and_add(self, nonce: str) -> bool:
        """Returns True if nonce is new (not a replay). False if seen before."""
        if nonce in self._data:
            return False
        self._data[nonce] = time.time()
        if len(self._data) > self._max_size:
            self._data.popitem(last=False)
        return True

    def __len__(self) -> int:
        return len(self._data)


@dataclass
class WebhookEndpoint:
    """A registered webhook endpoint."""

    name: str
    system_key: str
    secret: str = ""  # HMAC secret for signature verification
    enabled: bool = True
    message_template: str = ""  # Template for converting payload to message
    last_received: float = 0.0
    receive_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """Verify HMAC-SHA256 signature."""
        if not self.secret:
            return True  # No secret configured, skip verification

        expected = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()

        # Support both raw and prefixed signatures
        sig_clean = signature.replace("sha256=", "")
        return hmac.compare_digest(expected, sig_clean)

    def format_payload(self, payload: dict) -> str:
        """
        Convert a webhook payload to a human-readable message.

        If message_template is set, uses it for formatting.
        Otherwise, creates a structured summary.
        """
        if self.message_template:
            try:
                return self.message_template.format(**payload)
            except (KeyError, ValueError):
                pass

        # Default: summarize the payload
        lines = [f"Webhook received: {self.name}"]
        for key, value in payload.items():
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"  {key}: {value}")
            elif isinstance(value, dict):
                lines.append(f"  {key}: {{{len(value)} fields}}")
            elif isinstance(value, list):
                lines.append(f"  {key}: [{len(value)} items]")
        return "\n".join(lines)


class WebhookChannel(BaseChannel):
    """
    Webhook ingestion channel.

    Receives incoming webhooks, verifies signatures, transforms payloads
    into messages, and routes them through the engine.
    """

    def __init__(self, system_key: str = ""):
        super().__init__("webhook")
        self.system_key = system_key
        self._endpoints: dict[str, WebhookEndpoint] = {}
        self._seen_nonces = _BoundedNonceSet()

    async def start(self):
        """Webhook channel is driven by HTTP server."""
        self.logger.info(f"Webhook channel ready ({len(self._endpoints)} endpoints)")

    async def stop(self):
        self.logger.info("Webhook channel stopped")

    async def send_message(self, message: OutgoingMessage):
        """Webhooks are inbound-only; no outbound mechanism."""
        self.logger.debug("Webhook channel does not support outbound messages")

    def format_instructions(self) -> str:
        return (
            "This message came from a webhook. Analyze the data and "
            "take appropriate action. Respond with a structured summary "
            "of what happened and any actions taken."
        )

    def health_check(self) -> dict:
        """Return webhook channel health status."""
        return {
            "name": self.channel_name,
            "healthy": True,
            "details": {
                "total_endpoints": self.endpoint_count,
                "enabled_endpoints": sum(1 for ep in self._endpoints.values() if ep.enabled),
                "nonce_cache_size": len(self._seen_nonces),
            },
        }

    # -----------------------------------------------------------------------
    # Endpoint management
    # -----------------------------------------------------------------------

    def register_endpoint(self, endpoint: WebhookEndpoint):
        """Register a webhook endpoint."""
        self._endpoints[endpoint.name] = endpoint
        self.logger.info(f"Registered webhook endpoint: {endpoint.name}")

    def unregister_endpoint(self, name: str) -> bool:
        """Remove a webhook endpoint."""
        return self._endpoints.pop(name, None) is not None

    def get_endpoint(self, name: str) -> WebhookEndpoint | None:
        """Get a webhook endpoint by name."""
        return self._endpoints.get(name)

    def load_from_yaml(self, yaml_path: str | Path):
        """
        Load webhook endpoints from YAML config.

        Format:
        ```yaml
        webhooks:
          github_push:
            system_key: my-business
            secret: ${GITHUB_WEBHOOK_SECRET}
            message_template: "GitHub push to {repository[name]}: {head_commit[message]}"

          stripe_payment:
            system_key: my-business
            secret: ${STRIPE_WEBHOOK_SECRET}
            message_template: "Payment received: {data[object][amount]} {data[object][currency]}"
        ```
        """
        import os

        path = Path(yaml_path)
        if not path.exists():
            return

        try:
            import yaml
        except ImportError:
            logger.warning("pyyaml not installed, cannot load webhook config")
            return

        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        for name, cfg in config.get("webhooks", {}).items():
            secret = cfg.get("secret", "")
            # Resolve env vars in secrets
            if isinstance(secret, str) and secret.startswith("${") and secret.endswith("}"):
                secret = os.getenv(secret[2:-1], "")

            self.register_endpoint(
                WebhookEndpoint(
                    name=name,
                    system_key=cfg.get("system_key", self.system_key),
                    secret=secret,
                    enabled=cfg.get("enabled", True),
                    message_template=cfg.get("message_template", ""),
                    metadata=cfg.get("metadata", {}),
                )
            )

    # -----------------------------------------------------------------------
    # Webhook processing
    # -----------------------------------------------------------------------

    async def process_webhook(
        self,
        endpoint_name: str,
        payload: dict[str, Any],
        body_bytes: bytes = b"",
        signature: str = "",
        timestamp: float = 0.0,
        nonce: str = "",
    ) -> OutgoingMessage | None:
        """
        Process an incoming webhook.

        Args:
            endpoint_name: The registered endpoint name
            payload: Parsed JSON payload
            body_bytes: Raw body bytes (for signature verification)
            signature: The signature header value
            timestamp: Unix timestamp from webhook headers (replay prevention)
            nonce: Unique delivery ID (replay prevention)

        Returns:
            OutgoingMessage if processed, None if rejected
        """
        endpoint = self._endpoints.get(endpoint_name)
        if not endpoint:
            self.logger.warning(f"Unknown webhook endpoint: {endpoint_name}")
            return None

        if not endpoint.enabled:
            self.logger.info(f"Webhook endpoint '{endpoint_name}' is disabled")
            return None

        # Replay attack prevention: reject stale timestamps
        if timestamp:
            age = abs(time.time() - timestamp)
            if age > _TIMESTAMP_TOLERANCE:
                self.logger.warning(
                    f"Webhook timestamp too old ({age:.0f}s): {endpoint_name}"
                )
                return None

        # Replay attack prevention: reject duplicate nonces
        if nonce:
            if not self._seen_nonces.check_and_add(nonce):
                self.logger.warning(f"Webhook replay detected (duplicate nonce): {endpoint_name}")
                return None

        # Verify signature — require it if endpoint has a secret
        if endpoint.secret:
            if not signature:
                self.logger.warning(f"Webhook missing signature for secured endpoint: {endpoint_name}")
                return None
            if not endpoint.verify_signature(body_bytes, signature):
                self.logger.warning(f"Webhook signature verification failed: {endpoint_name}")
                return None
        elif body_bytes and signature:
            # No secret but signature provided — verify anyway
            if not endpoint.verify_signature(body_bytes, signature):
                self.logger.warning(f"Webhook signature verification failed: {endpoint_name}")
                return None

        # Update stats
        endpoint.last_received = time.time()
        endpoint.receive_count += 1

        # Transform to message
        text = endpoint.format_payload(payload)
        message = IncomingMessage(
            user_id="webhook",
            text=text,
            system_key=endpoint.system_key,
            channel="webhook",
            metadata={
                "endpoint": endpoint_name,
                "payload": payload,
            },
        )

        response = await self.handle_incoming(message)
        return response

    # -----------------------------------------------------------------------
    # Outgoing webhook delivery
    # -----------------------------------------------------------------------

    async def deliver_outgoing(
        self,
        url: str,
        payload: dict[str, Any],
        secret: str = "",
        max_retries: int = 3,
        timeout: float = 10.0,
    ) -> bool:
        """
        Deliver an outgoing webhook with retry logic.

        Args:
            url: Target URL
            payload: JSON payload to send
            secret: Optional HMAC secret for signing
            max_retries: Number of retries on failure
            timeout: HTTP timeout in seconds

        Returns:
            True if delivered successfully, False otherwise
        """
        import json as json_mod

        import httpx

        body = json_mod.dumps(payload, separators=(",", ":")).encode()
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if secret:
            sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Signature-256"] = f"sha256={sig}"

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, content=body, headers=headers)
                    resp.raise_for_status()
                    return True
            except Exception as e:
                self.logger.warning(
                    f"Outgoing webhook to {url} failed (attempt {attempt}/{max_retries}): {e}"
                )
                if attempt < max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        self.logger.error(f"Outgoing webhook to {url} failed after {max_retries} attempts")
        return False

    @property
    def endpoint_count(self) -> int:
        return len(self._endpoints)

    def status_summary(self) -> dict:
        return {
            "total_endpoints": self.endpoint_count,
            "endpoints": {
                name: {
                    "enabled": ep.enabled,
                    "system_key": ep.system_key,
                    "has_secret": bool(ep.secret),
                    "receive_count": ep.receive_count,
                    "last_received": ep.last_received,
                }
                for name, ep in self._endpoints.items()
            },
        }

