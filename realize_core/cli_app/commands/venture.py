"""``realize-os venture`` — manage ventures (sub-app with create/delete/list)."""

from __future__ import annotations

from typing import Annotated

import typer

venture_app = typer.Typer(no_args_is_help=True)


@venture_app.command("list")
def venture_list(
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """List all configured ventures."""
    import argparse

    from cli import cmd_venture

    ns = argparse.Namespace(
        venture_action="list", key=None, name=None, description=None, directory=directory, confirm=None
    )
    cmd_venture(ns)


@venture_app.command("create")
def venture_create(
    key: Annotated[str, typer.Option("--key", "-k", help="Venture key (directory name).")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Display name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Venture description.")] = None,
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Create a new venture."""
    import argparse

    from cli import cmd_venture

    ns = argparse.Namespace(
        venture_action="create", key=key, name=name, description=description, directory=directory, confirm=None
    )
    cmd_venture(ns)


@venture_app.command("delete")
def venture_delete(
    key: Annotated[str, typer.Option("--key", "-k", help="Venture key (directory name).")],
    confirm: Annotated[str | None, typer.Option("--confirm", help="Confirm deletion (must match --key).")] = None,
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Delete a venture (requires --confirm matching the key)."""
    import argparse

    from cli import cmd_venture

    ns = argparse.Namespace(
        venture_action="delete", key=key, name=None, description=None, directory=directory, confirm=confirm
    )
    cmd_venture(ns)
