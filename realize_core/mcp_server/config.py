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
    #: Serve the Streamable HTTP transport on ``/mcp`` next to ``/mcp/sse``.
    streamable_http: bool = True
    #: Run the OAuth 2.1 authorization server (Claude.ai custom connectors).
    oauth_enabled: bool = False
    #: Public base URL (``https://host``) — the OAuth issuer and resource origin.
    public_url: str = ""
    #: Hosts OAuth clients may redirect to; empty = the built-in default list.
    oauth_redirect_hosts: tuple[str, ...] = ()
    #: Only these tools are served (within the exposed families); empty = all of them.
    #: A hosted profile uses it to serve one workflow, e.g. the self-serve tender register.
    tools: tuple[str, ...] = ()

    @property
    def resource_url(self) -> str:
        """The MCP resource URL OAuth tokens are issued for (``<public_url>/mcp``)."""
        return f"{self.public_url.rstrip('/')}/mcp"

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


def _host_list(raw: object) -> tuple[str, ...]:
    """Hosts from a comma-separated string or a YAML list."""
    items = raw.split(",") if isinstance(raw, str) else raw if isinstance(raw, list) else []
    return tuple(str(h).strip().lower() for h in items if str(h).strip())


def _name_list(raw: object) -> tuple[str, ...]:
    """Tool names from a comma-separated string or a YAML list, in order, without duplicates."""
    items = raw.split(",") if isinstance(raw, str) else raw if isinstance(raw, list) else []
    return tuple(dict.fromkeys(str(n).strip() for n in items if str(n).strip()))


def mcp_config_from_env(config: dict | None = None) -> McpConfig:
    """Resolve effective MCP config from ``realize-os.yaml`` + env vars.

    Env vars (``MCP_ENABLED``, ``MCP_EXPOSE_KB``, ``MCP_EXPOSE_OPS``,
    ``MCP_ALLOW_ADMIN``, ``MCP_AUDIT_FULL_PAYLOAD``,
    ``MCP_BEARER_TOKEN_OVERRIDE``, ``MCP_STREAMABLE_HTTP``,
    ``MCP_OAUTH_ENABLED``, ``MCP_OAUTH_REDIRECT_HOSTS``, ``MCP_PUBLIC_URL``, ``MCP_TOOLS``) take precedence
    over the yaml block.
    """
    raw = (config or {}).get("mcp", {}) if isinstance(config, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    oauth_raw = raw.get("oauth", {})
    oauth_raw = oauth_raw if isinstance(oauth_raw, dict) else {}

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
        streamable_http=_env_bool("MCP_STREAMABLE_HTTP", yaml_bool("streamable_http", True)),
        oauth_enabled=_env_bool("MCP_OAUTH_ENABLED", bool(oauth_raw.get("enabled", False))),
        oauth_redirect_hosts=_host_list(
            os.environ.get("MCP_OAUTH_REDIRECT_HOSTS", oauth_raw.get("redirect_hosts") or "")
        ),
        public_url=os.environ.get("MCP_PUBLIC_URL", str(raw.get("public_url", "") or "")).strip().rstrip("/"),
        tools=_name_list(os.environ.get("MCP_TOOLS", raw.get("tools") or "")),
    )
