"""``realize-os kb`` — knowledge base sub-app (search, get, reindex)."""

from __future__ import annotations

from typing import Annotated

import typer

from realize_core.cli_app.formatters import emit
from realize_core.cli_app.http_client import api_get, api_post
from realize_core.cli_app.state import get_state

kb_app = typer.Typer(no_args_is_help=True)


@kb_app.command("search")
def kb_search(
    query: Annotated[str, typer.Argument(help="Search query.")],
    venture: Annotated[str | None, typer.Option("--venture", "-v", help="Venture key to scope search.")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results.")] = 10,
) -> None:
    """Search the knowledge base."""
    state = get_state()

    params: dict[str, object] = {"query": query, "limit": limit}
    if venture:
        params["venture_key"] = venture

    path = "/api/venture-kb/search" if venture else "/api/kb/search"
    result = api_get(path, profile=state.profile, params=params)
    emit(result, output_format=state.output_format)


@kb_app.command("get")
def kb_get(
    doc_id: Annotated[str, typer.Argument(help="Document ID to retrieve.")],
) -> None:
    """Retrieve a KB document by ID."""
    state = get_state()
    result = api_get(f"/api/kb/documents/{doc_id}", profile=state.profile)
    emit(result, output_format=state.output_format)


@kb_app.command("reindex")
def kb_reindex(
    venture: Annotated[str | None, typer.Option("--venture", "-v", help="Venture key to reindex.")] = None,
) -> None:
    """Rebuild the knowledge-base search index."""
    state = get_state()

    body: dict[str, object] = {}
    if venture:
        body["venture_key"] = venture

    result = api_post("/api/kb/reindex", profile=state.profile, json_body=body)
    typer.echo(result.get("message", "Reindex complete."))
