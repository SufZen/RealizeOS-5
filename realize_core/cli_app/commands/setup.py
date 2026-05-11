"""``realize-os setup`` — interactive setup wizard."""

from __future__ import annotations

from typing import Annotated

import typer


def setup(
    directory: Annotated[str, typer.Option("--directory", "-d", help="Target directory.")] = ".",
    skip_dashboard: Annotated[bool, typer.Option("--skip-dashboard", help="Skip dashboard setup.")] = False,
) -> None:
    """Run the interactive setup wizard."""
    import argparse

    from cli import cmd_setup

    ns = argparse.Namespace(directory=directory, skip_dashboard=skip_dashboard)
    cmd_setup(ns)
