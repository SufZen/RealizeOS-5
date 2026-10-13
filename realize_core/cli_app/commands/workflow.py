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
    venture: Annotated[str, typer.Option("--venture", "-v", help="The venture whose copy of the workflow runs.")],
    message: Annotated[
        str | None, typer.Option("--message", "-m", help="The input message (what you'd type in chat).")
    ] = None,
    input_json: Annotated[
        str | None, typer.Option("--input", "-i", help='Deprecated: JSON input; {"input_text": "..."} or any JSON.')
    ] = None,
) -> None:
    """Run a venture's workflow with an input message (POST /api/workflows/{name}/run)."""
    import json
    from urllib.parse import quote

    state = get_state()

    text = message
    if text is None and input_json:
        try:
            parsed = json.loads(input_json)
        except json.JSONDecodeError as exc:
            typer.echo(f"Error: Invalid JSON input: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        text = parsed.get("input_text") if isinstance(parsed, dict) else None
        text = text if isinstance(text, str) else json.dumps(parsed, ensure_ascii=False)
    if not text:
        typer.echo("Error: give the input with --message", err=True)
        raise typer.Exit(code=1)

    body = {"system_key": venture, "input_text": text}
    result = api_post(f"/api/workflows/{quote(name, safe='')}/run", profile=state.profile, json_body=body)
    emit(result, output_format=state.output_format)
