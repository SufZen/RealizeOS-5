"""Command registry — attaches all subcommand groups to the Typer app."""

from __future__ import annotations

import typer


def register_commands(app: typer.Typer) -> None:
    """Import and register every command group on *app*."""
    # Each module exposes either a Typer sub-app or bare @app.command functions.
    # We import them lazily so startup stays fast when only one command is used.

    # --- Existing commands (Story 6) ---
    # --- New operator commands (Story 7) ---
    from realize_core.cli_app.commands.ask import ask
    from realize_core.cli_app.commands.audit import audit
    from realize_core.cli_app.commands.bot import bot
    from realize_core.cli_app.commands.chat import chat
    from realize_core.cli_app.commands.config import config_app
    from realize_core.cli_app.commands.devmode import devmode_app
    from realize_core.cli_app.commands.doctor import doctor
    from realize_core.cli_app.commands.evolution import evolution_app
    from realize_core.cli_app.commands.fabric import fabric_app
    from realize_core.cli_app.commands.index import index
    from realize_core.cli_app.commands.init import init
    from realize_core.cli_app.commands.kb import kb_app

    # --- MCP + REPL (Story 8) ---
    from realize_core.cli_app.commands.mcp import mcp_app
    from realize_core.cli_app.commands.repl import repl
    from realize_core.cli_app.commands.serve import serve
    from realize_core.cli_app.commands.setup import setup
    from realize_core.cli_app.commands.skill import skill_app
    from realize_core.cli_app.commands.status import status
    from realize_core.cli_app.commands.venture import venture_app
    from realize_core.cli_app.commands.version import version
    from realize_core.cli_app.commands.workflow import workflow_app

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
    app.command()(chat)
    app.command()(ask)
    app.command()(repl)

    # Subcommand groups
    app.add_typer(venture_app, name="venture", help="Manage ventures.")
    app.add_typer(config_app, name="config", help="Manage CLI configuration and profiles.")
    app.add_typer(devmode_app, name="devmode", help="Developer Mode -- AI client integration tools.")
    app.add_typer(kb_app, name="kb", help="Knowledge base search and management.")
    app.add_typer(workflow_app, name="workflow", help="Workflow management.")
    app.add_typer(skill_app, name="skill", help="Skill management.")
    app.add_typer(evolution_app, name="evolution", help="Evolution engine and suggestions.")
    app.add_typer(mcp_app, name="mcp", help="MCP server management.")
    # v5.5.0 — FABRIC Knowledge System
    app.add_typer(fabric_app, name="fabric", help="FABRIC knowledge system: lint, reindex, search, dream.")
