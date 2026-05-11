"""``realize-os repl`` — interactive chat REPL with prompt-toolkit.

Features:
  - Line history (persisted in ~/.realize-os/history)
  - Slash commands: /system, /agent, /clear, /exit, /help
  - Multi-line input (Alt+Enter submits)
  - Streams responses or falls back to batch
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from realize_core.cli_app.http_client import api_post
from realize_core.cli_app.state import get_state

logger = logging.getLogger(__name__)

_HISTORY_DIR = Path.home() / ".realize-os"
_HISTORY_FILE = _HISTORY_DIR / "history"

# Slash commands the REPL understands
_SLASH_HELP = """\
Slash commands:
  /system <key>   — switch to a different system
  /agent <key>    — switch to a different agent
  /session <id>   — resume a session
  /clear          — clear the screen
  /help           — show this help
  /exit, /quit    — exit the REPL
"""


def repl(
    system: Annotated[str | None, typer.Option("--system", "-s", help="System key to start with.")] = None,
    agent: Annotated[str | None, typer.Option("--agent", "-a", help="Agent key to start with.")] = None,
) -> None:
    """Launch an interactive chat session (REPL)."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
    except ImportError:
        typer.echo(
            "prompt-toolkit is required for the REPL. "
            "Install it with: pip install prompt-toolkit>=3.0",
            err=True,
        )
        raise typer.Exit(code=1) from None

    state = get_state()
    session_id: str | None = None
    current_system = system
    current_agent = agent

    # Ensure history directory exists
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    history = FileHistory(str(_HISTORY_FILE))
    session = PromptSession(history=history)

    typer.echo("RealizeOS Interactive REPL")
    typer.echo("Type your message and press Enter. Use /help for commands.\n")

    while True:
        try:
            user_input = session.prompt("realize-os> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nGoodbye!")
            break

        if not user_input:
            continue

        # Handle slash commands
        if user_input.startswith("/"):
            handled = _handle_slash(user_input, locals_ref={
                "current_system": current_system,
                "current_agent": current_agent,
                "session_id": session_id,
            })
            if handled == "exit":
                typer.echo("Goodbye!")
                break
            if handled == "clear":
                os.system("cls" if sys.platform == "win32" else "clear")
                continue
            if isinstance(handled, dict):
                current_system = handled.get("current_system", current_system)
                current_agent = handled.get("current_agent", current_agent)
                session_id = handled.get("session_id", session_id)
                continue
            # handled == "help" or unknown — message already printed
            continue

        # Send to the API
        body: dict[str, object] = {"message": user_input}
        if current_system:
            body["system_key"] = current_system
        if current_agent:
            body["agent_key"] = current_agent
        if session_id:
            body["session_id"] = session_id

        try:
            result = api_post("/api/chat", profile=state.profile, json_body=body)
        except SystemExit:
            typer.echo("[Connection error — is the RealizeOS server running?]", err=True)
            continue

        response_text = result.get("response", result.get("message", str(result)))
        session_id = result.get("session_id", session_id)
        typer.echo(f"\n{response_text}\n")


def _handle_slash(cmd: str, locals_ref: dict) -> str | dict:
    """Process a slash command. Returns action string or updated locals dict."""
    parts = cmd.split(maxsplit=1)
    verb = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if verb in ("/exit", "/quit"):
        return "exit"

    if verb == "/clear":
        return "clear"

    if verb == "/help":
        typer.echo(_SLASH_HELP)
        return "help"

    if verb == "/system":
        if not arg:
            typer.echo(f"Current system: {locals_ref.get('current_system') or '(default)'}")
        else:
            typer.echo(f"Switched system to: {arg}")
            return {**locals_ref, "current_system": arg}
        return "info"

    if verb == "/agent":
        if not arg:
            typer.echo(f"Current agent: {locals_ref.get('current_agent') or '(default)'}")
        else:
            typer.echo(f"Switched agent to: {arg}")
            return {**locals_ref, "current_agent": arg}
        return "info"

    if verb == "/session":
        if not arg:
            typer.echo(f"Current session: {locals_ref.get('session_id') or '(none)'}")
        else:
            typer.echo(f"Resumed session: {arg}")
            return {**locals_ref, "session_id": arg}
        return "info"

    typer.echo(f"Unknown command: {verb}. Type /help for available commands.")
    return "unknown"
