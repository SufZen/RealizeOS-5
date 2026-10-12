"""Issue #21 — Streamable HTTP on /mcp + OAuth 2.1 for Claude.ai custom connectors.

Walks the flow a connector runs: 401 with a discovery hint, protected-resource
and authorization-server metadata, dynamic registration, authorize with PKCE,
sign-in on /oauth/login, code exchange, MCP calls over Streamable HTTP as the
signed-in user, refresh rotation, revocation and user removal.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import textwrap
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

PUBLIC_URL = "http://localhost:8080"
REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"
API_KEY = "test-api-key-1234567890abcdef"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _users_yaml(password_hash: str, *, include_dana: bool = True) -> str:
    dana = f"""
      - email: dana@acme.io
        role: operator
        ventures: [acme]
        password_hash: "{password_hash}"
    """
    return textwrap.dedent(
        f"""
        users:
          - email: owner@realization.co.il
            role: owner
            password_hash: "{password_hash}"
        """
    ) + (textwrap.indent(textwrap.dedent(dana), "  ") if include_dana else "")


@pytest.fixture(scope="module")
def password_hash() -> str:
    from realize_core.security.users import hash_password

    return hash_password("correct-horse")


@pytest.fixture
def oauth_env(tmp_path, monkeypatch, password_hash):
    from realize_api.routes import mcp_oauth
    from realize_core.db.schema import set_db_path
    from realize_core.mcp_server import registry as registry_mod

    monkeypatch.chdir(tmp_path)
    (tmp_path / "users.yaml").write_text(_users_yaml(password_hash), encoding="utf-8")
    monkeypatch.setenv("REALIZE_API_KEY", API_KEY)
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_PUBLIC_URL", PUBLIC_URL)
    set_db_path(tmp_path / "realize_data.db")
    registry_mod.reset_for_tests()
    mcp_oauth._failures.clear()
    yield tmp_path
    mcp_oauth._failures.clear()
    registry_mod.reset_for_tests()
    set_db_path(None)


@pytest.fixture
def client(oauth_env):
    from realize_api.main import create_app

    with TestClient(create_app(), base_url=PUBLIC_URL) as c:
        yield c


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def _register(client: TestClient) -> str:
    r = client.post(
        "/register",
        json={
            "redirect_uris": [REDIRECT_URI],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "client_name": "Claude",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def _start_authorize(client: TestClient, client_id: str, challenge: str) -> str:
    """Run /authorize; returns the sign-in page's request id."""
    r = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "st-123",
            "resource": f"{PUBLIC_URL}/mcp",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    location = urlparse(r.headers["location"])
    assert location.path == "/oauth/login"
    return parse_qs(location.query)["request"][0]


def _sign_in(client: TestClient, request_id: str, email: str, password: str = "correct-horse", action: str = "allow"):
    return client.post(
        "/oauth/login",
        data={"request": request_id, "email": email, "password": password, "action": action},
        follow_redirects=False,
    )


def _connect(client: TestClient, email: str = "dana@acme.io") -> tuple[str, dict]:
    """The whole connector flow; returns (client_id, token response)."""
    client_id = _register(client)
    verifier, challenge = _pkce()
    request_id = _start_authorize(client, client_id, challenge)
    r = _sign_in(client, request_id, email)
    assert r.status_code == 302, r.text
    query = parse_qs(urlparse(r.headers["location"]).query)
    assert query["state"] == ["st-123"]
    r = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": query["code"][0],
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    assert r.status_code == 200, r.text
    return client_id, r.json()


def _rpc(client: TestClient, method: str, params: dict | None = None, *, token: str | None = None):
    headers = dict(MCP_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/mcp", headers=headers, content=json.dumps(body))


def _tool_text(response) -> dict:
    assert response.status_code == 200, response.text
    return json.loads(response.json()["result"]["content"][0]["text"])


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_unauthenticated_mcp_points_at_resource_metadata(self, client):
        r = _rpc(client, "tools/list")
        assert r.status_code == 401
        assert (
            r.headers["www-authenticate"]
            == f'Bearer resource_metadata="{PUBLIC_URL}/.well-known/oauth-protected-resource/mcp"'
        )

    def test_protected_resource_metadata(self, client):
        r = client.get("/.well-known/oauth-protected-resource/mcp")
        assert r.status_code == 200
        body = r.json()
        assert body["resource"] == f"{PUBLIC_URL}/mcp"
        assert body["authorization_servers"] == [f"{PUBLIC_URL}/"]

    def test_authorization_server_metadata(self, client):
        body = client.get("/.well-known/oauth-authorization-server").json()
        assert body["authorization_endpoint"] == f"{PUBLIC_URL}/authorize"
        assert body["token_endpoint"] == f"{PUBLIC_URL}/token"
        assert body["registration_endpoint"] == f"{PUBLIC_URL}/register"
        assert body["code_challenge_methods_supported"] == ["S256"]


# ---------------------------------------------------------------------------
# Authorize + sign-in
# ---------------------------------------------------------------------------


class TestSignIn:
    def test_login_page_names_client_and_redirect_host(self, client):
        request_id = _start_authorize(client, _register(client), _pkce()[1])
        r = client.get("/oauth/login", params={"request": request_id})
        assert r.status_code == 200
        assert "Claude" in r.text
        assert "claude.ai" in r.text
        assert r.headers["x-frame-options"] == "DENY"

    def test_wrong_password_stays_on_page(self, client):
        request_id = _start_authorize(client, _register(client), _pkce()[1])
        r = _sign_in(client, request_id, "dana@acme.io", password="nope")
        assert r.status_code == 401
        assert "wrong" in r.text

    def test_deny_redirects_with_access_denied(self, client):
        request_id = _start_authorize(client, _register(client), _pkce()[1])
        r = _sign_in(client, request_id, "", password="", action="deny")
        assert r.status_code == 302
        query = parse_qs(urlparse(r.headers["location"]).query)
        assert query["error"] == ["access_denied"]
        assert query["state"] == ["st-123"]
        # The request is gone once answered.
        assert client.get("/oauth/login", params={"request": request_id}).status_code == 400

    def test_unknown_request_is_expired(self, client):
        assert client.get("/oauth/login", params={"request": "nope"}).status_code == 400

    def test_repeated_failures_lock_the_ip(self, client):
        from realize_api.routes.mcp_oauth import MAX_FAILED_SIGNINS

        request_id = _start_authorize(client, _register(client), _pkce()[1])
        for _ in range(MAX_FAILED_SIGNINS):
            assert _sign_in(client, request_id, "dana@acme.io", password="nope").status_code == 401
        assert _sign_in(client, request_id, "dana@acme.io").status_code == 429


# ---------------------------------------------------------------------------
# Tokens + MCP over Streamable HTTP
# ---------------------------------------------------------------------------


class TestTokens:
    def test_token_calls_mcp_as_the_signed_in_user(self, client):
        _, tokens = _connect(client)
        assert tokens["access_token"].startswith("rzat_")

        r = _rpc(client, "tools/list", token=tokens["access_token"])
        assert r.status_code == 200, r.text
        names = {t["name"] for t in r.json()["result"]["tools"]}
        assert "realize_health" in names

        # dana is limited to venture "acme": the venture guard applies.
        call = {"name": "get_system", "arguments": {"system_key": "globex"}}
        refused = _tool_text(_rpc(client, "tools/call", call, token=tokens["access_token"]))
        assert refused["code"] == "MCP_FORBIDDEN"
        assert "venture 'globex'" in refused["error"]

    def test_owner_token_is_not_venture_limited(self, client):
        _, tokens = _connect(client, email="owner@realization.co.il")
        call = {"name": "get_system", "arguments": {"system_key": "globex"}}
        result = _tool_text(_rpc(client, "tools/call", call, token=tokens["access_token"]))
        assert result.get("code") != "MCP_FORBIDDEN"

    def test_code_is_single_use(self, client):
        client_id = _register(client)
        verifier, challenge = _pkce()
        r = _sign_in(client, _start_authorize(client, client_id, challenge), "dana@acme.io")
        code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        }
        assert client.post("/token", data=data).status_code == 200
        assert client.post("/token", data=data).status_code == 400

    def test_wrong_pkce_verifier_is_refused(self, client):
        client_id = _register(client)
        _, challenge = _pkce()
        r = _sign_in(client, _start_authorize(client, client_id, challenge), "dana@acme.io")
        code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
        r = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": client_id,
                "code_verifier": _pkce()[0],
            },
        )
        assert r.status_code == 400

    def test_refresh_rotates_tokens(self, client):
        client_id, tokens = _connect(client)
        data = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": client_id}
        r = client.post("/token", data=data)
        assert r.status_code == 200, r.text
        fresh = r.json()
        assert fresh["access_token"] != tokens["access_token"]
        # The old pair is gone; the new access token works.
        assert client.post("/token", data=data).status_code == 400
        assert _rpc(client, "tools/list", token=tokens["access_token"]).status_code == 401
        assert _rpc(client, "tools/list", token=fresh["access_token"]).status_code == 200

    def test_revoke_ends_the_grant(self, client):
        client_id, tokens = _connect(client)
        # The SDK wants the client_secret field even for public clients.
        r = client.post("/revoke", data={"token": tokens["access_token"], "client_id": client_id, "client_secret": ""})
        assert r.status_code == 200
        assert _rpc(client, "tools/list", token=tokens["access_token"]).status_code == 401

    def test_removed_user_loses_access(self, client, oauth_env, password_hash):
        _, tokens = _connect(client)
        (oauth_env / "users.yaml").write_text(_users_yaml(password_hash, include_dana=False), encoding="utf-8")
        assert _rpc(client, "tools/list", token=tokens["access_token"]).status_code == 401

    def test_unknown_token_is_refused(self, client):
        assert _rpc(client, "tools/list", token="rzat_not-a-real-token").status_code == 401


# ---------------------------------------------------------------------------
# Transport + config
# ---------------------------------------------------------------------------


class TestStreamableHTTP:
    def test_api_key_still_works_on_both_transports(self, client):
        r = _rpc(client, "tools/list", token=API_KEY)
        assert r.status_code == 200, r.text
        assert client.get("/mcp/health", headers={"X-API-Key": API_KEY}).json()["ok"] is True

    def test_initialize_handshake(self, client):
        r = _rpc(
            client,
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
            token=API_KEY,
        )
        assert r.status_code == 200, r.text
        assert r.json()["result"]["serverInfo"]["name"] == "realize-os"


class TestConfig:
    def test_defaults(self):
        from realize_core.mcp_server.config import mcp_config_from_env

        cfg = mcp_config_from_env({"mcp": {"enabled": True}})
        assert cfg.streamable_http is True
        assert cfg.oauth_enabled is False

    def test_yaml_block(self, monkeypatch):
        from realize_core.mcp_server.config import mcp_config_from_env

        for name in ("MCP_OAUTH_ENABLED", "MCP_PUBLIC_URL", "MCP_STREAMABLE_HTTP"):
            monkeypatch.delenv(name, raising=False)
        cfg = mcp_config_from_env(
            {"mcp": {"public_url": "https://os.example.com/", "streamable_http": False, "oauth": {"enabled": True}}}
        )
        assert cfg.oauth_enabled is True
        assert cfg.streamable_http is False
        assert cfg.resource_url == "https://os.example.com/mcp"

    def test_oauth_needs_public_url(self, oauth_env, monkeypatch):
        from realize_api.main import create_app

        monkeypatch.delenv("MCP_PUBLIC_URL")
        app = create_app()
        assert app.state.mcp_oauth is None
        with TestClient(app) as c:
            assert "www-authenticate" not in _rpc(c, "tools/list").headers

    def test_oauth_refused_for_plain_http_public_host(self, oauth_env, monkeypatch):
        from realize_api.main import create_app

        monkeypatch.setenv("MCP_PUBLIC_URL", "http://os.example.com")
        assert create_app().state.mcp_oauth is None
