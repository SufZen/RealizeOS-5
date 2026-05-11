"""``realize-os workflow`` — workflow sub-app (list, run)."""

from __future__ import annotations

from typing import Annotated

import typer

from realize_core.cli_app.formatters import emit
from realize_core.cli_app.http_client import api_get, api_post
from realize_core.cli_app.state import get_state

workflow_app = typer.Typer(no_args_is_help=True)


@workflow_app.command("list")
def workflow_list() -> None:
    """List all available workflows."""
    state = get_state()
    result = api_get("/api/workflows", profile=state.profile)
    emit(result, output_format=state.output_format)


@workflow_app.command("run")
def workflow_run(
    name: Annotated[str, typer.Argument(help="Workflow name to run.")],
    input_json: Annotated[str | None, typer.Option("--input", "-i", help="Input JSON string.")] = None,
) -> None:
    """Run a workflow by name."""
    import json

    state = get_state()

    body: dict[str, object] = {"name": name}
    if input_json:
        try:
            body["input"] = json.loads(input_json)
        except json.JSONDecodeError as exc:
            typer.echo(f"Error: Invalid JSON input: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    result = api_post("/api/workflows/run", profile=state.profile, json_body=body)
    emit(result, output_format=state.output_format)
