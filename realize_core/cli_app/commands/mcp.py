"""``realize-os mcp`` — MCP server management sub-app.

Commands:
  serve   — start the RealizeOS API + MCP server together
  stdio   — serve MCP over stdin/stdout for a desktop agent (no port)
  status  — show enabled MCP tools and recent call stats
  token   — issue a bearer token for an MCP client
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
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
        sys.executable,
        "-m",
        "uvicorn",
        "realize_api.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
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


@mcp_app.command("stdio")
def mcp_stdio(
    user: Annotated[
        str | None,
        typer.Option(
            "--user",
            "-u",
            help="Email of the users.yaml user the agent acts as (required; their role and ventures apply).",
        ),
    ] = None,
    venture: Annotated[
        list[str] | None,
        typer.Option(
            "--venture",
            help="Limit the session to this venture (repeatable). Must be one of the user's ventures.",
        ),
    ] = None,
    directory: Annotated[
        Path | None,
        typer.Option(
            "--directory",
            "-d",
            exists=True,
            file_okay=False,
            dir_okay=True,
            help="RealizeOS project folder (realize-os.yaml, users.yaml, .env). Defaults to the working directory.",
        ),
    ] = None,
) -> None:
    """Serve MCP over stdin/stdout for a local agent (Claude Desktop, Claude Code, Cursor).

    No network port is opened. stdout carries only JSON-RPC; logs go to
    stderr. The server never runs as an anonymous owner: it needs
    ``--user`` naming a ``users.yaml`` user and refuses to start without one
    (identity is taken from arguments only, never from the environment).
    MCP must be on (``MCP_ENABLED=true``). See docs/connect-your-agent.md.
    """
    if directory is not None:
        _enter_project_directory(directory.resolve())

    from realize_core.mcp_server.auth import MCPProductionAuthError
    from realize_core.mcp_server.stdio import StdioStartupError, run_stdio

    try:
        run_stdio(user, list(venture or []))
    except (StdioStartupError, MCPProductionAuthError) as exc:
        typer.echo(f"RealizeOS MCP stdio server not started: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except KeyboardInterrupt:
        logger.info("MCP stdio server stopped")


def _enter_project_directory(directory: Path) -> None:
    """Work in ``directory`` as if RealizeOS had been started there, in this process.

    Desktop agents can't set a working directory, and RealizeOS reads
    realize-os.yaml, users.yaml, .env and the KB relative to it. Relative
    ``sys.path`` entries are pinned first, so the project folder never
    becomes an import location. Then the folder's ``.env`` is loaded (values
    already in the environment win, as at normal startup) and the settings
    :mod:`realize_core.config` computes at import time (``KB_PATH``,
    ``DATA_PATH``, model names) are recomputed: the CLI imports that module
    before any command runs.
    """
    import importlib
    import sys

    sys.path[:] = [p if os.path.isabs(p) else os.path.abspath(p) for p in sys.path]
    os.chdir(directory)
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(directory / ".env")

    import realize_core.config

    importlib.reload(realize_core.config)
