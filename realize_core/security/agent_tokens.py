"""
Venture-scoped agent tokens (STORY-37): one outside agent sees one client's brain.

An owner or admin issues a named token for an outside agent (Claude Desktop,
Cursor, ChatGPT, n8n, ...). The token:

- is bound to a configured ``users.yaml`` user, whose role applies;
- names at least one venture. On every request the token's ventures are
  intersected with the user's own venture list, so a token never widens
  access, and a token whose ventures all fall away stops working;
- may expire, records when it was last used, and can be revoked;
- is shown once at creation and stored only as a SHA-256 hash;
- looks like ``rzag_<id>_<secret>``, so it can't be confused with the
  API key, a JWT (which has dots) or an MCP OAuth token (``rzat_``).

A request made with one is an **agent principal**: ``request.state.user_id``
is ``agent:<id>`` (its own identity in the audit log, the approval queue,
conversation memory and the rate limiter) and its scopes are
``["agent:<id>", "venture:<key>", ...]``. Existing RBAC and venture scope
apply unchanged; governance uses :func:`is_agent_principal` to tell an
outside agent from a person (an agent never approves its own held write).

Tokens live in the ``agent_tokens`` table (migration 012). The table is also
created on first use, like the other small stores.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

#: Every agent token starts with this, so logs and the auth middleware can tell it apart.
TOKEN_PREFIX = "rzag_"
#: ``request.state.user_id`` of an agent principal is ``agent:<token id>``.
PRINCIPAL_PREFIX = "agent:"
#: Scope that marks the caller as an outside agent (``agent:<token id>``).
AGENT_SCOPE_PREFIX = "agent:"
#: Same prefix as :data:`realize_core.security.venture_scope.VENTURE_SCOPE_PREFIX`.
VENTURE_SCOPE_PREFIX = "venture:"

_ID_HEX_CHARS = 12
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
_VENTURE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_VENTURES = 50
MAX_EXPIRY_DAYS = 3650
#: ``last_used_at`` is written at most this often per token (one write per request is wasteful).
LAST_USED_RESOLUTION = timedelta(seconds=60)

DDL = """
CREATE TABLE IF NOT EXISTS agent_tokens (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    token_hash    TEXT NOT NULL UNIQUE,
    user_email    TEXT NOT NULL,
    ventures      TEXT NOT NULL,
    created_by    TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    expires_at    TEXT,
    last_used_at  TEXT,
    revoked_at    TEXT,
    revoked_by    TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_tokens_user ON agent_tokens(user_email);
"""


class AgentTokenError(ValueError):
    """A token can't be created as asked (unknown user, venture outside the user's list, ...)."""


@dataclass(frozen=True)
class AgentToken:
    """A stored agent token. Never carries the secret or its hash."""

    id: str
    name: str
    user_email: str
    ventures: tuple[str, ...]
    created_by: str
    created_at: str
    expires_at: str | None
    last_used_at: str | None
    revoked_at: str | None
    revoked_by: str | None

    @property
    def principal_id(self) -> str:
        """The ``user_id`` requests made with this token carry."""
        return f"{PRINCIPAL_PREFIX}{self.id}"

    @property
    def status(self) -> str:
        """``revoked``, ``expired`` or ``active``."""
        if self.revoked_at:
            return "revoked"
        if _expired(self.expires_at):
            return "expired"
        return "active"

    def to_dict(self) -> dict:
        """Public fields for listings (no secret, no hash)."""
        return {
            "id": self.id,
            "name": self.name,
            "principal": self.principal_id,
            "user": self.user_email,
            "ventures": list(self.ventures),
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_used_at": self.last_used_at,
            "revoked_at": self.revoked_at,
            "revoked_by": self.revoked_by,
        }


@dataclass(frozen=True)
class AgentPrincipal:
    """Who a live agent token stands for on this request."""

    token_id: str
    name: str
    bound_user: str
    role: str
    ventures: frozenset[str]

    @property
    def user_id(self) -> str:
        """The principal id (``agent:<token id>``)."""
        return f"{PRINCIPAL_PREFIX}{self.token_id}"

    @property
    def scopes(self) -> list[str]:
        """The agent marker plus one ``venture:<key>`` scope per effective venture."""
        return [f"{AGENT_SCOPE_PREFIX}{self.token_id}"] + [f"{VENTURE_SCOPE_PREFIX}{v}" for v in sorted(self.ventures)]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    moment = _parse(expires_at)
    # An unreadable expiry fails closed.
    return moment is None or moment <= _now()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _conn() -> sqlite3.Connection:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    conn.executescript(DDL)
    return conn


def _row_to_token(row: sqlite3.Row) -> AgentToken:
    try:
        ventures = tuple(json.loads(row["ventures"]) or ())
    except (TypeError, ValueError):
        ventures = ()
    return AgentToken(
        id=row["id"],
        name=row["name"],
        user_email=row["user_email"],
        ventures=ventures,
        created_by=row["created_by"] or "",
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        last_used_at=row["last_used_at"],
        revoked_at=row["revoked_at"],
        revoked_by=row["revoked_by"],
    )


def _audit(action: str, user_id: str, *, outcome: str = "success", severity: str = "info", **fields) -> None:
    """Write an audit event; a failing audit log never breaks token handling."""
    try:
        from realize_core.security.audit import get_audit_logger

        get_audit_logger().log(
            user_id=user_id,
            action=action,
            outcome=outcome,
            resource_type="agent_token",
            severity=severity,
            **fields,
        )
    except (OSError, ValueError, TypeError, RuntimeError, ImportError):
        logger.warning("Audit log write failed for %s", action, exc_info=True)


def looks_like_agent_token(value: str | None) -> bool:
    """True when ``value`` has the agent token prefix (it may still be invalid)."""
    return isinstance(value, str) and value.startswith(TOKEN_PREFIX)


def is_agent_principal(user_id: str | None) -> bool:
    """True when ``user_id`` is an outside agent's principal id (``agent:<id>``)."""
    return isinstance(user_id, str) and user_id.startswith(PRINCIPAL_PREFIX)


def has_agent_scope(scopes: Iterable[str] | None) -> bool:
    """True when ``scopes`` carry the outside-agent marker."""
    return any(isinstance(s, str) and s.startswith(AGENT_SCOPE_PREFIX) for s in scopes or ())


def token_id_of(user_id: str | None) -> str | None:
    """The token id inside an agent principal id, or None."""
    if not is_agent_principal(user_id):
        return None
    token_id = user_id[len(PRINCIPAL_PREFIX) :]
    return token_id if _valid_id(token_id) else None


def _valid_id(token_id: str) -> bool:
    return len(token_id) == _ID_HEX_CHARS and all(c in "0123456789abcdef" for c in token_id)


def _split(token: str) -> tuple[str, str] | None:
    """``(id, secret)`` from ``rzag_<id>_<secret>``, or None when malformed."""
    if not looks_like_agent_token(token):
        return None
    rest = token[len(TOKEN_PREFIX) :]
    token_id, sep, secret = rest[:_ID_HEX_CHARS], rest[_ID_HEX_CHARS : _ID_HEX_CHARS + 1], rest[_ID_HEX_CHARS + 1 :]
    if sep != "_" or not _valid_id(token_id) or len(secret) < 32:
        return None
    return token_id, secret


# ---------------------------------------------------------------------------
# Create / list / revoke
# ---------------------------------------------------------------------------


def _clean_ventures(ventures: Iterable[str] | None) -> tuple[str, ...]:
    if ventures is None or isinstance(ventures, str):
        raise AgentTokenError("Name at least one venture as a list of venture keys")
    cleaned: list[str] = []
    for venture in ventures:
        if not isinstance(venture, str) or not _VENTURE_RE.fullmatch(venture.strip()):
            raise AgentTokenError(f"Invalid venture key: {venture!r}")
        key = venture.strip()
        if key not in cleaned:
            cleaned.append(key)
    if not cleaned:
        raise AgentTokenError("An agent token must name at least one venture")
    if len(cleaned) > MAX_VENTURES:
        raise AgentTokenError(f"At most {MAX_VENTURES} ventures per token")
    return tuple(cleaned)


def create_token(
    *,
    name: str,
    user_email: str,
    ventures: Iterable[str],
    expires_in_days: int | None = None,
    created_by: str = "",
    known_ventures: Iterable[str] | None = None,
    channel: str = "api",
) -> tuple[AgentToken, str]:
    """Issue a token. Returns the stored token and the secret (shown once, never stored).

    Args:
        name: A label for people (``claude-desktop-acme``).
        user_email: The ``users.yaml`` user the agent acts for; their role applies.
        ventures: Ventures the agent may see; each must be one the user may see.
        expires_in_days: Optional lifetime (1..3650 days). None = no expiry.
        created_by: Who issued it (stored and audit-logged).
        known_ventures: Configured venture keys; when given, every venture must be one.
        channel: Where the request came from (``api`` or ``cli``), for the audit log.

    Raises:
        AgentTokenError: The request is invalid.
    """
    from realize_core.security.users import get_user

    name = (name or "").strip()
    if not _NAME_RE.fullmatch(name):
        raise AgentTokenError("Name must be 1-64 letters, digits, spaces, dots, dashes or underscores")
    user = get_user(user_email or "")
    if user is None:
        raise AgentTokenError(f"No user '{user_email}' in users.yaml; an agent token acts for a configured user")
    cleaned = _clean_ventures(ventures)
    if known_ventures is not None:
        known = set(known_ventures)
        unknown = [v for v in cleaned if v not in known]
        if unknown:
            raise AgentTokenError(f"Unknown venture: {unknown[0]}")
    if user.ventures:
        outside = [v for v in cleaned if v not in user.ventures]
        if outside:
            raise AgentTokenError(f"User '{user.email}' can't see venture '{outside[0]}', so their agent can't either")
    expires_at = None
    if expires_in_days is not None:
        if isinstance(expires_in_days, bool) or not isinstance(expires_in_days, int):
            raise AgentTokenError("expires_in_days must be a whole number of days")
        if not 1 <= expires_in_days <= MAX_EXPIRY_DAYS:
            raise AgentTokenError(f"expires_in_days must be between 1 and {MAX_EXPIRY_DAYS}")
        expires_at = _stamp(_now() + timedelta(days=expires_in_days))

    token_id = secrets.token_hex(_ID_HEX_CHARS // 2)
    secret = f"{TOKEN_PREFIX}{token_id}_{secrets.token_urlsafe(32)}"
    created_at = _stamp(_now())
    conn = _conn()
    try:
        conn.execute(
            """INSERT INTO agent_tokens (id, name, token_hash, user_email, ventures, created_by, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (token_id, name, _hash(secret), user.email, json.dumps(list(cleaned)), created_by, created_at, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

    token = AgentToken(
        id=token_id,
        name=name,
        user_email=user.email,
        ventures=cleaned,
        created_by=created_by,
        created_at=created_at,
        expires_at=expires_at,
        last_used_at=None,
        revoked_at=None,
        revoked_by=None,
    )
    _audit(
        "agent_token.create",
        created_by or "unknown",
        channel=channel,
        resource_id=token_id,
        metadata={"name": name, "user": user.email, "ventures": list(cleaned), "expires_at": expires_at},
    )
    logger.info("Agent token %s (%s) created for %s, ventures=%s", token_id, name, user.email, ",".join(cleaned))
    return token, secret


def list_tokens() -> list[AgentToken]:
    """Every token, newest first (secrets are never stored, so never listed)."""
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM agent_tokens ORDER BY created_at DESC, id").fetchall()
    finally:
        conn.close()
    return [_row_to_token(r) for r in rows]


def get_token(token_id: str) -> AgentToken | None:
    """One token by id, or None."""
    if not isinstance(token_id, str) or not _valid_id(token_id):
        return None
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM agent_tokens WHERE id = ?", (token_id,)).fetchone()
    finally:
        conn.close()
    return _row_to_token(row) if row else None


def revoke_token(token_id: str, *, revoked_by: str = "", channel: str = "api") -> tuple[AgentToken, int] | None:
    """Revoke a token at once and withdraw the writes it has waiting for approval.

    Returns ``(token, withdrawn)`` — ``withdrawn`` is how many of the agent's
    pending held MCP writes were rejected — or None for an unknown id.
    Revoking twice is harmless.
    """
    token = get_token(token_id)
    if token is None:
        return None
    if token.revoked_at:
        return token, 0
    stamp = _stamp(_now())
    conn = _conn()
    try:
        conn.execute(
            "UPDATE agent_tokens SET revoked_at = ?, revoked_by = ? WHERE id = ? AND revoked_at IS NULL",
            (stamp, revoked_by, token_id),
        )
        conn.commit()
    finally:
        conn.close()
    withdrawn = _withdraw_pending_writes(token.principal_id, revoked_by)
    _audit(
        "agent_token.revoke",
        revoked_by or "unknown",
        channel=channel,
        resource_id=token_id,
        metadata={"name": token.name, "withdrawn_approvals": withdrawn},
    )
    logger.info("Agent token %s (%s) revoked; %d held write(s) withdrawn", token_id, token.name, withdrawn)
    return get_token(token_id) or token, withdrawn


def _withdraw_pending_writes(principal_id: str, revoked_by: str) -> int:
    """Reject the agent's pending held MCP writes (they have no paused skill or mission behind them)."""
    from realize_core.governance.gates import MCP_WRITE_ACTION_TYPE

    now = _now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")  # approval_queue's timestamp format
    conn = _conn()
    try:
        cur = conn.execute(
            """UPDATE approval_queue
               SET status = 'rejected', decision_note = ?, decided_at = ?, updated_at = ?,
                   decided_by = ?, decision_channel = 'agent_token_revoked'
               WHERE requested_by = ? AND action_type = ? AND status = 'pending'""",
            (
                "Withdrawn: the agent's token was revoked",
                now,
                now,
                revoked_by or "system",
                principal_id,
                MCP_WRITE_ACTION_TYPE,
            ),
        )
        conn.commit()
        return cur.rowcount
    except sqlite3.OperationalError as exc:  # no approval_queue table yet
        logger.warning("Could not withdraw held writes for %s: %s", principal_id, exc)
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Resolve (auth middleware) and re-check (held-write execution)
# ---------------------------------------------------------------------------


def _principal(token: AgentToken) -> tuple[AgentPrincipal | None, str]:
    """The live principal for a stored token, or ``(None, reason)``."""
    from realize_core.security.users import get_user

    if token.revoked_at:
        return None, "revoked"
    if _expired(token.expires_at):
        return None, "expired"
    user = get_user(token.user_email)
    if user is None:
        return None, "user_removed"
    ventures = frozenset(token.ventures)
    if user.ventures:
        ventures &= frozenset(user.ventures)
    if not ventures:
        return None, "no_ventures"
    return AgentPrincipal(token.id, token.name, user.email, user.role, ventures), "ok"


def resolve_token(token: str, *, ip_address: str = "") -> AgentPrincipal | None:
    """The principal a presented agent token stands for, or None (audit-logged).

    The secret is compared as a SHA-256 hash with :func:`hmac.compare_digest`.
    ``users.yaml`` is read again on every call: a role change applies at once,
    and a removed user's tokens stop working.
    """
    parts = _split(token)
    if parts is None:
        _audit(
            "agent_token.denied",
            "unknown",
            outcome="denied",
            severity="warning",
            ip_address=ip_address,
            channel="auth",
            metadata={"reason": "malformed"},
        )
        return None
    token_id, _secret = parts
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM agent_tokens WHERE id = ?", (token_id,)).fetchone()
    finally:
        conn.close()
    presented = _hash(token)
    stored = row["token_hash"] if row else _hash(TOKEN_PREFIX)  # same work for unknown ids
    if row is None or not hmac.compare_digest(presented, stored):
        _audit(
            "agent_token.denied",
            f"{PRINCIPAL_PREFIX}{token_id}",
            outcome="denied",
            severity="warning",
            ip_address=ip_address,
            channel="auth",
            resource_id=token_id,
            metadata={"reason": "unknown" if row is None else "bad_secret"},
        )
        return None
    record = _row_to_token(row)
    principal, reason = _principal(record)
    if principal is None:
        _audit(
            "agent_token.denied",
            record.principal_id,
            outcome="denied",
            severity="warning",
            ip_address=ip_address,
            channel="auth",
            resource_id=token_id,
            metadata={"reason": reason},
        )
        return None
    _touch(record)
    return principal


def principal_for(token_id: str | None) -> AgentPrincipal | None:
    """The live principal for a token id (no secret involved), or None.

    Used when a held write is about to run: a token revoked or expired in the
    meantime, or whose user lost the venture, must not act.
    """
    token = get_token(token_id or "")
    if token is None:
        return None
    principal, _reason = _principal(token)
    return principal


def _touch(token: AgentToken) -> None:
    """Record use (at most once per :data:`LAST_USED_RESOLUTION`)."""
    last = _parse(token.last_used_at)
    now = _now()
    if last is not None and now - last < LAST_USED_RESOLUTION:
        return
    conn = _conn()
    try:
        conn.execute("UPDATE agent_tokens SET last_used_at = ? WHERE id = ?", (_stamp(now), token.id))
        conn.commit()
    except sqlite3.OperationalError as exc:  # a busy DB must not fail the request
        logger.debug("last_used_at update skipped for %s: %s", token.id, exc)
    finally:
        conn.close()
