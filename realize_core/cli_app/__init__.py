"""RealizeOS first-class operator CLI — Typer-based (5.1.0+).

Exports:

* :data:`app`  — the configured :class:`typer.Typer` instance.
* :func:`main` — entry point referenced by ``pyproject.toml [project.scripts]``
  and called from the legacy :mod:`cli` shim at the repo root.

Backwards compatibility: every ``python cli.py <verb>`` form from 5.0.x
keeps working because the Typer commands forward to the legacy
``cmd_*`` handlers in :mod:`cli` (the root module). New subcommands
land alongside (``config``, ``version``, and — in Stories 7–8 —
``chat``, ``kb``, ``workflow``, ``skill``, ``evolution``, ``repl``,
``mcp``).
"""

from __future__ import annotations

import typer

from realize_core.cli_app.commands import register_commands
from realize_core.cli_app.state import CLIState, ensure_state


def _build_app() -> typer.Typer:
    """Build the configured Typer app. Idempotent."""
    app = typer.Typer(
        name="realize-os",
        help="RealizeOS — AI Operations System. Operator CLI for any RealizeOS instance.",
        no_args_is_help=True,
        add_completion=True,
        rich_markup_mode=None,  # plain markup — keeps output stable across terminals
    )

    @app.callback()
    def _root(
        ctx: typer.Context,
        profile: str | None = typer.Option(
            None,
            "--profile",
            help="Named profile from ~/.realize-os/config.toml. Overrides default for one call.",
        ),
        output_format: str | None = typer.Option(
            None,
            "--format",
            help="Output format for list/get commands: table | json | yaml. Default: table.",
        ),
    ) -> None:
        """Top-level options shared by every subcommand."""
        ensure_state(ctx, profile=profile, output_format=output_format)

    register_commands(app)
    return app


#: Module-level Typer app. Re-created on import. Lightweight.
app: typer.Typer = _build_app()


def main() -> None:
    """Entry point used by ``[project.scripts] realize-os`` and the
    ``cli.py`` shim at the repo root.

    Tries to load ``.env`` first (so users invoking the CLI from a project
    directory see their configured providers) — best-effort; missing
    python-dotenv is fine.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    app()


__all__ = ["CLIState", "app", "main"]
