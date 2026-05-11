"""``realize-os devmode`` — developer mode sub-app (AI client integration tools)."""

from __future__ import annotations

from typing import Annotated

import typer

devmode_app = typer.Typer(no_args_is_help=True)


@devmode_app.command("setup")
def devmode_setup(
    tools: Annotated[
        str | None, typer.Option("--tools", help="Comma-separated AI tools (e.g. claude,gemini,cursor).")
    ] = None,
    level: Annotated[
        str | None, typer.Option("--level", help="Protection level: strict, standard, or relaxed.")
    ] = None,
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Generate AI-tool context files for the project."""
    import argparse

    from cli import cmd_devmode

    ns = argparse.Namespace(
        devmode_action="setup",
        tools=tools,
        level=level,
        name=None,
        type=None,
        description=None,
        label=None,
        tag=None,
        quick=False,
        directory=directory,
    )
    cmd_devmode(ns)


@devmode_app.command("check")
def devmode_check(
    quick: Annotated[bool, typer.Option("--quick", help="Skip slow checks.")] = False,
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Run health checks for developer mode."""
    import argparse

    from cli import cmd_devmode

    ns = argparse.Namespace(
        devmode_action="check",
        tools=None,
        level=None,
        name=None,
        type=None,
        description=None,
        label=None,
        tag=None,
        quick=quick,
        directory=directory,
    )
    cmd_devmode(ns)


@devmode_app.command("scaffold")
def devmode_scaffold(
    name: Annotated[str, typer.Option("--name", help="Extension name.")],
    type: Annotated[
        str | None, typer.Option("--type", help="Extension type: tool, channel, integration, hook.")
    ] = None,
    description: Annotated[str | None, typer.Option("--description", help="Extension description.")] = None,
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Scaffold a new extension."""
    import argparse

    from cli import cmd_devmode

    ns = argparse.Namespace(
        devmode_action="scaffold",
        tools=None,
        level=None,
        name=name,
        type=type,
        description=description,
        label=None,
        tag=None,
        quick=False,
        directory=directory,
    )
    cmd_devmode(ns)


@devmode_app.command("snapshot")
def devmode_snapshot(
    label: Annotated[str | None, typer.Option("--label", help="Snapshot label.")] = None,
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Create a git snapshot of the current state."""
    import argparse

    from cli import cmd_devmode

    ns = argparse.Namespace(
        devmode_action="snapshot",
        tools=None,
        level=None,
        name=None,
        type=None,
        description=None,
        label=label,
        tag=None,
        quick=False,
        directory=directory,
    )
    cmd_devmode(ns)


@devmode_app.command("rollback")
def devmode_rollback(
    tag: Annotated[str | None, typer.Option("--tag", help="Snapshot tag to roll back to.")] = None,
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Roll back to a previous snapshot."""
    import argparse

    from cli import cmd_devmode

    ns = argparse.Namespace(
        devmode_action="rollback",
        tools=None,
        level=None,
        name=None,
        type=None,
        description=None,
        label=None,
        tag=tag,
        quick=False,
        directory=directory,
    )
    cmd_devmode(ns)


@devmode_app.command("diff")
def devmode_diff(
    tag: Annotated[str | None, typer.Option("--tag", help="Tag to diff from.")] = None,
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Show changes since a snapshot."""
    import argparse

    from cli import cmd_devmode

    ns = argparse.Namespace(
        devmode_action="diff",
        tools=None,
        level=None,
        name=None,
        type=None,
        description=None,
        label=None,
        tag=tag,
        quick=False,
        directory=directory,
    )
    cmd_devmode(ns)


@devmode_app.command("status")
def devmode_status(
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Show developer mode status."""
    import argparse

    from cli import cmd_devmode

    ns = argparse.Namespace(
        devmode_action="status",
        tools=None,
        level=None,
        name=None,
        type=None,
        description=None,
        label=None,
        tag=None,
        quick=False,
        directory=directory,
    )
    cmd_devmode(ns)
