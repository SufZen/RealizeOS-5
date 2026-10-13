"""``realize-os wedge`` — host the self-serve tender register pilot (STORY-46).

Commands:
  invite     — add an invite-only pilot user (shows their password once)
  funnel     — runs, users and converted users per market, and the pass check
  contacts   — the people who asked for a call and are waiting
  contacted  — mark a person as contacted (takes them out of the queue)
  purge      — delete expired runs now (the server also does it daily)
"""

from __future__ import annotations

import json
import os
from typing import Annotated

import typer

from realize_core.utils.text import escape_nonprintable as _safe

# Contacts and markets come from pilot users, who are outsiders: every stored
# value shown here goes through _safe. The store already strips control
# characters; this also covers rows written before that.

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
    """Show the pilot funnel per market and the pass check, from recorded runs only.

    ``converted`` counts each person who asked for a call once; ``requests`` is
    how many runs asked (volume only). The rate is converted / users.
    """
    from realize_core.wedge import funnel, funnel_summary

    rows = funnel(days=days)
    summary = funnel_summary(days=days)
    if output == "json":
        typer.echo(json.dumps({"markets": rows, "summary": summary}, indent=2))
        return
    if not rows:
        typer.echo(f"No pilot runs in the last {days} days.")
        return
    typer.echo(f"{'market':<8}{'runs':>6}{'users':>7}{'converted':>11}{'requests':>10}{'rate':>7}{'avg lvl':>9}")
    for r in rows:
        typer.echo(
            f"{_safe(r['market'] or '-'):<8}{r['runs']:>6}{r['users']:>7}{r['converted_users']:>11}"
            f"{r['calls_requested']:>10}{r['call_rate']:>7.0%}{r['avg_verification']:>9}"
        )
    verdict = "PASS" if summary["passed"] else "not yet"
    typer.echo(
        f"All markets: {summary['converted_users']} of {summary['users']} users asked for a call "
        f"({summary['call_rate']:.0%}); {summary['converted_outside_home']} outside Israel. {verdict}"
    )
    typer.echo("Pass: 30% of users ask for a call, and at least one of them is outside Israel.")


@wedge_app.command("contacts")
def wedge_contacts(
    include_handled: Annotated[bool, typer.Option("--all", help="Include people already contacted.")] = False,
    output: Annotated[str, typer.Option("--format", help="Output format: text or json.")] = "text",
) -> None:
    """List the people who asked for a call, oldest waiting first."""
    from realize_core.wedge import contacts

    rows = contacts(include_handled=include_handled)
    if output == "json":
        typer.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        typer.echo("Nobody is waiting for a call." if not include_handled else "No call requests yet.")
        return
    for r in rows:
        state = f"contacted {r['handled_at'][:10]} by {_safe(r['handled_by'])}" if r["handled_at"] else "waiting"
        typer.echo(
            f"{_safe(r['user_id'])}  contact: {_safe(r['contact'])}  markets: {_safe(', '.join(r['markets']))}  "
            f"asked {r['requests']}x since {_safe(r['first_requested_at'][:10])}  [{state}]"
        )
    typer.echo("After calling someone: realize-os wedge contacted <their email>")


@wedge_app.command("contacted")
def wedge_contacted(
    user: Annotated[str, typer.Argument(help="The pilot user's email, as listed by `wedge contacts`.")],
    by: Annotated[str, typer.Option("--by", help="Who handled it (recorded).")] = "",
) -> None:
    """Mark a person as contacted, which takes them out of the queue."""
    import getpass

    from realize_core.wedge import mark_contacted

    handled_by = by.strip() or getpass.getuser()
    done = mark_contacted(user.strip().lower(), handled_by)
    if not done:
        typer.echo(f"{user} has no waiting call request.", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Marked {user} as contacted ({done} request(s)).")


@wedge_app.command("purge")
def wedge_purge(
    days: Annotated[int, typer.Option("--days", help="Delete runs older than this, unless the user opted in.")] = 30,
) -> None:
    """Delete expired pilot runs now. The server does this daily while the pilot is on."""
    from realize_core.wedge import purge_expired

    typer.echo(f"Deleted {purge_expired(days=days)} expired run(s).")
