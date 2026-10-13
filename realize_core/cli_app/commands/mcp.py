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
            envvar="REALIZE_MCP_USER",
            help="Email of the users.yaml user the agent acts as (required; their role and ventures apply).",
        ),
    ] = None,
    venture: Annotated[
        list[str] | None,
        typer.Option(
            "--venture",
            envvar="REALIZE_MCP_VENTURE",
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
    stderr. The server never runs as an anonymous owner: it needs a
    ``users.yaml`` identity and refuses to start without one. MCP must be on
    (``MCP_ENABLED=true``). See docs/connect-your-agent.md.
    """
    ventures = list(venture or [])
    if directory is not None and directory.resolve() != Path.cwd().resolve():
        raise typer.Exit(code=_relaunch_stdio_in(directory.resolve(), user, ventures))

    from realize_core.mcp_server.auth import MCPProductionAuthError
    from realize_core.mcp_server.stdio import StdioStartupError, run_stdio

    try:
        run_stdio(user, ventures)
    except (StdioStartupError, MCPProductionAuthError) as exc:
        typer.echo(f"RealizeOS MCP stdio server not started: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except KeyboardInterrupt:
        logger.info("MCP stdio server stopped")


def _relaunch_stdio_in(directory: Path, user: str | None, ventures: list[str]) -> int:
    """Run ``mcp stdio`` in a fresh process whose working directory is ``directory``.

    RealizeOS reads realize-os.yaml, users.yaml, .env and the KB relative to
    the working directory, and some settings are fixed when modules are
    imported, so a new process is the reliable way to switch folders. The
    child uses this process's stdin, stdout and stderr unchanged. Values from
    ``directory/.env`` are added for keys not already in the environment.
    """
    import subprocess
    import sys

    import realize_core

    env = dict(os.environ)
    try:
        from dotenv import dotenv_values
    except ImportError:
        pass
    else:
        for key, value in dotenv_values(directory / ".env").items():
            if value is not None:
                env.setdefault(key, value)

    # A source checkout isn't on the child's import path once the working
    # directory changes; an installed package already is.
    code_root = Path(realize_core.__file__).resolve().parent.parent
    if not {"site-packages", "dist-packages"} & set(code_root.parts):
        env["PYTHONPATH"] = os.pathsep.join(p for p in (str(code_root), env.get("PYTHONPATH", "")) if p)

    args = ["mcp", "stdio"]
    if user:
        args += ["--user", user]
    for key in ventures:
        args += ["--venture", key]
    cmd = [sys.executable, "-c", "from realize_core.cli_app import main; main()", *args]
    return subprocess.call(cmd, cwd=directory, env=env)
