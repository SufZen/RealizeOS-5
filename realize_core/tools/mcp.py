"""
MCP Client: Connect to MCP servers, discover tools, execute calls.

Uses the official MCP Python SDK to manage connections to stdio-based
MCP servers. Each server runs as a subprocess and exposes tools
that get auto-discovered and converted to Claude tool_use schemas.
"""
import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack

logger = logging.getLogger(__name__)


class MCPServerConnection:
    """Manages a connection to a single MCP server."""

    def __init__(self, name: str, command: str, args: list[str],
                 env: dict[str, str] | None = None, enabled: bool = True):
        self.name = name
        self.command = command
        self.args = args
        self.env = env or {}
        self.enabled = enabled
        self.session = None
        self.tools: list[dict] = []
        self._raw_tools = []
        self._exit_stack: AsyncExitStack | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self.session is not None

    async def connect(self) -> bool:
        if not self.enabled:
            return False
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            logger.error("mcp package not installed. Run: pip install mcp")
            return False

        resolved_env = dict(os.environ)
        for key, value in self.env.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                resolved_env[key] = os.getenv(value[2:-1], "")
            else:
                resolved_env[key] = value

        server_params = StdioServerParameters(
            command=self.command, args=self.args, env=resolved_env,
        )
        try:
            self._exit_stack = AsyncExitStack()
            await self._exit_stack.__aenter__()
            read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
            self.session = await self._exit_stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            tools_result = await self.session.list_tools()
            self._raw_tools = tools_result.tools if hasattr(tools_result, 'tools') else []
            self.tools = [self._mcp_to_claude_schema(t) for t in self._raw_tools]
            self._connected = True
            logger.info(f"MCP server '{self.name}' connected: {len(self.tools)} tools")
            return True
        except FileNotFoundError:
            logger.error(f"MCP server '{self.name}': command '{self.command}' not found")
            await self._cleanup()
            return False
        except Exception as e:
            logger.error(f"MCP server '{self.name}' failed: {e}", exc_info=True)
            await self._cleanup()
            return False

    async def disconnect(self):
        await self._cleanup()

    async def _cleanup(self):
        self._connected = False
        self.session = None
        self.tools = []
        self._raw_tools = []
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
            self._exit_stack = None

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        if not self.connected:
            return f"Error: server '{self.name}' is not connected"
        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            if hasattr(result, 'content') and result.content:
                parts = []
                for block in result.content:
                    if hasattr(block, 'text'):
                        parts.append(block.text)
                    elif hasattr(block, 'data'):
                        parts.append(f"[binary data: {len(block.data)} bytes]")
                    else:
                        parts.append(str(block))
                return "\n".join(parts)
            return json.dumps(result, default=str)
        except Exception as e:
            logger.error(f"MCP tool call '{tool_name}' on '{self.name}' failed: {e}")
            return f"Error calling {tool_name}: {str(e)[:300]}"

    def _mcp_to_claude_schema(self, mcp_tool) -> dict:
        return {
            "name": f"mcp__{self.name}__{mcp_tool.name}",
            "description": getattr(mcp_tool, 'description', '') or f"Tool from {self.name}",
            "input_schema": getattr(mcp_tool, 'inputSchema', {"type": "object", "properties": {}}),
        }

    def get_tool_names(self) -> list[str]:
        return [t.name for t in self._raw_tools]

    def status_dict(self) -> dict:
        return {
            "name": self.name, "enabled": self.enabled, "connected": self.connected,
            "command": f"{self.command} {' '.join(self.args[:2])}",
            "tools_count": len(self.tools), "tool_names": self.get_tool_names(),
        }


class MCPClientHub:
    """Manages connections to multiple MCP servers."""

    def __init__(self):
        self.servers: dict[str, MCPServerConnection] = {}
        self._initialized = False

    async def load_from_config(self, config_path: str | None = None):
        if config_path is None:
            from pathlib import Path
            config_path = str(Path(__file__).parent.parent / "mcp-servers.yaml")
        try:
            import yaml
        except ImportError:
            logger.warning("pyyaml not installed, cannot load MCP config")
            return
        from pathlib import Path
        path = Path(config_path)
        if not path.exists():
            logger.info(f"MCP config not found at {config_path}")
            return
        with open(path) as f:
            config = yaml.safe_load(f) or {}
        for name, cfg in config.get("servers", {}).items():
            self.servers[name] = MCPServerConnection(
                name=name, command=cfg.get("command", ""),
                args=cfg.get("args", []), env=cfg.get("env", {}),
                enabled=cfg.get("enabled", True),
            )
        logger.info(f"Loaded {len(self.servers)} MCP server configs")

    async def connect_all(self):
        tasks = [self._connect_with_timeout(s) for s in self.servers.values() if s.enabled]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            connected = sum(1 for r in results if r is True)
            logger.info(f"MCP: {connected}/{len(tasks)} servers connected")
        self._initialized = True

    async def _connect_with_timeout(self, server: MCPServerConnection, timeout: int = 30) -> bool:
        try:
            return await asyncio.wait_for(server.connect(), timeout=timeout)
        except (TimeoutError, Exception) as e:
            logger.error(f"MCP server '{server.name}' connection error: {e}")
            return False

    async def disconnect_all(self):
        for server in self.servers.values():
            if server.connected:
                await server.disconnect()

    def get_all_tools(self) -> list[dict]:
        return [t for s in self.servers.values() if s.connected for t in s.tools]

    async def call_tool(self, namespaced_name: str, arguments: dict) -> str:
        parts = namespaced_name.split("__", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            return f"Error: invalid MCP tool name: {namespaced_name}"
        server = self.servers.get(parts[1])
        if not server:
            return f"Error: MCP server '{parts[1]}' not found"
        if not server.connected:
            return f"Error: MCP server '{parts[1]}' not connected"
        return await server.call_tool(parts[2], arguments)

    def status_overview(self) -> str:
        if not self.servers:
            return "No MCP servers configured."
        lines = ["**MCP Servers:**\n"]
        for name, server in self.servers.items():
            if server.connected:
                status = f"Connected ({len(server.tools)} tools)"
            elif server.enabled:
                status = "Enabled (not connected)"
            else:
                status = "Disabled"
            lines.append(f"  **{name}** - {status}")
            if server.connected and server.get_tool_names():
                tool_list = ", ".join(server.get_tool_names()[:5])
                if len(server.get_tool_names()) > 5:
                    tool_list += f" (+{len(server.get_tool_names()) - 5} more)"
                lines.append(f"    Tools: {tool_list}")
        return "\n".join(lines)


# Singleton
_hub: MCPClientHub | None = None


def get_mcp_hub() -> MCPClientHub:
    global _hub
    if _hub is None:
        _hub = MCPClientHub()
    return _hub


async def initialize_mcp(config_path: str = None):
    hub = get_mcp_hub()
    await hub.load_from_config(config_path)
    await hub.connect_all()
    return hub


async def shutdown_mcp():
    hub = get_mcp_hub()
    await hub.disconnect_all()
