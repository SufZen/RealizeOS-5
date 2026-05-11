"""``realize-os doctor`` — diagnose installation issues."""

from __future__ import annotations

from typing import Annotated

import typer


def doctor(
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Diagnose installation issues."""
    import argparse

    from cli import cmd_doctor

    ns = argparse.Namespace(directory=directory)
    cmd_doctor(ns)
