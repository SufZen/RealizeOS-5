"""``realize-os chat`` — send a one-shot prompt to RealizeOS."""

from __future__ import annotations

from typing import Annotated

import typer

from realize_core.cli_app.formatters import emit
from realize_core.cli_app.http_client import api_post
from realize_core.cli_app.state import get_state


def chat(
    message: Annotated[str, typer.Argument(help="The message to send.")],
    system: Annotated[str | None, typer.Option("--system", "-s", help="System key to route to.")] = None,
    agent: Annotated[str | None, typer.Option("--agent", "-a", help="Agent key to route to.")] = None,
    session_id: Annotated[str | None, typer.Option("--session", help="Session ID (for continuations).")] = None,
) -> None:
    """Send a one-shot chat message to a RealizeOS instance."""
    state = get_state()

    body: dict[str, object] = {"message": message}
    if system:
        body["system_key"] = system
    if agent:
        body["agent_key"] = agent
    if session_id:
        body["session_id"] = session_id

    result = api_post("/api/chat", profile=state.profile, json_body=body)

    # Pretty-print the response
    fmt = state.output_format
    if fmt == "table":
        response_text = result.get("response", result.get("message", ""))
        typer.echo(response_text)
    else:
        emit(result, output_format=fmt)
