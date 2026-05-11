"""``realize-os evolution`` — evolution sub-app (run, suggestions, approve, dismiss)."""

from __future__ import annotations

from typing import Annotated

import typer

from realize_core.cli_app.formatters import emit
from realize_core.cli_app.http_client import api_get, api_post
from realize_core.cli_app.state import get_state

evolution_app = typer.Typer(no_args_is_help=True)


@evolution_app.command("run")
def evolution_run() -> None:
    """Run the evolution engine."""
    state = get_state()
    result = api_post("/api/evolution/run", profile=state.profile, json_body={})
    emit(result, output_format=state.output_format)


@evolution_app.command("suggestions")
def evolution_suggestions(
    status: Annotated[str | None, typer.Option("--status", "-s", help="Filter by status (e.g. pending, approved).")] = None,
) -> None:
    """List evolution suggestions."""
    state = get_state()

    params: dict[str, object] = {}
    if status:
        params["status"] = status

    result = api_get("/api/evolution/suggestions", profile=state.profile, params=params)
    emit(result, output_format=state.output_format)


@evolution_app.command("approve")
def evolution_approve(
    suggestion_id: Annotated[str, typer.Argument(help="Suggestion ID to approve.")],
) -> None:
    """Approve an evolution suggestion."""
    state = get_state()
    result = api_post(
        f"/api/approvals/{suggestion_id}/approve",
        profile=state.profile,
        json_body={},
    )
    typer.echo(result.get("message", f"Suggestion {suggestion_id} approved."))


@evolution_app.command("dismiss")
def evolution_dismiss(
    suggestion_id: Annotated[str, typer.Argument(help="Suggestion ID to dismiss.")],
) -> None:
    """Dismiss an evolution suggestion."""
    state = get_state()
    result = api_post(
        f"/api/approvals/{suggestion_id}/dismiss",
        profile=state.profile,
        json_body={},
    )
    typer.echo(result.get("message", f"Suggestion {suggestion_id} dismissed."))
