"""``realize-os serve`` — start the API server."""

from __future__ import annotations

from typing import Annotated

import typer


def serve(
    host: Annotated[str | None, typer.Option("--host", help="Bind address (default: 127.0.0.1).")] = None,
    port: Annotated[int | None, typer.Option("--port", "-p", help="Port (default: 8080).")] = None,
    reload: Annotated[bool, typer.Option("--reload", help="Enable auto-reload for development.")] = False,
) -> None:
    """Start the RealizeOS API server."""
    import argparse

    from cli import cmd_serve

    ns = argparse.Namespace(host=host, port=port, reload=reload)
    cmd_serve(ns)
