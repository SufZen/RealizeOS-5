"""``realize-os status`` — show system status."""

from __future__ import annotations

from typing import Annotated

import typer


def status(
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Show RealizeOS system status."""
    import argparse

    from cli import cmd_status

    ns = argparse.Namespace(directory=directory)
    cmd_status(ns)
