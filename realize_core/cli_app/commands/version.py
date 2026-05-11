"""``realize-os version`` — print the current version."""

from __future__ import annotations

from pathlib import Path

import typer


def version() -> None:
    """Print the RealizeOS version and exit."""
    version_file = Path(__file__).resolve().parents[3] / "VERSION"
    if version_file.exists():
        ver = version_file.read_text(encoding="utf-8").strip()
    else:
        ver = "unknown"
    typer.echo(f"RealizeOS v{ver}")
