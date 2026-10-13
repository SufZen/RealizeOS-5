"""``realize-os agent-token`` — venture-scoped tokens for outside agents (STORY-37).

Commands (run on the server, in the project folder, against the local database):

  create  — issue a token for one agent; prints the token once
  list    — every token, without secrets
  revoke  — revoke a token now and withdraw its pending held writes

``python cli.py agent-token ...`` works the same.
"""

from __future__ import annotations

import os
from typing import Annotated

import typer

from realize_core.cli_app.formatters import emit
from realize_core.cli_app.state import get_state

agent_token_app = typer.Typer(no_args_is_help=True)

_LIST_COLUMNS = ("id", "name", "user", "ventures", "status", "created_at", "expires_at", "last_used_at")


def _enter(directory: str) -> None:
    """Work in the project folder (where users.yaml and realize-os.yaml live)."""
    if directory and directory != ".":
        os.chdir(directory)


def _known_ventures() -> list[str] | None:
    """Configured venture keys, or None when no venture is configured here."""
    from realize_core.config import KB_PATH, build_systems_dict, load_config

    systems = build_systems_dict(load_config(), KB_PATH)
    return list(systems) or None


def _auth_is_on() -> bool:
    jwt = os.environ.get("REALIZE_JWT_ENABLED", "").lower() in ("true", "1", "yes")
    return bool(os.environ.get("REALIZE_API_KEY")) or jwt


@agent_token_app.command("create")
def agent_token_create(
    name: Annotated[str, typer.Option("--name", "-n", help="Label, e.g. claude-desktop-acme.")],
    user: Annotated[str, typer.Option("--user", "-u", help="users.yaml user (email) the agent acts for.")],
    venture: Annotated[
        list[str],
        typer.Option("--venture", "-v", help="Venture the agent may see. Repeat, or separate with commas."),
    ],
    expires_in_days: Annotated[
        int | None, typer.Option("--expires-in-days", help="Optional lifetime in days (1-3650).")
    ] = None,
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Issue a venture-scoped token for an outside agent. The token is printed once."""
    from realize_core.security.agent_tokens import AgentTokenError, create_token

    _enter(directory)
    ventures = [v.strip() for item in venture for v in item.split(",") if v.strip()]
    known = _known_ventures()
    try:
        token, secret = create_token(
            name=name,
            user_email=user,
            ventures=ventures,
            expires_in_days=expires_in_days,
            created_by="cli",
            known_ventures=known,
            channel="cli",
        )
    except AgentTokenError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Agent token created: {token.id} ({token.name})")
    typer.echo(f"  Acts for: {token.user_email}")
    typer.echo(f"  Ventures: {', '.join(token.ventures)}")
    typer.echo(f"  Expires:  {token.expires_at or 'never'}")
    typer.echo("")
    typer.echo("Copy this token now. It is shown only once:")
    typer.echo("")
    typer.echo(f"  {secret}")
    typer.echo("")
    typer.echo("Send it as 'Authorization: Bearer <token>' (MCP at /mcp, or the REST API).")
    if known is None:
        typer.echo("Note: no ventures are configured in this folder, so the venture names were not checked.")
    if not _auth_is_on():
        typer.echo("Warning: auth is off (REALIZE_API_KEY unset, JWT disabled), so the API is open and the token")
        typer.echo("         limits nothing. Set REALIZE_API_KEY before connecting an outside agent.")


@agent_token_app.command("list")
def agent_token_list(
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """List agent tokens (secrets are never stored, so never shown)."""
    from realize_core.security.agent_tokens import list_tokens

    _enter(directory)
    rows = []
    for token in list_tokens():
        row = token.to_dict()
        row["ventures"] = ",".join(row["ventures"])
        rows.append(row)
    state = get_state()
    emit(rows, output_format=state.output_format, columns=_LIST_COLUMNS, title="Agent tokens")


@agent_token_app.command("revoke")
def agent_token_revoke(
    token_id: Annotated[str, typer.Argument(help="Token id (from 'agent-token list').")],
    directory: Annotated[str, typer.Option("--directory", "-d", help="Project root directory.")] = ".",
) -> None:
    """Revoke an agent token now. Its pending held writes are withdrawn."""
    from realize_core.security.agent_tokens import revoke_token

    _enter(directory)
    revoked = revoke_token(token_id.strip(), revoked_by="cli", channel="cli")
    if revoked is None:
        typer.echo(f"Error: no agent token '{token_id}'", err=True)
        raise typer.Exit(code=1)
    token, withdrawn = revoked
    typer.echo(f"Revoked {token.id} ({token.name}). Held writes withdrawn: {withdrawn}.")
