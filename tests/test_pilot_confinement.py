"""Pilot accounts (STORY-46) are confined on the server, whatever the host's config.

They may only call the pilot tools over MCP; the REST API and dashboard sign-in
refuse them. The confinement comes from ``pilot: true`` in users.yaml, which
``realize-os wedge invite`` writes.
"""

from __future__ import annotations

import asyncio
import textwrap
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

USERS_YAML = textwrap.dedent(
    """
    users:
      - email: owner@example.com
        role: owner
        password_hash: "$2b$12$owner"
      - email: pilot@example.com
        role: viewer
        ventures: [pilot-abc]
        pilot: true
        password_hash: "$2b$12$pilot"
      - email: odd@example.com
        role: viewer
        ventures: [pilot-def]
        pilot: maybe
        password_hash: "$2b$12$odd"
      - email: plain@example.com
        role: viewer
        ventures: [acme]
        pilot: false
        password_hash: "$2b$12$plain"
    """
)


@pytest.fixture
def users_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "users.yaml"
    path.write_text(USERS_YAML, encoding="utf-8")
    return path


def test_pilot_marker_is_read_and_fails_closed(users_file):
    from realize_core.security.users import get_user, is_pilot_user

    assert get_user("pilot@example.com").pilot is True
    assert is_pilot_user("pilot@example.com")
    assert is_pilot_user("odd@example.com")  # an unclear value keeps the account confined
    assert not is_pilot_user("plain@example.com")
    assert not is_pilot_user("owner@example.com")
    assert not is_pilot_user(None)
    assert not is_pilot_user("ghost@example.com")


def test_invite_marks_the_account(users_file, monkeypatch):
    import yaml
    from realize_core.wedge import pilot

    monkeypatch.delenv("MCP_TOOLS", raising=False)
    monkeypatch.setattr(pilot, "hash_password", lambda pw: "hashed")
    config = {"features": {"wedge": True}, "mcp": {"tools": sorted(pilot.PILOT_TOOLS)}}
    pilot.invite("new@example.com", config=config, users_file=users_file)
    entry = yaml.safe_load(users_file.read_text(encoding="utf-8"))["users"][-1]
    assert entry["pilot"] is True


# ---------------------------------------------------------------- REST + dashboard


def _client(user_id: str) -> TestClient:
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = {"acme": {"name": "Acme", "agents": {}}}
    app.state.config = {"features": {}}

    @app.middleware("http")
    async def as_principal(request, call_next):
        request.state.user_id = user_id
        request.state.role = "viewer"
        request.state.scopes = []
        return await call_next(request)

    return TestClient(app)


@pytest.mark.parametrize("path", ["/api/ventures", "/api/approvals", "/api/systems", "/api/agents"])
def test_rest_refuses_pilot_accounts(users_file, path):
    resp = _client("pilot@example.com").get(path)
    assert resp.status_code == 403
    assert "Pilot accounts" in resp.text


def test_rest_still_serves_other_viewers(users_file):
    assert _client("plain@example.com").get("/api/ventures").status_code == 200


def test_dashboard_login_refuses_pilot_accounts(users_file, monkeypatch):
    from realize_api.main import create_app
    from realize_core.security import users

    pilot = users.get_user("pilot@example.com")
    monkeypatch.setattr(users, "verify_password", lambda email, pw: pilot)
    client = TestClient(create_app())
    resp = client.post("/api/auth/login", json={"email": "pilot@example.com", "password": "x"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "pilot_account"
    assert "set-cookie" not in {k.lower() for k in resp.headers}


# ---------------------------------------------------------------- MCP


def _mcp_cfg(**overrides):
    from realize_core.mcp_server.config import McpConfig

    base = {
        "enabled": True,
        "expose_kb": True,
        "expose_ops": True,
        "allow_admin": False,
        "audit_full_payload": False,
        "bearer_token_override": "",
    }
    base.update(overrides)
    return McpConfig(**base)


def _as(email: str):
    from realize_api.dependencies import CurrentUser
    from realize_core.mcp_server.auth import bind_user

    return bind_user(CurrentUser(user_id=email, role="viewer", scopes=[]))


def test_mcp_refuses_non_pilot_tools_even_without_an_allowlist(users_file):
    from realize_core.mcp_server.auth import reset_user
    from realize_core.mcp_server.registry import get_registry
    from realize_core.mcp_server.server import MCPErrorCode, _dispatch

    token = _as("pilot@example.com")
    try:
        out = asyncio.run(_dispatch(get_registry(), _mcp_cfg(), SimpleNamespace(), "list_ventures", {}))
    finally:
        reset_user(token)
    assert MCPErrorCode.FORBIDDEN in out[0].text
    assert "Pilot accounts" in out[0].text


def test_mcp_lists_only_pilot_tools_for_pilot_accounts(users_file):
    import mcp.types as mcp_types
    from realize_core.mcp_server.auth import reset_user
    from realize_core.mcp_server.server import build_mcp_server
    from realize_core.wedge.pilot import PILOT_TOOLS

    server = build_mcp_server(app_state=SimpleNamespace(), mcp_config=_mcp_cfg())
    handler = server.request_handlers[mcp_types.ListToolsRequest]

    def names(email: str) -> set[str]:
        token = _as(email)
        try:
            result = asyncio.run(handler(mcp_types.ListToolsRequest(method="tools/list")))
        finally:
            reset_user(token)
        return {t.name for t in result.root.tools}

    assert names("pilot@example.com") <= set(PILOT_TOOLS)
    assert "tender_register_submit" in names("pilot@example.com")
    assert "list_ventures" in names("plain@example.com")
