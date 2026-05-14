"""
Server-side session store for cookie-based dashboard authentication.

Sessions are stored in the operational SQLite database (``user_sessions`` table,
see migration 006). The cookie value is an opaque 32-byte URL-safe random
string — no claims, no signature. All session data lives server-side, so
revocation is instant (just delete the row).

Two cookies are issued per session:
- ``realize_session``: HttpOnly, SameSite=Strict — the session ID.
- ``realize_csrf``: readable from JS, SameSite=Strict — used by the SPA in a
  double-submit pattern. Mutating requests must echo this value in the
  ``X-Realize-CSRF`` header; the AuthMiddleware compares it to the server-side
  ``csrf_token`` column on the session.

Public API:
    create_session(user_id, role, *, ip_address, user_agent, remember_me) -> SessionRecord
    get_session(session_id) -> SessionRecord | None
    touch_session(session_id) -> None
    revoke_session(session_id) -> bool
    revoke_all_for_user(user_id) -> int
    list_sessions_for_user(user_id) -> list[SessionRecord]
    cleanup_expired() -> int

The store assumes the operational DB schema (migration 006) is in place. Callers
must run ``realize_core.db.migrations.run_migrations()`` before using it.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from realize_core.db.schema import get_connection

logger = logging.getLogger(__name__)

# Default TTLs — overridable by remember_me at session creation time.
DEFAULT_TTL = timedelta(hours=24)
REMEMBER_ME_TTL = timedelta(days=30)

# Cookie metadata — consumed by realize_api/routes/auth.py when setting cookies.
SESSION_COOKIE_NAME = "realize_session"
CSRF_COOKIE_NAME = "realize_csrf"
CSRF_HEADER_NAME = "X-Realize-CSRF"


@dataclass(frozen=True)
class SessionRecord:
    """A single row from the ``user_sessions`` table."""

    session_id: str
    csrf_token: str
    user_id: str
    role: str
    created_at: str
    expires_at: str
    last_seen_at: str
    ip_address: str
    user_agent: str
    remember_me: bool

    @property
    def is_expired(self) -> bool:
        """True when the session's expiry timestamp is in the past (UTC)."""
        expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry < datetime.now(timezone.utc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _row_to_record(row) -> SessionRecord:
    return SessionRecord(
        session_id=row["session_id"],
        csrf_token=row["csrf_token"],
        user_id=row["user_id"],
        role=row["role"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        last_seen_at=row["last_seen_at"],
        ip_address=row["ip_address"] or "",
        user_agent=row["user_agent"] or "",
        remember_me=bool(row["remember_me"]),
    )


def create_session(
    user_id: str,
    role: str,
    *,
    ip_address: str = "",
    user_agent: str = "",
    remember_me: bool = False,
) -> SessionRecord:
    """Create a new session and return its record.

    The returned ``session_id`` is a 32-byte URL-safe random string. Callers
    should set it as the ``realize_session`` HttpOnly cookie. ``csrf_token``
    should be set as the ``realize_csrf`` cookie (NOT HttpOnly) so the SPA
    can echo it in mutating requests.
    """
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    ttl = REMEMBER_ME_TTL if remember_me else DEFAULT_TTL
    expires_at = datetime.now(timezone.utc) + ttl

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO user_sessions
                (session_id, csrf_token, user_id, role, expires_at,
                 ip_address, user_agent, remember_me)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                csrf_token,
                user_id,
                role,
                expires_at.isoformat(timespec="milliseconds"),
                ip_address,
                user_agent,
                1 if remember_me else 0,
            ),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM user_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return _row_to_record(row)
    finally:
        conn.close()


def get_session(session_id: str) -> SessionRecord | None:
    """Look up a session by ID. Returns None if missing or expired."""
    if not session_id:
        return None

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM user_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None

        record = _row_to_record(row)
        if record.is_expired:
            # Lazy cleanup: drop the expired row on first observation.
            conn.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return None
        return record
    finally:
        conn.close()


def touch_session(session_id: str) -> None:
    """Update ``last_seen_at`` for an active session."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE user_sessions SET last_seen_at = ? WHERE session_id = ?",
            (_now_iso(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


def revoke_session(session_id: str) -> bool:
    """Delete a session. Returns True if a row was deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM user_sessions WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def revoke_all_for_user(user_id: str) -> int:
    """Delete every session for the given user. Returns the number deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM user_sessions WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def list_sessions_for_user(user_id: str) -> list[SessionRecord]:
    """Return all active (non-expired) sessions for a user."""
    conn = get_connection()
    try:
        cleanup_expired()  # opportunistic
        rows = conn.execute(
            """
            SELECT * FROM user_sessions
             WHERE user_id = ?
          ORDER BY last_seen_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [_row_to_record(r) for r in rows]
    finally:
        conn.close()


def cleanup_expired() -> int:
    """Delete all expired sessions. Returns the number deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM user_sessions WHERE expires_at < ?",
            (_now_iso(),),
        )
        conn.commit()
        if cursor.rowcount:
            logger.debug("Cleaned up %d expired session(s)", cursor.rowcount)
        return cursor.rowcount
    finally:
        conn.close()
