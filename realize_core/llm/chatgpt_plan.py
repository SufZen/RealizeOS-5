"""
Sign-in and tokens for using the owner's ChatGPT plan (OpenAI "token sharing").

OpenAI lets an open-source or self-hosted app send Responses API requests that
draw on the user's ChatGPT plan instead of an API key. The app registers itself
through the user's browser sign-in, then keeps an access token (1 hour) and a
refresh token (30 days, replaced on every refresh).

This module holds what is not about inference:

- the credential file (``DATA_PATH/chatgpt_plan.json``, owner-only, written
  atomically, never logged);
- the host ID (``DATA_PATH/chatgpt_plan_host_id``), one per machine;
- the browser sign-in (PKCE, loopback redirect on 127.0.0.1), used by
  ``scripts/chatgpt_signin.py``;
- refresh, serialized across processes with a lock file, because the API and
  every bot share ``DATA_PATH`` and a refresh token is single use.

The protocol follows OpenAI's token-sharing docs as read on 2026-11-24
(developers.openai.com/siwc/token-sharing-open-source). It is a preview.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import secrets
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
FIRST_CLIENT_ID = "dynamic_agent_client"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
CALLBACK_PATH = "/auth/callback"
DEFAULT_PORT = 1455
AGENT_NAME = "RealizeOS"

CREDENTIALS_FILE = "chatgpt_plan.json"
HOST_ID_FILE = "chatgpt_plan_host_id"
LOCK_FILE = "chatgpt_plan.lock"

REFRESH_MARGIN_SECONDS = 120
# Refresh errors after which only a new browser sign-in helps.
REAUTH_ERRORS = frozenset(
    {
        "invalid_grant",
        "invalid_refresh_token",
        "token_expired",
        "refresh_token_expired",
        "refresh_token_invalidated",
        "refresh_token_reused",
    }
)

_thread_lock = threading.Lock()


class ReauthRequiredError(RuntimeError):
    """The saved sign-in no longer works; the owner has to sign in again."""


@dataclass
class Credentials:
    client_id: str
    ext_agent_host_id: str
    access_token: str
    refresh_token: str
    id_token: str = ""
    token_type: str = "Bearer"
    expires_in: int = 3600
    scope: str = ""
    saved_at: float = 0.0
    email: str = ""
    subject: str = ""
    needs_reauth: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def expires_at(self) -> float:
        return self.saved_at + float(self.expires_in or 0)

    def access_valid(self, now: float | None = None) -> bool:
        return (time.time() if now is None else now) < self.expires_at - REFRESH_MARGIN_SECONDS

    def has_plan_scope(self) -> bool:
        return PLAN_SCOPE in (self.scope or "").split()

    @classmethod
    def from_dict(cls, data: dict) -> Credentials:
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        return cls(
            **{k: v for k, v in data.items() if k in known}, extra={k: v for k, v in data.items() if k not in known}
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        extra = data.pop("extra") or {}
        return {**extra, **data}


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def data_dir() -> Path:
    from realize_core.config import DATA_PATH

    return Path(DATA_PATH)


def credentials_path(base: Path | None = None) -> Path:
    return (base or data_dir()) / CREDENTIALS_FILE


def write_private(path: Path, text: str) -> None:
    """Write ``text`` atomically with owner-only permissions (0600 where supported)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with contextlib.suppress(OSError):
            os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def load_credentials(path: Path | None = None) -> Credentials | None:
    """The saved sign-in, or None when there is none (or it cannot be read)."""
    path = path or credentials_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        logger.error(f"ChatGPT plan credentials unreadable at {path.name}: {type(e).__name__}")
        return None
    try:
        return Credentials.from_dict(data)
    except TypeError as e:
        logger.error(f"ChatGPT plan credentials incomplete in {path.name}: {e}")
        return None


def save_credentials(creds: Credentials, path: Path | None = None) -> None:
    write_private(path or credentials_path(), json.dumps(creds.to_dict(), indent=2))


def new_host_id() -> str:
    """An opaque host ID (UUIDv4 URN, one of the formats OpenAI accepts)."""
    return f"urn:uuid:{uuid.uuid4()}"


def host_id(base: Path | None = None, create: bool = True) -> str | None:
    """This machine's host ID, created and saved on first use when ``create``."""
    path = (base or data_dir()) / HOST_ID_FILE
    try:
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    except FileNotFoundError:
        pass
    if not create:
        return None
    value = new_host_id()
    write_private(path, value + "\n")
    return value


@contextlib.contextmanager
def refresh_lock(base: Path | None = None):
    """Hold an exclusive lock for a refresh, across threads and processes."""
    path = (base or data_dir()) / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with _thread_lock, open(path, "a+") as fh:
        try:
            import fcntl
        except ImportError:  # Windows: one process in practice (dev); the thread lock is enough
            yield
            return
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Browser sign-in (PKCE)
# ---------------------------------------------------------------------------


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def pkce_pair() -> tuple[str, str]:
    """(code_verifier, S256 code_challenge)."""
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def redirect_uri(port: int = DEFAULT_PORT) -> str:
    return f"http://127.0.0.1:{port}{CALLBACK_PATH}"


@dataclass
class AuthRequest:
    url: str
    state: str
    nonce: str
    verifier: str
    redirect_uri: str
    first_registration: bool


def build_authorize_request(
    ext_agent_host_id: str, port: int = DEFAULT_PORT, client_id: str | None = None, login_hint: str | None = None
) -> AuthRequest:
    """The authorize URL and the secrets to keep until the callback.

    ``client_id`` is the issued ID from an earlier sign-in (re-authorization);
    without it this is a first registration with ``dynamic_agent_client``.
    """
    from urllib.parse import urlencode

    verifier, challenge = pkce_pair()
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    uri = redirect_uri(port)
    params = {
        "client_id": client_id or FIRST_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": uri,
        "scope": SCOPES,
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "ext_agent_host_id": ext_agent_host_id,
    }
    if not client_id:
        params["agent_name_hint"] = AGENT_NAME
    if login_hint:
        params["login_hint"] = login_hint
    return AuthRequest(
        url=f"{AUTHORIZE_URL}?{urlencode(params)}",
        state=state,
        nonce=nonce,
        verifier=verifier,
        redirect_uri=uri,
        first_registration=not client_id,
    )


def jwt_claims(token: str) -> dict:
    """The payload of a JWT, NOT signature-checked (used only for display fields and nonce)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return {}


def _token_post(form: dict[str, str], timeout: float = 30.0) -> dict:
    import httpx

    response = httpx.post(TOKEN_URL, data=form, timeout=timeout, headers={"Accept": "application/json"})
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200:
        code = (body.get("error") if isinstance(body, dict) else None) or f"http_{response.status_code}"
        raise TokenError(str(code), response.status_code)
    return body


class TokenError(RuntimeError):
    def __init__(self, code: str, status: int = 0):
        super().__init__(f"token endpoint error: {code} (HTTP {status})")
        self.code = code
        self.status = status


def exchange_code(
    request: AuthRequest, code: str, issued_client_id: str, ext_agent_host_id: str, now: float | None = None
) -> Credentials:
    """Trade the callback code for tokens and check the plan scope was granted."""
    body = _token_post(
        {
            "grant_type": "authorization_code",
            "client_id": issued_client_id,
            "code": code,
            "code_verifier": request.verifier,
            "redirect_uri": request.redirect_uri,
            "resource": RESOURCE,
        }
    )
    claims = jwt_claims(body.get("id_token", ""))
    if claims.get("nonce") not in (None, request.nonce):
        raise TokenError("nonce_mismatch")
    creds = Credentials(
        client_id=issued_client_id,
        ext_agent_host_id=ext_agent_host_id,
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", ""),
        id_token=body.get("id_token", ""),
        token_type=body.get("token_type", "Bearer"),
        expires_in=int(body.get("expires_in") or 3600),
        scope=body.get("scope", ""),
        saved_at=time.time() if now is None else now,
        email=str(claims.get("email", "")),
        subject=str(claims.get("sub", "")),
    )
    if not creds.refresh_token:
        raise TokenError("no_refresh_token")
    if not creds.has_plan_scope():
        raise TokenError("plan_scope_not_granted")
    return creds


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


def refresh(creds: Credentials, now: float | None = None) -> Credentials:
    """One refresh call. The response carries a new refresh token; keep it."""
    body = _token_post(
        {
            "grant_type": "refresh_token",
            "client_id": creds.client_id,
            "refresh_token": creds.refresh_token,
            "resource": RESOURCE,
        }
    )
    creds.access_token = body["access_token"]
    creds.refresh_token = body.get("refresh_token") or creds.refresh_token
    creds.id_token = body.get("id_token") or creds.id_token
    creds.expires_in = int(body.get("expires_in") or 3600)
    creds.scope = body.get("scope") or creds.scope
    creds.saved_at = time.time() if now is None else now
    return creds


def valid_access_token(path: Path | None = None, force: bool = False) -> str:
    """A usable access token, refreshing (under the lock) when it is about to expire.

    Raises:
        ReauthRequiredError: no sign-in, a sign-in marked for re-auth, or a terminal
            refresh error (the file is then marked ``needs_reauth``).
        TokenError: a temporary refresh failure; try again later.
    """
    path = path or credentials_path()
    creds = load_credentials(path)
    if creds is None or creds.needs_reauth:
        raise ReauthRequiredError("no usable ChatGPT plan sign-in")
    if creds.access_valid() and not force:
        return creds.access_token
    with refresh_lock(path.parent):
        creds = load_credentials(path)  # another process may have refreshed meanwhile
        if creds is None or creds.needs_reauth:
            raise ReauthRequiredError("no usable ChatGPT plan sign-in")
        if creds.access_valid() and not force:
            return creds.access_token
        try:
            creds = refresh(creds)
        except TokenError as e:
            if e.code in REAUTH_ERRORS:
                creds.needs_reauth = True
                save_credentials(creds, path)
                logger.error(f"ChatGPT plan sign-in expired ({e.code}); run scripts/chatgpt_signin.py again")
                raise ReauthRequiredError(e.code) from e
            raise
        save_credentials(creds, path)
        return creds.access_token
