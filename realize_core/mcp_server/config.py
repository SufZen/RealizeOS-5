"""MCP server configuration resolver.

Reads the ``mcp:`` block from ``realize-os.yaml`` and overlays environment
variable overrides. Returns an :class:`McpConfig` snapshot used by the
server, the router, and the tool registry.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class McpConfig:
    """Effective MCP server configuration after env overlay."""

    enabled: bool
    expose_kb: bool
    expose_ops: bool
    allow_admin: bool
    audit_full_payload: bool
    bearer_token_override: str

    @property
    def families(self) -> list[str]:
        """Tool families currently exposed."""
        out = ["chat"]
        if self.expose_kb:
            out.append("kb")
        if self.expose_ops:
            out.append("ops")
        if self.allow_admin:
            out.append("admin")
        return out


def mcp_config_from_env(config: dict | None = None) -> McpConfig:
    """Resolve effective MCP config from ``realize-os.yaml`` + env vars.

    Env vars (``MCP_ENABLED``, ``MCP_EXPOSE_KB``, ``MCP_EXPOSE_OPS``,
    ``MCP_ALLOW_ADMIN``, ``MCP_AUDIT_FULL_PAYLOAD``,
    ``MCP_BEARER_TOKEN_OVERRIDE``) take precedence over the yaml block.
    """
    raw = (config or {}).get("mcp", {}) if isinstance(config, dict) else {}

    def yaml_bool(key: str, default: bool) -> bool:
        if key not in raw:
            return default
        return bool(raw.get(key))

    return McpConfig(
        enabled=_env_bool("MCP_ENABLED", yaml_bool("enabled", False)),
        expose_kb=_env_bool("MCP_EXPOSE_KB", yaml_bool("expose_kb", True)),
        expose_ops=_env_bool("MCP_EXPOSE_OPS", yaml_bool("expose_ops", True)),
        allow_admin=_env_bool("MCP_ALLOW_ADMIN", yaml_bool("allow_admin", False)),
        audit_full_payload=_env_bool("MCP_AUDIT_FULL_PAYLOAD", yaml_bool("audit_full_payload", False)),
        bearer_token_override=os.environ.get("MCP_BEARER_TOKEN_OVERRIDE", str(raw.get("bearer_token_override", ""))),
    )
