"""
RealizeOS built-in MCP server (HTTP+SSE transport).

Exposes the RealizeOS REST surface as Model Context Protocol tools so any
MCP-speaking agent (Claude Desktop, Cursor, n8n, cloud routines, …) can
plug into a user's RealizeOS instance.

Counterpart to ``realize_core.tools.mcp`` — that module is the outbound
*client* (RealizeOS calls external MCP servers); this module is the inbound
*server* (external agents call RealizeOS).

Public entry points
-------------------
``mount_mcp(app)``
    Wire MCP into a FastAPI app at ``/mcp/sse`` + ``/mcp/messages``. Idempotent.

``mcp_config_from_env(config)``
    Resolve effective MCP configuration from ``realize-os.yaml`` + env overrides.
"""

from realize_core.mcp_server.config import McpConfig, mcp_config_from_env
from realize_core.mcp_server.mount import mount_mcp

__all__ = ["mount_mcp", "McpConfig", "mcp_config_from_env"]
