"""stdio transport for the built-in MCP server (STORY-37).

A desktop agent (Claude Desktop, Claude Code, Cursor, ...) starts
``realize-os mcp stdio --user <email>`` as a child process and speaks
JSON-RPC over the process's stdin and stdout. No port is opened.

Identity: there is no HTTP request to authenticate, so the caller is named
with ``--user`` when the server starts and must have an entry in
``users.yaml``. Identity comes from arguments only, never from environment
variables. The user's role and ventures apply exactly as on the HTTP
transports; ``--venture`` can only narrow the session to some of the user's
ventures. There is no anonymous or default-owner fallback: without a valid
identity the server refuses to start, in every environment.

Configuration: the CLI reads ``realize-os.yaml``, ``users.yaml``, ``.env``
and data from an explicit, absolute ``--directory`` or from the folder
RealizeOS is installed in, never from the folder the agent starts it in.
Admin tools are served only with ``--allow-admin`` on the command line;
``mcp.allow_admin`` doesn't widen a stdio session.

stdout carries only JSON-RPC. Before anything else runs, the real stdout is
kept for the transport and file descriptor 1 is pointed at stderr, so stray
``print()`` calls, C extensions and child processes can't corrupt the
stream. Logging goes to stderr.

It reuses the same tool registry, families, ``allow_admin``, permission
checks, venture guard and audit logging as ``/mcp`` and ``/mcp/sse``
(:func:`realize_core.mcp_server.server.build_mcp_server`).
"""

from __future__ import annotations

import dataclasses
import functools
import io
import logging
import os
import sys
from collections.abc import Sequence
from io import TextIOWrapper
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from realize_api.dependencies import CurrentUser

from realize_core.mcp_server.auth import bind_user, reset_user, validate_production_auth
from realize_core.mcp_server.config import McpConfig, mcp_config_from_env
from realize_core.mcp_server.server import build_mcp_server

logger = logging.getLogger(__name__)


class StdioStartupError(RuntimeError):
    """The stdio server refused to start (no identity, MCP off, unknown venture, ...)."""


def _is_plain_token(value: str) -> bool:
    """True for a non-empty value without whitespace or control characters."""
    return bool(value) and all(c.isprintable() and not c.isspace() for c in value)


def resolve_stdio_user(user_id: str | None, ventures: Sequence[str] = ()) -> CurrentUser:
    """The MCP caller for a stdio session, from ``users.yaml``.

    Args:
        user_id: Email of a user in ``users.yaml``. Required: there is no default.
        ventures: Venture keys that narrow the session. Each must be one of the
            user's own ventures when ``users.yaml`` limits them.

    Returns:
        A :class:`CurrentUser` with the user's email and role, marked as an
        outside agent (``agent:stdio`` scope, STORY-37). Its ventures (``--venture``,
        else the user's own) are carried as ``venture:<key>`` scopes, the same way
        a scoped JWT does it.

    Raises:
        StdioStartupError: No user named, no ``users.yaml``, the user isn't in
            it or is a pilot account (hosted-only, STORY-46), a value isn't a
            plain token, or a venture is outside the user's ventures.
    """
    from realize_core.security.agent_tokens import STDIO_SCOPE
    from realize_core.security.users import USERS_FILE, get_user
    from realize_core.security.venture_scope import VENTURE_SCOPE_PREFIX

    name = (user_id or "").strip()
    if not name:
        raise StdioStartupError(
            "No identity: pass --user <email of a users.yaml user>. The stdio server never runs as an anonymous owner."
        )
    if not _is_plain_token(name):
        raise StdioStartupError(f"--user {name!r} is not a valid user id")
    # users.yaml only: the REALIZE_ADMIN_USER environment fallback doesn't apply here.
    if not Path(USERS_FILE).is_file():
        raise StdioStartupError(
            f"No {USERS_FILE} in {Path.cwd()}: the stdio server needs a users.yaml user "
            "(pass --directory /absolute/path/to/RealizeOS)"
        )
    user = get_user(name)
    if user is None:
        raise StdioStartupError(
            f"{name!r} is not in {USERS_FILE}. Add them there (role and ventures decide what the agent can do)."
        )
    if user.pilot:
        # A pilot account (STORY-46) is hosted-only: its agent connects to the pilot
        # server's /mcp with OAuth. A local session would sit next to the host's files.
        raise StdioStartupError(
            f"{user.email} is a pilot account: pilot accounts connect only to the hosted pilot "
            "(its /mcp URL, signing in with OAuth), never over stdio."
        )

    requested = tuple(dict.fromkeys((v or "").strip() for v in ventures))
    invalid = [v for v in requested if not _is_plain_token(v)]
    if invalid:
        raise StdioStartupError(f"--venture needs a plain venture key, got {invalid[0]!r}")
    if user.ventures:
        outside = [v for v in requested if v not in user.ventures]
        if outside:
            raise StdioStartupError(f"{user.email} has no access to venture(s): {', '.join(outside)}")
    # The client of a stdio session is always an AI agent (STORY-37, ADR 0004): it is
    # governed as an outside agent. The marker is set here, server-side, so it can't
    # be spoofed; the user's role and ventures stay the upper bound. An unrestricted
    # user without --venture gets every configured venture in prepare_stdio.
    session_ventures = requested or user.ventures
    scopes = [STDIO_SCOPE] + [f"{VENTURE_SCOPE_PREFIX}{v}" for v in session_ventures]
    return CurrentUser(user_id=user.email, role=user.role, scopes=scopes)


def build_stdio_state(config: dict, kb_path: str | Path | None = None) -> SimpleNamespace:
    """Initialise the app state MCP tools read, without the HTTP server.

    Mirrors the parts of the API lifespan the tools need: config, systems and
    the governance tool gate (via :func:`realize_core.config_runtime.reload_app_config`),
    the memory store, the operational database, the tool registry, custom
    RBAC roles, the audit log location and the KB index.

    Args:
        config: The loaded ``realize-os.yaml``.
        kb_path: KB root; defaults to ``KB_PATH``.
    """
    from realize_core.config import KB_PATH
    from realize_core.config_runtime import reload_app_config

    kb = Path(kb_path) if kb_path is not None else KB_PATH
    state = SimpleNamespace(
        kb_path=kb,
        store_errors={},
        tool_gate=None,
        shared_config=config.get(
            "shared",
            {"identity": "shared/identity.md", "preferences": "shared/user-preferences.md"},
        ),
    )

    from realize_core.memory.store import init_db

    init_db()

    from realize_core.db.migrations import run_migrations
    from realize_core.migration.engine import MigrationEngine

    run_migrations()
    MigrationEngine().migrate_up()

    from realize_core.tools.tool_registry import get_tool_registry

    registry = get_tool_registry()
    if registry.tool_count == 0:
        registry.auto_discover()

    # Config, systems and the tool gate, exactly as a Settings reload applies them.
    reload_app_config(state, kb, config)

    _load_custom_roles(config)

    data_path = os.environ.get("DATA_PATH", "data")
    os.environ.setdefault("REALIZE_AUDIT_LOG_DIR", str(Path(data_path) / "audit"))

    _index_kb(kb, getattr(state, "systems", None))
    return state


def _load_custom_roles(config: dict) -> None:
    """Load ``roles.yaml`` custom RBAC roles, as the API does at startup."""
    import yaml

    from realize_core.security.rbac import get_rbac_manager

    roles_path = Path(config.get("kb_path", ".")) / "roles.yaml"
    if not roles_path.exists():
        return
    try:
        count = get_rbac_manager().load_from_yaml(roles_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        logger.warning("Custom RBAC roles not loaded from %s: %s", roles_path, exc)
        return
    logger.info("Loaded %d custom RBAC roles", count)


def _index_kb(kb_path: Path, systems: dict | None = None) -> None:
    """Bring the KB search index up to date (incremental), as the API does at startup."""
    import sqlite3

    from realize_core.kb.indexer import index_kb_files

    try:
        index_kb_files(str(kb_path), systems_config=systems)
    except (OSError, sqlite3.Error) as exc:
        logger.warning("KB indexing skipped (kb_search may miss recent files): %s", exc)


def stdio_mcp_config(config: dict, *, allow_admin: bool = False) -> McpConfig:
    """The MCP config for a stdio session.

    Same as for HTTP, except admin tools: over stdio they are served only
    when ``allow_admin`` is passed on the command line. ``mcp.allow_admin`` /
    ``MCP_ALLOW_ADMIN`` don't widen a stdio session.

    Args:
        config: The loaded ``realize-os.yaml``.
        allow_admin: ``--allow-admin`` was given.
    """
    mcp_config = mcp_config_from_env(config)
    if mcp_config.allow_admin and not allow_admin:
        logger.warning("mcp.allow_admin is ignored over stdio: admin tools stay off unless --allow-admin is given")
    return dataclasses.replace(mcp_config, allow_admin=allow_admin)


def prepare_stdio(
    user_id: str | None,
    ventures: Sequence[str] = (),
    *,
    allow_admin: bool = False,
    config: dict | None = None,
    kb_path: str | Path | None = None,
) -> tuple[Server, CurrentUser, McpConfig]:
    """Check identity and configuration, build the app state and the MCP server.

    Identity and configuration refusals happen before any state is built; an
    unknown ``--venture`` is caught once the systems are loaded.

    Args:
        user_id: ``users.yaml`` email the agent acts as.
        ventures: Optional venture keys that narrow the session.
        allow_admin: ``--allow-admin`` was given (see :func:`stdio_mcp_config`).
        config: Loaded ``realize-os.yaml``; read from disk when None.
        kb_path: KB root; defaults to ``KB_PATH``.

    Returns:
        The MCP server, the bound caller and the effective MCP config.

    Raises:
        StdioStartupError: MCP is off, the identity is missing or invalid, or
            a named venture doesn't exist.
        realize_core.mcp_server.auth.MCPProductionAuthError: admin tools on in
            production without strong JWT settings.
    """
    from realize_core.config import load_config

    if config is None:
        config = load_config()
    mcp_config = stdio_mcp_config(config, allow_admin=allow_admin)
    if not mcp_config.enabled:
        raise StdioStartupError("MCP is off. Set MCP_ENABLED=true in .env (or mcp.enabled: true in realize-os.yaml).")
    validate_production_auth(allow_admin=mcp_config.allow_admin)
    user = resolve_stdio_user(user_id, ventures)

    state = build_stdio_state(config, kb_path)
    named = [v.strip() for v in ventures if (v or "").strip()]
    unknown = [v for v in named if v not in state.systems]
    if unknown:
        raise StdioStartupError(
            f"Unknown venture(s): {', '.join(unknown)}. Known: {', '.join(state.systems) or 'none'}"
        )
    if not _named_ventures(user):
        # An agent is always venture-scoped: an unrestricted user's session sees
        # the ventures configured when it starts.
        from realize_core.security.venture_scope import VENTURE_SCOPE_PREFIX

        user = CurrentUser(
            user_id=user.user_id,
            role=user.role,
            scopes=list(user.scopes) + [f"{VENTURE_SCOPE_PREFIX}{v}" for v in state.systems],
        )

    server = build_mcp_server(app_state=state, mcp_config=mcp_config)
    return server, user, mcp_config


def _named_ventures(user: CurrentUser) -> list[str]:
    """Ventures named with ``--venture`` (carried as ``venture:<key>`` scopes)."""
    from realize_core.security.venture_scope import VENTURE_SCOPE_PREFIX

    return [s[len(VENTURE_SCOPE_PREFIX) :] for s in user.scopes if s.startswith(VENTURE_SCOPE_PREFIX)]


async def serve_stdio(server: Server, user: CurrentUser, *, stdout: Any = None) -> None:
    """Serve MCP over stdin/stdout as ``user`` until the client closes stdin.

    Args:
        server: From :func:`prepare_stdio`.
        user: The caller every tool call runs as.
        stdout: ``anyio`` text file for JSON-RPC output; defaults to the SDK's
            wrapper around ``sys.stdout``.
    """
    token = bind_user(user)
    try:
        async with stdio_server(stdout=stdout) as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        reset_user(token)


def claim_stdout() -> Any:
    """Keep the real stdout for JSON-RPC and send everything else to stderr.

    Duplicates file descriptor 1 for the transport, then points fd 1 at
    stderr, so ``print()``, C extensions and inherited child processes all
    write to stderr. Falls back to replacing ``sys.stdout`` when stdout has
    no file descriptor.

    Returns:
        An ``anyio`` text file writing UTF-8, ``\\n``-terminated lines to the real stdout.
    """
    sys.stdout.flush()
    try:
        stdout_fd = sys.stdout.fileno()
        stderr_fd = sys.stderr.fileno()
    except (AttributeError, OSError, ValueError, io.UnsupportedOperation):
        raw = sys.stdout.buffer
        sys.stdout = sys.stderr
    else:
        raw = open(os.dup(stdout_fd), "wb")  # noqa: SIM115 - lives as long as the process
        os.dup2(stderr_fd, stdout_fd)
    return anyio.wrap_file(TextIOWrapper(raw, encoding="utf-8", newline="\n"))


def _logging_to_stderr() -> None:
    """Send all log output to stderr (stdout belongs to JSON-RPC)."""
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream in (sys.stdout, sys.__stdout__):
            handler.setStream(sys.stderr)
    if not root.handlers:
        logging.basicConfig(
            stream=sys.stderr,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )


def _audit_session_start(user: CurrentUser, mcp_config: McpConfig) -> None:
    """Record who opened a stdio session, with which scope."""
    from realize_core.security.audit import get_audit_logger

    try:
        get_audit_logger().log(
            user_id=user.user_id,
            action="mcp.stdio.session_start",
            outcome="success",
            channel="mcp",
            resource_type="mcp_transport",
            resource_id="stdio",
            metadata={"role": user.role, "scopes": list(user.scopes), "families": mcp_config.families},
        )
    except OSError as exc:
        logger.warning("Audit log for the stdio session failed: %s", exc)


def run_stdio(user_id: str | None, ventures: Sequence[str] = (), *, allow_admin: bool = False) -> None:
    """Run the MCP server over stdio in the current working directory.

    The CLI makes that directory the RealizeOS folder first (``--directory``
    or the install folder). Claims stdout first, so nothing printed during
    startup reaches the client.

    Args:
        user_id: ``users.yaml`` email the agent acts as.
        ventures: Optional venture keys that narrow the session.
        allow_admin: ``--allow-admin`` was given.

    Raises:
        StdioStartupError: see :func:`prepare_stdio`.
        realize_core.mcp_server.auth.MCPProductionAuthError: see :func:`prepare_stdio`.
    """
    transport_out = claim_stdout()
    _logging_to_stderr()
    server, user, mcp_config = prepare_stdio(user_id, ventures, allow_admin=allow_admin)
    _audit_session_start(user, mcp_config)

    from realize_core.mcp_server.venture_guard import caller_ventures

    allowed = caller_ventures(user)
    logger.info(
        "MCP stdio server ready — user=%s role=%s ventures=%s families=%s allow_admin=%s tools=%s",
        user.user_id,
        user.role,
        "all" if allowed is None else ",".join(sorted(allowed)),
        ",".join(mcp_config.families),
        mcp_config.allow_admin,
        "all" if mcp_config.tools is None else ",".join(mcp_config.tools) or "none",
    )
    anyio.run(functools.partial(serve_stdio, server, user, stdout=transport_out))
