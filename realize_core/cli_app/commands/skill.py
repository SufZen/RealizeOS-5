"""``realize-os skill`` — skill sub-app (list, trigger)."""

from __future__ import annotations

from typing import Annotated

import typer

from realize_core.cli_app.formatters import emit
from realize_core.cli_app.http_client import api_get, api_post
from realize_core.cli_app.state import get_state

skill_app = typer.Typer(no_args_is_help=True)


@skill_app.command("list")
def skill_list() -> None:
    """List all available skills."""
    state = get_state()
    result = api_get("/api/skills", profile=state.profile)
    emit(result, output_format=state.output_format)


@skill_app.command("trigger")
def skill_trigger(
    name: Annotated[str, typer.Argument(help="Skill name to trigger.")],
) -> None:
    """Trigger a skill by name."""
    state = get_state()
    result = api_post("/api/skills/trigger", profile=state.profile, json_body={"name": name})
    emit(result, output_format=state.output_format)
