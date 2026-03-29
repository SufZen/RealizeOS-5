"""
RealizeOS CLI entry point for pip-installed packages.

When installed via `pip install realize-os`, setuptools creates a console script
`realize-os` that calls `realize_core.cli_main:main`. This wrapper locates the
full CLI module (which lives at the repo root as cli.py) and delegates to it.

For source users (`python cli.py serve`), the root cli.py is used directly.
"""

import importlib
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
    """Entry point for the `realize-os` console script."""
    project_root = _find_project_root()

    if project_root is None:
        # Editable install or pip install — cli.py should be at the package root
        print("Error: Could not locate cli.py. Are you running from the project directory?")
        print("  Try:  cd /path/to/RealizeOS-5 && python cli.py <command>")
        sys.exit(1)

    # Add project root to sys.path so `import cli` and local imports work
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # Change to project root so relative paths (templates/, .env, etc.) resolve
    os.chdir(project_root)

    # Import and run the real CLI
    cli_module = importlib.import_module("cli")
    cli_module.main()


if __name__ == "__main__":
    main()
