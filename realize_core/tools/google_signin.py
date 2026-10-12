"""
Sign in to Google once and store the token the Google tools read.

The Google tools (:mod:`realize_core.tools.google_auth`) load
``.credentials/tokens.json`` but nothing in the engine created it. This is the
standard OAuth flow for a desktop client, built on the standard library so it
needs no extra dependency: open Google's consent page in the browser, receive
the code on a one-shot local server (``127.0.0.1``), exchange it with PKCE and
write ``tokens.json`` in the format ``google_auth`` expects.

Usage (from the project root, with ``.credentials/client_secrets.json`` from a
Google Cloud "Desktop app" OAuth client)::

    python scripts/google_signin.py
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from realize_core.tools.google_auth import _CLIENT_SECRETS_PATH, _TOKENS_PATH, SCOPES, _load_client_config

logger = logging.getLogger(__name__)

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


class SignInError(RuntimeError):
    """The sign-in could not finish; the message says why."""


def pkce_pair() -> tuple[str, str]:
    """A PKCE ``(verifier, S256 challenge)`` pair."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_auth_url(client_id: str, redirect_uri: str, state: str, challenge: str, scopes=SCOPES) -> str:
    """Google's consent URL for an offline (refresh-token) grant."""
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URI}?{urllib.parse.urlencode(query)}"


def parse_callback(path: str, expected_state: str) -> str:
    """Return the authorization code from the redirect path.

    Raises:
        SignInError: Google returned an error, the state doesn't match, or no code.
    """
    params = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    if "error" in params:
        raise SignInError(f"Google refused the sign-in: {params['error'][0]}")
    if params.get("state", [""])[0] != expected_state:
        raise SignInError("The sign-in response doesn't match this request (state mismatch)")
    code = params.get("code", [""])[0]
    if not code:
        raise SignInError("Google returned no authorization code")
    return code


def token_file_data(response: dict, now: float | None = None) -> dict:
    """The ``tokens.json`` content for a token-endpoint response.

    Raises:
        SignInError: The response has no refresh token (the tools couldn't renew access).
    """
    if not response.get("refresh_token"):
        raise SignInError("Google returned no refresh token; remove the app's access in the Google account and retry")
    now = time.time() if now is None else now
    return {
        "access_token": response.get("access_token", ""),
        "refresh_token": response["refresh_token"],
        "scope": response.get("scope", ""),
        "token_type": response.get("token_type", "Bearer"),
        "expiry_date": int((now + int(response.get("expires_in", 0))) * 1000),
    }


def write_private(path: Path, text: str) -> None:
    """Write a secret file readable only by its owner (0600, folder 0700 on POSIX)."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)  # also tightens a file that existed with looser permissions


def _exchange(client: dict, code: str, verifier: str, redirect_uri: str) -> dict:
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        }
    ).encode("ascii")
    request = urllib.request.Request(TOKEN_URI, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:  # noqa: S310 - fixed https endpoint
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise SignInError(f"Google rejected the code exchange: {detail}") from None


def _wait_for_redirect(server: http.server.HTTPServer, timeout: float) -> str:
    captured: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            captured["path"] = self.path
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<p>RealizeOS: sign-in received. You can close this tab.</p>")

        def log_message(self, *args):
            return

    server.RequestHandlerClass = Handler
    server.timeout = timeout
    deadline = time.monotonic() + timeout
    while "path" not in captured and time.monotonic() < deadline:
        server.handle_request()
    if "path" not in captured:
        raise SignInError("No sign-in response arrived in time")
    return captured["path"]


def sign_in(tokens_path: Path | None = None, open_browser: bool = True, timeout: float = 300) -> Path:
    """Run the browser sign-in and write ``tokens.json``.

    Args:
        tokens_path: Where to write the token (default ``.credentials/tokens.json``).
        open_browser: Open the consent page automatically; the URL is also logged.
        timeout: Seconds to wait for the browser to come back.

    Returns:
        The token file path.

    Raises:
        SignInError: Missing client secrets, a refused consent, or a failed exchange.
    """
    client = _load_client_config()
    if not client.get("client_id") or not client.get("client_secret"):
        raise SignInError(
            f"No OAuth client found. Download a 'Desktop app' OAuth client JSON from Google Cloud "
            f"and save it as {_CLIENT_SECRETS_PATH}"
        )
    tokens_path = Path(tokens_path or _TOKENS_PATH)

    server = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
    try:
        redirect_uri = f"http://127.0.0.1:{server.server_port}/"
        state = secrets.token_urlsafe(24)
        verifier, challenge = pkce_pair()
        url = build_auth_url(client["client_id"], redirect_uri, state, challenge)
        logger.info("Open this URL to sign in to Google: %s", url)
        if open_browser:
            webbrowser.open(url)
        code = parse_callback(_wait_for_redirect(server, timeout), state)
    finally:
        server.server_close()

    data = token_file_data(_exchange(client, code, verifier, redirect_uri))
    write_private(tokens_path, json.dumps(data, indent=2))
    logger.info("Saved Google token to %s", tokens_path)
    return tokens_path
