"""OAuth 2.1 authorization server for the MCP endpoint (issue #21, STORY-37).

Claude.ai custom connectors (and other remote MCP clients) can't send a
static ``Authorization`` header: they discover the authorization server from
``/.well-known/oauth-protected-resource/mcp``, register themselves (RFC 7591),
send the user through ``/authorize`` with PKCE, and exchange the code at
``/token``. The HTTP handlers come from the official SDK
(:mod:`mcp.server.auth`); this module is the storage-backed provider behind
them.

Every grant is bound to a ``users.yaml`` user, who signs in on
``/oauth/login`` (see :mod:`realize_api.routes.mcp_oauth`). The token itself
carries no role: the auth middleware looks the user up on every request (the
same rule as cookie sessions), so RBAC, venture scope and user removal apply
at once.

Codes and tokens are random strings stored as SHA-256 hashes in SQLite
(migration 009). Refresh tokens rotate on every use.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from realize_core.db.schema import get_connection

logger = logging.getLogger(__name__)

#: Path of the sign-in page that finishes an authorize request.
LOGIN_PATH = "/oauth/login"
#: Prefixes make tokens recognisable in logs and in the auth middleware.
ACCESS_TOKEN_PREFIX = "rzat_"
REFRESH_TOKEN_PREFIX = "rzrt_"

ACCESS_TOKEN_TTL = 60 * 60  # 1 hour
REFRESH_TOKEN_TTL = 30 * 24 * 60 * 60  # 30 days
AUTH_CODE_TTL = 5 * 60
AUTH_REQUEST_TTL = 10 * 60
#: Dynamic registration is open by design; this caps how many rows it can add.
MAX_CLIENTS = 500


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RealizeAuthorizationCode(AuthorizationCode):
    """An authorization code bound to the user who approved it."""

    user_id: str


class RealizeRefreshToken(RefreshToken):
    """A refresh token bound to a user and a grant."""

    user_id: str
    grant_id: str


class RealizeAccessToken(AccessToken):
    """An access token bound to a user and a grant."""

    user_id: str
    grant_id: str


@dataclass(frozen=True)
class PendingAuthorization:
    """An ``/authorize`` request waiting for the user to sign in."""

    request_id: str
    client: OAuthClientInformationFull
    params: AuthorizationParams


class RealizeOAuthProvider:
    """SQLite-backed ``OAuthAuthorizationServerProvider`` for the MCP endpoint."""

    def __init__(self, issuer_url: str):
        self.issuer_url = issuer_url.rstrip("/")

    # ------------------------------------------------------------- clients

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Load a registered client."""
        conn = get_connection()
        try:
            row = conn.execute("SELECT client_info FROM mcp_oauth_clients WHERE client_id = ?", (client_id,)).fetchone()
        finally:
            conn.close()
        return OAuthClientInformationFull.model_validate_json(row["client_info"]) if row else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Store a dynamically registered client."""
        conn = get_connection()
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM mcp_oauth_clients").fetchone()["n"]
            if count >= MAX_CLIENTS:
                logger.warning("MCP OAuth client registration refused: %d clients already registered", count)
                raise RegistrationError("invalid_client_metadata", "Too many registered clients")
            conn.execute(
                "INSERT INTO mcp_oauth_clients (client_id, client_info) VALUES (?, ?)",
                (client_info.client_id, client_info.model_dump_json()),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("MCP OAuth client registered: %s (%s)", client_info.client_id, client_info.client_name or "unnamed")

    # ----------------------------------------------------------- authorize

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Park the request and send the user to the sign-in page."""
        request_id = secrets.token_urlsafe(32)
        conn = get_connection()
        try:
            conn.execute("DELETE FROM mcp_oauth_requests WHERE expires_at < ?", (time.time(),))
            conn.execute(
                "INSERT INTO mcp_oauth_requests (request_id, client_id, params, expires_at) VALUES (?, ?, ?, ?)",
                (request_id, client.client_id, params.model_dump_json(), time.time() + AUTH_REQUEST_TTL),
            )
            conn.commit()
        finally:
            conn.close()
        return construct_redirect_uri(f"{self.issuer_url}{LOGIN_PATH}", request=request_id)

    async def get_pending(self, request_id: str) -> PendingAuthorization | None:
        """The unexpired authorize request ``request_id``, or None."""
        if not request_id:
            return None
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT client_id, params FROM mcp_oauth_requests WHERE request_id = ? AND expires_at >= ?",
                (request_id, time.time()),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        client = await self.get_client(row["client_id"])
        if client is None:
            return None
        return PendingAuthorization(request_id, client, AuthorizationParams.model_validate_json(row["params"]))

    def _take_pending(self, request_id: str) -> bool:
        """Delete a pending request. True if it existed (so it's used once)."""
        conn = get_connection()
        try:
            cur = conn.execute("DELETE FROM mcp_oauth_requests WHERE request_id = ?", (request_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    async def approve(self, pending: PendingAuthorization, user_id: str) -> str | None:
        """Issue a code for ``user_id``; returns the client redirect URL.

        Returns None when the request was already used (double submit).
        """
        if not self._take_pending(pending.request_id):
            return None
        params = pending.params
        code = secrets.token_urlsafe(32)
        auth_code = RealizeAuthorizationCode(
            code=code,
            scopes=params.scopes or (pending.client.scope or "").split(),
            expires_at=time.time() + AUTH_CODE_TTL,
            client_id=pending.client.client_id or "",
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            user_id=user_id,
        )
        conn = get_connection()
        try:
            conn.execute("DELETE FROM mcp_oauth_codes WHERE expires_at < ?", (time.time(),))
            conn.execute(
                "INSERT INTO mcp_oauth_codes (code_hash, client_id, user_id, data, expires_at) VALUES (?, ?, ?, ?, ?)",
                (
                    _hash(code),
                    auth_code.client_id,
                    user_id,
                    auth_code.model_dump_json(exclude={"code"}),
                    auth_code.expires_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    def deny(self, pending: PendingAuthorization) -> str:
        """Drop the request; returns the client redirect URL with ``access_denied``."""
        self._take_pending(pending.request_id)
        return construct_redirect_uri(
            str(pending.params.redirect_uri),
            error="access_denied",
            error_description="The user declined the connection",
            state=pending.params.state,
        )

    # --------------------------------------------------------------- codes

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> RealizeAuthorizationCode | None:
        """Load an unused code issued to ``client``."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT data FROM mcp_oauth_codes WHERE code_hash = ? AND client_id = ?",
                (_hash(authorization_code), client.client_id),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return RealizeAuthorizationCode.model_validate({**json.loads(row["data"]), "code": authorization_code})

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: RealizeAuthorizationCode
    ) -> OAuthToken:
        """Spend the code (once) and issue an access + refresh token pair."""
        conn = get_connection()
        try:
            cur = conn.execute("DELETE FROM mcp_oauth_codes WHERE code_hash = ?", (_hash(authorization_code.code),))
            conn.commit()
        finally:
            conn.close()
        if cur.rowcount == 0:
            raise TokenError("invalid_grant", "authorization code already used")
        _require_user(authorization_code.user_id)
        return self._issue(
            client_id=client.client_id or "",
            user_id=authorization_code.user_id,
            scopes=authorization_code.scopes,
            resource=authorization_code.resource,
            grant_id=uuid.uuid4().hex,
        )

    # -------------------------------------------------------------- tokens

    def _issue(
        self, *, client_id: str, user_id: str, scopes: list[str], resource: str | None, grant_id: str
    ) -> OAuthToken:
        access = ACCESS_TOKEN_PREFIX + secrets.token_urlsafe(32)
        refresh = REFRESH_TOKEN_PREFIX + secrets.token_urlsafe(32)
        now = int(time.time())
        scope_str = " ".join(scopes)
        conn = get_connection()
        try:
            conn.executemany(
                """
                INSERT INTO mcp_oauth_tokens
                    (token_hash, kind, grant_id, client_id, user_id, scopes, resource, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        _hash(access),
                        "access",
                        grant_id,
                        client_id,
                        user_id,
                        scope_str,
                        resource,
                        now + ACCESS_TOKEN_TTL,
                    ),
                    (
                        _hash(refresh),
                        "refresh",
                        grant_id,
                        client_id,
                        user_id,
                        scope_str,
                        resource,
                        now + REFRESH_TOKEN_TTL,
                    ),
                ],
            )
            conn.execute("DELETE FROM mcp_oauth_tokens WHERE expires_at < ?", (now,))
            conn.commit()
        finally:
            conn.close()
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            scope=scope_str or None,
            refresh_token=refresh,
        )

    def _load_token(self, token: str, kind: str):
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM mcp_oauth_tokens WHERE token_hash = ? AND kind = ? AND expires_at >= ?",
                (_hash(token), kind, int(time.time())),
            ).fetchone()
        finally:
            conn.close()
        return row

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RealizeRefreshToken | None:
        """Load a live refresh token issued to ``client``."""
        row = self._load_token(refresh_token, "refresh")
        if row is None or row["client_id"] != client.client_id:
            return None
        return RealizeRefreshToken(
            token=refresh_token,
            client_id=row["client_id"],
            scopes=row["scopes"].split(),
            expires_at=row["expires_at"],
            user_id=row["user_id"],
            grant_id=row["grant_id"],
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RealizeRefreshToken, scopes: list[str]
    ) -> OAuthToken:
        """Rotate: drop the grant's old tokens and issue a new pair."""
        _require_user(refresh_token.user_id)
        row = self._load_token(refresh_token.token, "refresh")
        if row is None:
            raise TokenError("invalid_grant", "refresh token already used")
        self._revoke_grant(refresh_token.grant_id)
        return self._issue(
            client_id=client.client_id or "",
            user_id=refresh_token.user_id,
            scopes=scopes or refresh_token.scopes,
            resource=row["resource"],
            grant_id=refresh_token.grant_id,
        )

    async def load_access_token(self, token: str) -> RealizeAccessToken | None:
        """Load a live access token."""
        row = self._load_token(token, "access")
        if row is None:
            return None
        return RealizeAccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=row["scopes"].split(),
            expires_at=row["expires_at"],
            resource=row["resource"],
            user_id=row["user_id"],
            grant_id=row["grant_id"],
        )

    async def revoke_token(self, token: RealizeAccessToken | RealizeRefreshToken) -> None:
        """Revoke the whole grant (access and refresh) the token belongs to."""
        self._revoke_grant(token.grant_id)

    def _revoke_grant(self, grant_id: str) -> None:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM mcp_oauth_tokens WHERE grant_id = ?", (grant_id,))
            conn.commit()
        finally:
            conn.close()


def _require_user(user_id: str) -> None:
    """Refuse a grant whose user was removed from ``users.yaml``."""
    from realize_core.security.users import get_user

    if get_user(user_id) is None:
        raise TokenError("invalid_grant", "user is no longer configured")


def resolve_access_token(token: str):
    """The :class:`CurrentUser` an MCP access token stands for, or None.

    Re-reads ``users.yaml`` on every call, so a role change applies at once
    and a removed user's tokens stop working.
    """
    if not token.startswith(ACCESS_TOKEN_PREFIX):
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT user_id FROM mcp_oauth_tokens WHERE token_hash = ? AND kind = 'access' AND expires_at >= ?",
            (_hash(token), int(time.time())),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None

    from realize_api.dependencies import CurrentUser

    from realize_core.security.users import get_user

    user = get_user(row["user_id"])
    if user is None:
        logger.warning("MCP OAuth token refused: user %s is no longer configured", row["user_id"])
        return None
    return CurrentUser(user_id=user.email, role=user.role, scopes=[])
