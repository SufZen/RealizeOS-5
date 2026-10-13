"""``realize-os decisions`` — the decision log's write queue (Codex audit N05).

Commands:
  retry  — write decisions whose earlier write failed, then list what is still waiting
"""

from __future__ import annotations

from typing import Annotated

import typer

decisions_app = typer.Typer(no_args_is_help=True)


@decisions_app.command("retry")
def decisions_retry(
    limit: Annotated[int, typer.Option("--limit", help="Retry at most this many writes.")] = 500,
) -> None:
    """Write decisions whose earlier write failed (disk full, read-only mount, missing venture folder).

    Run it on the server, in the project directory. A decision already on
    disk is never written twice. Exits 1 while some writes are still waiting.
    """
    from realize_core.governance.decision_log import pending_decisions, retry_pending_decisions

    result = retry_pending_decisions(limit=limit, max_attempts=None)
    typer.echo(f"Recorded {result['logged']} decision(s); {result['pending']} still waiting.")
    if not result["pending"]:
        return
    for intent in pending_decisions(limit=limit):
        reason = intent.get("last_error") or "not tried yet"
        typer.echo(f"  {intent['approval_id']}  venture {intent['venture_key'] or '-'}: {reason}")
    raise typer.Exit(code=1)
