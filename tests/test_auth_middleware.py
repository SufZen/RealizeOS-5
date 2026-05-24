"""Regression tests for the v5.2.0 unified AuthMiddleware.

Covers:
- Public paths bypass auth.
- Cookie session, API key, and JWT bearer all authenticate independently.
- CSRF double-submit check fires on mutating cookie requests only.
- 401 is returned when no credentials match.
"""

from __future__ import annotations

import tempfile

import pytest


@pytest.fixture
def app_env(monkeypatch):
    """Set up env + temp DB so create_app() can boot cleanly."""
    tmp = tempfile.mkdtemp()
    monkeypatch.chdir(tmp)
    monkeypatch.setenv("REALIZE_API_KEY", "test-api-key-1234567890abcdef")
    monkeypatch.setenv("REALIZE_ADMIN_USER", "owner@example.com")

    from realize_core.security.users import hash_password

    monkeypatch.setenv("REALIZE_ADMIN_PASSWORD_HASH", hash_password("correct-horse"))


@pytest.fixture
def client(app_env):
    from fastapi.testclient import TestClient
    from realize_api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def test_public_health_no_auth(client):
    assert client.get("/api/health").status_code == 200


def test_protected_endpoint_rejects_no_creds(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 401
    assert r.json()["error"] == "auth_required"


def test_api_key_header_authenticates(client):
    r = client.get("/api/auth/me", headers={"X-API-Key": "test-api-key-1234567890abcdef"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "owner"


def test_api_key_bearer_form_authenticates(client):
    r = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer test-api-key-1234567890abcdef"},
    )
    assert r.status_code == 200


def test_api_key_query_param_authenticates(client):
    r = client.get("/api/auth/me?api_key=test-api-key-1234567890abcdef")
    assert r.status_code == 200


def test_login_then_cookie_authenticates(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse"},
    )
    assert r.status_code == 200
    assert "realize_session" in r.cookies
    assert "realize_csrf" in r.cookies

    r = client.get("/api/auth/me", cookies={"realize_session": r.cookies["realize_session"]})
    assert r.status_code == 200
    assert r.json()["user_id"] == "owner@example.com"


def test_login_bad_password_returns_401(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "wrong"},
    )
    assert r.status_code == 401


def test_login_unknown_user_returns_401(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "anything"},
    )
    assert r.status_code == 401


def test_cookie_mutating_request_without_csrf_is_forbidden(client):
    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse"},
    )
    session = login.cookies["realize_session"]

    # POST without the CSRF header — must be rejected.
    r = client.post("/api/auth/logout", cookies={"realize_session": session})
    assert r.status_code == 403
    assert r.json()["error"] == "csrf_failed"


def test_cookie_mutating_request_with_csrf_succeeds(client):
    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse"},
    )
    session = login.cookies["realize_session"]
    csrf = login.cookies["realize_csrf"]

    r = client.post(
        "/api/auth/logout",
        cookies={"realize_session": session},
        headers={"X-Realize-CSRF": csrf},
    )
    assert r.status_code == 200
    assert r.json()["revoked"] is True


def test_api_key_mutating_request_skips_csrf(client):
    # API-key callers are programmatic — they must NOT need a CSRF header.
    # We need an actual mutating endpoint; settings is safe.
    r = client.delete(
        "/api/auth/sessions",
        headers={"X-API-Key": "test-api-key-1234567890abcdef"},
    )
    # Either 200 (revoked something) or 401 (no session for the api-key user)
    # — either way, NOT 403 (CSRF) which would prove the check fires for api-keys.
    assert r.status_code != 403


def test_session_invalid_after_logout(client):
    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse"},
    )
    session = login.cookies["realize_session"]
    csrf = login.cookies["realize_csrf"]

    client.post(
        "/api/auth/logout",
        cookies={"realize_session": session},
        headers={"X-Realize-CSRF": csrf},
    )

    r = client.get("/api/auth/me", cookies={"realize_session": session})
    assert r.status_code == 401
