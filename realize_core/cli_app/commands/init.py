"""``realize-os init`` — create a new system from a template or setup file."""

from __future__ import annotations

from typing import Annotated

import typer


def init(
    template: Annotated[str, typer.Option("--template", "-t", help="Template name.")] = "consulting",
    setup: Annotated[str | None, typer.Option("--setup", "-s", help="Path to setup.yaml for one-command init.")] = None,
    directory: Annotated[str, typer.Option("--directory", "-d", help="Target directory.")] = ".",
) -> None:
    """Initialize a new RealizeOS system from a template or setup file."""
    # Delegate to the existing cmd_init logic in cli.py via an argparse-
    # compatible namespace so we don't duplicate 100+ lines.
    import argparse

    from cli import cmd_init

    ns = argparse.Namespace(template=template, setup=setup, directory=directory)
    cmd_init(ns)
