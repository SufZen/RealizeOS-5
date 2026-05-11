"""``realize-os mcp`` — MCP server management sub-app.

Commands:
  serve   — start the RealizeOS API + MCP server together
  status  — show enabled MCP tools and recent call stats
  token   — issue a bearer token for an MCP client
"""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from realize_core.cli_app.formatters import emit
from realize_core.cli_app.http_client import api_get, api_post
from realize_core.cli_app.state import get_state

logger = logging.getLogger(__name__)

mcp_app = typer.Typer(no_args_is_help=True)


@mcp_app.command("serve")
def mcp_serve(
    port: Annotated[int, typer.Option("--port", "-p", help="Port for the API+MCP server.")] = 8080,
    allow_admin: Annotated[bool, typer.Option("--allow-admin", help="Enable admin MCP tools.")] = False,
    reload: Annotated[bool, typer.Option("--reload", help="Enable auto-reload for development.")] = False,
) -> None:
    """Start the RealizeOS API server with MCP endpoint enabled.

    This is equivalent to ``realize-os serve`` but also sets the
    ``MCP_ENABLED`` environment variable so the MCP SSE endpoint
    is mounted at ``/mcp/sse``.
    """
    import os
    import subprocess
    import sys

    os.environ["MCP_ENABLED"] = "true"
    if allow_admin:
        os.environ["MCP_ALLOW_ADMIN"] = "true"

    # Delegate to the standard serve path
    cmd = [
        sys.executable, "-m", "uvicorn",
        "realize_api.main:app",
        "--host", "0.0.0.0",
        "--port", str(port),
    ]
    if reload:
        cmd.append("--reload")

    typer.echo(f"Starting RealizeOS API + MCP on port {port} ...")
    if allow_admin:
        typer.echo("  Admin MCP tools: ENABLED")
    typer.echo(f"  MCP SSE endpoint: http://0.0.0.0:{port}/mcp/sse")
    typer.echo("")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        typer.echo("\nShutting down.")
    except subprocess.CalledProcessError as exc:
        typer.echo(f"Server exited with code {exc.returncode}", err=True)
        raise typer.Exit(code=exc.returncode) from exc


@mcp_app.command("status")
def mcp_status() -> None:
    """Show MCP server status — enabled tools and health."""
    state = get_state()
    result = api_get("/mcp/health", profile=state.profile)
    emit(result, output_format=state.output_format)


@mcp_app.command("token")
def mcp_token(
    user: Annotated[str, typer.Option("--user", "-u", help="User ID for the token.")] = "owner",
    role: Annotated[str, typer.Option("--role", "-r", help="Role for the token.")] = "owner",
) -> None:
    """Issue a bearer token for an MCP client.

    The token can be used as ``Authorization: Bearer <token>``
    in Claude Desktop, Cursor, or any MCP client configuration.
    """
    state = get_state()
    result = api_post(
        "/api/auth/token",
        profile=state.profile,
        json_body={"user_id": user, "role": role},
    )
    token = result.get("access_token", result.get("token", ""))
    if token:
        typer.echo(token)
    else:
        emit(result, output_format=state.output_format)
