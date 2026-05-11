"""``realize-os audit`` — run the structured system audit."""

from __future__ import annotations

from typing import Annotated

import typer


def audit(
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
    quick: Annotated[bool, typer.Option("--quick", help="Skip slower checks.")] = False,
    format: Annotated[str, typer.Option("--format", help="Output format: text or json.")] = "text",
) -> None:
    """Run the structured RealizeOS audit playbook."""
    import argparse

    from cli import cmd_audit

    ns = argparse.Namespace(directory=directory, quick=quick, format=format)
    cmd_audit(ns)
