"""``realize-os wedge`` — host the self-serve tender register pilot (STORY-46).

Commands:
  invite  — add an invite-only pilot user (shows their password once)
  funnel  — runs, users and call requests per market, from recorded runs
  purge   — delete expired runs now (the server also does it daily)
"""

from __future__ import annotations

import json
import os
from typing import Annotated

import typer

wedge_app = typer.Typer(no_args_is_help=True)


@wedge_app.command("invite")
def wedge_invite(
    email: Annotated[str, typer.Argument(help="The pilot user's sign-in email.")],
) -> None:
    """Add a pilot user to users.yaml: a viewer limited to an empty sandbox venture of their own.

    Only works on a pilot host: features.wedge on and mcp.tools limited to the pilot tools.
    """
    from realize_core.config import load_config
    from realize_core.wedge.pilot import PilotInviteError, invite

    try:
        result = invite(email, config=load_config())
    except PilotInviteError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.written:
        typer.echo(f"Added {result.email} to users.yaml (role viewer, venture {result.venture}).")
        kept = f"Previous file kept as {result.backup}. " if result.backup else "No backup could be written. "
        typer.echo(f"{kept}Comments in users.yaml are not preserved.")
    else:
        typer.echo("users.yaml could not be written. Add this entry under 'users:' yourself:\n")
        typer.echo(result.entry_yaml)
    typer.echo(f"\nPassword (shown once, send it privately): {result.password}")
    public_url = os.environ.get("MCP_PUBLIC_URL", "").rstrip("/")
    connector = f"{public_url}/mcp" if public_url else "https://<your host>/mcp"
    typer.echo(f"Connector URL for their agent: {connector}  (guide: docs/connect-your-agent.md)")


@wedge_app.command("funnel")
def wedge_funnel(
    days: Annotated[int, typer.Option("--days", help="Look back this many days.")] = 30,
    output: Annotated[str, typer.Option("--format", help="Output format: text or json.")] = "text",
) -> None:
    """Show the pilot funnel per market (runs, users, call requests), from recorded runs only."""
    from realize_core.wedge import funnel

    rows = funnel(days=days)
    if output == "json":
        typer.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        typer.echo(f"No pilot runs in the last {days} days.")
        return
    typer.echo(f"{'market':<8}{'runs':>6}{'users':>7}{'calls':>7}{'rate':>7}{'avg lvl':>9}")
    for r in rows:
        typer.echo(
            f"{r['market'] or '-':<8}{r['runs']:>6}{r['users']:>7}{r['calls_requested']:>7}"
            f"{r['call_rate']:>7.0%}{r['avg_verification']:>9}"
        )
    typer.echo("Pass: 30% of users request a call, and at least one comes from outside Israel.")


@wedge_app.command("purge")
def wedge_purge(
    days: Annotated[int, typer.Option("--days", help="Delete runs older than this, unless the user opted in.")] = 30,
) -> None:
    """Delete expired pilot runs now. The server does this daily while the pilot is on."""
    from realize_core.wedge import purge_expired

    typer.echo(f"Deleted {purge_expired(days=days)} expired run(s).")
