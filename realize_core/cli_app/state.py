"""Typer context state shared across CLI subcommands."""

from __future__ import annotations

from dataclasses import dataclass

import typer


@dataclass
class CLIState:
    """Per-invocation state carried on ``ctx.obj``."""

    profile: str | None = None
    output_format: str = "table"  # table | json | yaml


def ensure_state(
    ctx: typer.Context,
    *,
    profile: str | None = None,
    output_format: str | None = None,
) -> CLIState:
    """Get-or-create the :class:`CLIState` on the Typer context."""
    if not isinstance(ctx.obj, CLIState):
        ctx.obj = CLIState()
    if profile is not None:
        ctx.obj.profile = profile
    if output_format is not None:
        ctx.obj.output_format = output_format.lower().strip()
    return ctx.obj


def get_state() -> CLIState:
    """Retrieve the :class:`CLIState` from the current Typer context.

    Falls back to sensible defaults if called outside a proper Typer
    invocation (e.g. from tests or direct imports).
    """
    try:
        import click

        ctx = click.get_current_context(silent=True)
        if ctx is not None and isinstance(ctx.obj, CLIState):
            return ctx.obj
    except (ImportError, RuntimeError):
        pass
    return CLIState()
