"""MCP tool families.

Each module declares a ``register(registry)`` function that adds its
tools to the singleton :class:`~realize_core.mcp_server.registry.ToolRegistry`.
The registry's loader calls these on first access.
"""
