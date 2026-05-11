"""``realize-os ask`` — smart-routed question (alias for chat)."""

from __future__ import annotations

from typing import Annotated

import typer

from realize_core.cli_app.formatters import emit
from realize_core.cli_app.http_client import api_post
from realize_core.cli_app.state import get_state


def ask(
    query: Annotated[str, typer.Argument(help="The question to ask.")],
) -> None:
    """Ask a question — smart-routed to the best system/agent."""
    state = get_state()

    result = api_post("/api/chat", profile=state.profile, json_body={"message": query})

    fmt = state.output_format
    if fmt == "table":
        response_text = result.get("response", result.get("message", ""))
        typer.echo(response_text)
    else:
        emit(result, output_format=fmt)
