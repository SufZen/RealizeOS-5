"""Hosting the self-serve pilot (STORY-46): invite-only accounts and the retention job.

A pilot user signs in from their own agent (OAuth connector) and may only use
the tender-register tools. Each invite adds a ``viewer`` to ``users.yaml``,
limited to a sandbox venture of their own that holds nothing, so even tools
outside the pilot see no client data. The password is shown once and stored
only as a bcrypt hash.

:func:`purge_loop` runs :func:`realize_core.wedge.store.purge_expired` once a
day while the server runs with ``features.wedge`` on, so runs are deleted after
30 days unless the user asked to be contacted.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import secrets
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

from realize_core.security.users import USERS_FILE, hash_password
from realize_core.wedge.store import purge_expired

logger = logging.getLogger(__name__)

#: Pilot users can read and run the pilot tools, nothing else.
PILOT_ROLE = "viewer"
#: Sandbox venture keys start with this, followed by a hash of the email.
SANDBOX_PREFIX = "pilot-"
PURGE_INTERVAL_SECONDS = 24 * 60 * 60

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


#: The tools a pilot user's agent may be offered (``mcp.tools`` on the pilot host).
PILOT_TOOLS = frozenset({"tender_register_method", "tender_register_submit", "request_audit_call", "realize_health"})


class PilotInviteError(ValueError):
    """An invite that can't be created (bad email, existing user, no users.yaml, not a pilot host)."""


def pilot_profile_problems(config: dict) -> list[str]:
    """Why this instance isn't a pilot host, or [] when it is.

    Invites give outsiders a login, so they're only allowed where the pilot is
    on and the MCP server offers nothing but the pilot tools. That keeps an
    invite from opening the practice's own server, which holds client brains.
    """
    from realize_core.config import get_features
    from realize_core.mcp_server.config import mcp_config_from_env

    problems = []
    if not get_features(config).get("wedge"):
        problems.append("features.wedge is off")
    tools = mcp_config_from_env(config).tools
    if tools is None:
        problems.append("mcp.tools is not set, so every tool would be offered")
    elif not set(tools) <= PILOT_TOOLS:
        extra = ", ".join(sorted(set(tools) - PILOT_TOOLS))
        problems.append(f"mcp.tools offers more than the pilot tools: {extra}")
    return problems


@dataclass(frozen=True)
class PilotInvite:
    """The result of :func:`invite`. ``password`` is shown once and never stored."""

    email: str
    venture: str
    password: str
    written: bool
    entry_yaml: str
    backup: Path | None = None


def sandbox_venture(email: str) -> str:
    """The pilot user's own empty venture key, stable for an email."""
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:10]
    return f"{SANDBOX_PREFIX}{digest}"


def _write_text(path: Path, text: str) -> None:
    """Write ``text`` atomically, or in place when the file is a bind mount that can't be replaced.

    The temporary file is created owner-only and then given the original file's
    mode, so a ``0600`` users file never becomes readable by others on replace.
    """
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        path.write_text(text, encoding="utf-8")


def invite(email: str, *, config: dict, users_file: Path | None = None) -> PilotInvite:
    """Add a pilot user to ``users.yaml`` with a fresh password.

    Args:
        email: The pilot user's sign-in email.
        config: This instance's loaded ``realize-os.yaml``; it must be a pilot host
            (see :func:`pilot_profile_problems`).
        users_file: The users file; defaults to ``users.yaml`` in the working directory.

    Returns:
        The invite. When the file can't be written (for example a read-only
        mount), ``written`` is False and ``entry_yaml`` holds the entry to add by hand.

    Raises:
        PilotInviteError: This isn't a pilot host, the email is invalid or already
            a user, or there is no usable ``users.yaml``. Creating one would replace a single-owner
            ``REALIZE_ADMIN_USER`` login, so the owner must create it first.
    """
    problems = pilot_profile_problems(config)
    if problems:
        raise PilotInviteError("Invites only work on a pilot host: " + "; ".join(problems) + ".")
    address = (email or "").strip().lower()
    if not _EMAIL.match(address):
        raise PilotInviteError(f"Not an email address: {email!r}")
    path = users_file or Path(USERS_FILE)
    if not path.is_file():
        raise PilotInviteError(
            f"{path} not found. Create it with your own owner account first (see users.yaml.example): "
            "once it exists it replaces the REALIZE_ADMIN_USER login."
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PilotInviteError(f"{path} is not valid YAML: {exc}") from exc
    users = data.get("users") if isinstance(data, dict) else None
    if not isinstance(users, list):
        raise PilotInviteError(f"{path}: top-level 'users' key missing or not a list")
    if any(isinstance(u, dict) and str(u.get("email", "")).strip().lower() == address for u in users):
        raise PilotInviteError(f"{address} is already a user")

    password = secrets.token_urlsafe(18)
    venture = sandbox_venture(address)
    if venture in {s.get("key") for s in config.get("systems") or [] if isinstance(s, dict)}:
        raise PilotInviteError(f"A venture named {venture} exists; a pilot sandbox must be empty")
    entry = {"email": address, "role": PILOT_ROLE, "ventures": [venture], "password_hash": hash_password(password)}
    entry_yaml = yaml.safe_dump({"users": [entry]}, sort_keys=False, allow_unicode=True)

    users.append(entry)
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    backup: Path | None = path.with_name(f"{path.name}.bak")
    try:
        shutil.copy2(path, backup)  # keeps the file mode: it holds password hashes too
    except OSError as exc:  # e.g. a single-file bind mount in a read-only container
        logger.warning("No backup of %s (%s)", path, exc)
        backup = None
    try:
        _write_text(path, text)
    except OSError as exc:
        logger.warning("Could not write %s (%s); the entry must be added by hand", path, exc)
        return PilotInvite(address, venture, password, written=False, entry_yaml=entry_yaml)
    logger.info("Pilot user %s invited (venture %s)", address, venture)
    return PilotInvite(address, venture, password, written=True, entry_yaml=entry_yaml, backup=backup)


async def purge_loop(interval_seconds: float = PURGE_INTERVAL_SECONDS) -> None:
    """Delete expired pilot runs now and then once per ``interval_seconds``, until cancelled."""
    while True:
        try:
            deleted = await asyncio.to_thread(purge_expired)
        except (sqlite3.Error, OSError):
            logger.exception("Pilot run purge failed; retrying at the next interval")
        else:
            if deleted:
                logger.info("Purged %d expired pilot run(s)", deleted)
        await asyncio.sleep(interval_seconds)
