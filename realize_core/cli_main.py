"""
RealizeOS CLI entry point for pip-installed packages.

When installed via `pip install realize-os`, setuptools creates a console script
`realize-os` that calls `realize_core.cli_main:main`. This module delegates
to the Typer-based CLI in ``realize_core.cli_app``.

For source users (``python cli.py serve``), the root ``cli.py`` shim is used
directly — both paths converge on the same Typer app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_project_root() -> Path | None:
    """Walk up from this file to find a directory containing cli.py."""
    current = Path(__file__).resolve().parent
    # cli.py lives one level above realize_core/
    candidate = current.parent / "cli.py"
    if candidate.exists():
        return candidate.parent
    return None


def main():
    """Entry point for the ``realize-os`` console script."""
    project_root = _find_project_root()

    if project_root is not None:
        # Add project root to sys.path so local imports (cli.py, etc.) resolve
        root_str = str(project_root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        # Change to project root so relative paths (templates/, .env, etc.) work
        os.chdir(project_root)

    # Delegate to the Typer-based CLI
    from realize_core.cli_app import main as typer_main

    typer_main()


if __name__ == "__main__":
    main()
