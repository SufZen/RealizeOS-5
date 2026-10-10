"""``realize-os version`` — print the current version."""

from __future__ import annotations

import typer

from realize_core import __version__


def version() -> None:
    """Print the RealizeOS version and exit."""
    typer.echo(f"RealizeOS v{__version__}")
