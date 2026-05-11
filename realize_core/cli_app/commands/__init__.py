"""Command registry — attaches all subcommand groups to the Typer app."""

from __future__ import annotations

import typer


def register_commands(app: typer.Typer) -> None:
    """Import and register every command group on *app*."""
    # Each module exposes either a Typer sub-app or bare @app.command functions.
    # We import them lazily so startup stays fast when only one command is used.

    from realize_core.cli_app.commands.audit import audit
    from realize_core.cli_app.commands.bot import bot
    from realize_core.cli_app.commands.config import config_app
    from realize_core.cli_app.commands.devmode import devmode_app
    from realize_core.cli_app.commands.doctor import doctor
    from realize_core.cli_app.commands.index import index
    from realize_core.cli_app.commands.init import init
    from realize_core.cli_app.commands.serve import serve
    from realize_core.cli_app.commands.setup import setup
    from realize_core.cli_app.commands.status import status
    from realize_core.cli_app.commands.venture import venture_app
    from realize_core.cli_app.commands.version import version

    # Plain commands
    app.command()(init)
    app.command()(serve)
    app.command()(bot)
    app.command()(status)
    app.command()(audit)
    app.command()(index)
    app.command()(setup)
    app.command()(doctor)
    app.command()(version)

    # Subcommand groups
    app.add_typer(venture_app, name="venture", help="Manage ventures.")
    app.add_typer(config_app, name="config", help="Manage CLI configuration and profiles.")
    app.add_typer(devmode_app, name="devmode", help="Developer Mode — AI client integration tools.")
