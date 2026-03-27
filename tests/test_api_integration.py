"""
API Layer Integration Tests — validates hardening changes.

Tests cover:
- Health endpoint accessibility
- Error handler consistency (structured JSON responses)
- Response envelope format
- Middleware path bypass behavior
- Pydantic validation on ventures/setup endpoints
- Response helper correctness
"""

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from realize_api.error_handlers import register_error_handlers
from realize_api.middleware import APIKeyMiddleware
from realize_api.response import api_error, api_response
from realize_api.routes import health

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Create a minimal FastAPI app with error handlers and health routes."""
    _app = FastAPI()
    register_error_handlers(_app)
    _app.include_router(health.router, prefix="/api")
    return _app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def app_with_middleware():
    """App with API key middleware to test bypass paths."""
    import os

    os.environ["REALIZE_API_KEY"] = "test-secret-key"
    _app = FastAPI()
    _app.add_middleware(APIKeyMiddleware, api_key="test-secret-key")
    register_error_handlers(_app)
    _app.include_router(health.router, prefix="/api")
    yield _app
    os.environ.pop("REALIZE_API_KEY", None)


@pytest.fixture
def mw_client(app_with_middleware):
    return TestClient(app_with_middleware, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. Health Endpoint Tests
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Verify health endpoint is accessible and returns correct shape."""

    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "realize-os"

    def test_health_bypasses_api_key_middleware(self, mw_client):
        """Health endpoint should be accessible without API key."""
        resp = mw_client.get("/api/health")
        assert resp.status_code == 200

    def test_status_bypasses_api_key_middleware(self, mw_client):
        """Status endpoint should be accessible without API key."""
        resp = mw_client.get("/api/status")
        # 200 or 404 if no full status route configured — but NOT 401
        assert resp.status_code != 401


# ---------------------------------------------------------------------------
# 2. Error Handler Tests
# ---------------------------------------------------------------------------


class TestErrorHandlers:
    """Verify centralized error handlers return structured JSON."""

    def test_unhandled_exception_returns_500(self, app, client):
        @app.get("/api/test-error")
        async def raise_unhandled():
            raise RuntimeError("boom")

        resp = client.get("/api/test-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] == "Internal server error"
        assert body["type"] == "internal_error"
        # Must NOT leak the actual exception message
        assert "boom" not in str(body)

    def test_file_not_found_returns_404(self, app, client):
        @app.get("/api/test-fnf")
        async def raise_fnf():
            raise FileNotFoundError("secret/path/data.db")

        resp = client.get("/api/test-fnf")
        assert resp.status_code == 404
        body = resp.json()
        assert body["type"] == "not_found"
        # Must NOT leak filesystem path
        assert "secret" not in body["error"]

    def test_permission_error_returns_403(self, app, client):
        @app.get("/api/test-perm")
        async def raise_perm():
            raise PermissionError("cannot write to /etc/passwd")

        resp = client.get("/api/test-perm")
        assert resp.status_code == 403
        assert resp.json()["type"] == "permission_denied"

    def test_db_operational_error_returns_503(self, app, client):
        @app.get("/api/test-db")
        async def raise_db():
            raise sqlite3.OperationalError("database is locked")

        resp = client.get("/api/test-db")
        assert resp.status_code == 503
        body = resp.json()
        assert body["type"] == "database_error"
        assert "locked" not in body["error"]

    def test_timeout_error_returns_504(self, app, client):
        @app.get("/api/test-timeout")
        async def raise_timeout():
            raise TimeoutError()

        resp = client.get("/api/test-timeout")
        assert resp.status_code == 504
        assert resp.json()["type"] == "timeout"

    def test_validation_error_returns_422(self, app, client):
        from pydantic import BaseModel

        class Body(BaseModel):
            name: str

        @app.post("/api/test-validate")
        async def needs_body(body: Body):
            return {"ok": True}

        resp = client.post("/api/test-validate", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body["type"] == "validation_error"


# ---------------------------------------------------------------------------
# 3. Response Envelope Helper Tests
# ---------------------------------------------------------------------------


class TestResponseEnvelope:
    """Verify api_response/api_error produce correct shapes."""

    def test_api_response_basic(self):
        result = api_response({"items": [1, 2]})
        assert result["success"] is True
        assert result["data"]["items"] == [1, 2]
        assert "message" not in result

    def test_api_response_with_message(self):
        result = api_response(None, message="Done")
        assert result["success"] is True
        assert result["message"] == "Done"

    def test_api_error_basic(self):
        result = api_error("Not found")
        assert result["success"] is False
        assert result["error"] == "Not found"
        assert "detail" not in result

    def test_api_error_with_detail(self):
        result = api_error("Validation failed", detail={"field": "email"})
        assert result["success"] is False
        assert result["detail"]["field"] == "email"


# ---------------------------------------------------------------------------
# 4. Middleware Bypass Path Tests
# ---------------------------------------------------------------------------


class TestMiddlewareBypass:
    """Verify middleware skips correct public paths."""

    def test_docs_path_bypasses_middleware(self, mw_client):
        resp = mw_client.get("/docs")
        # docs returns HTML
        assert resp.status_code == 200

    def test_openapi_json_bypasses_middleware(self, mw_client):
        resp = mw_client.get("/openapi.json")
        assert resp.status_code == 200

    def test_protected_path_requires_auth(self, mw_client):
        """Non-public paths should return 401 without API key."""
        resp = mw_client.get("/api/ventures")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 5. Security Middleware Path Validation
# ---------------------------------------------------------------------------


class TestSecurityMiddlewarePaths:
    """Verify _PUBLIC_PATHS and _is_public function correctly."""

    def test_public_paths_include_api_health(self):
        from realize_api.security_middleware import _PUBLIC_PATHS

        assert "/api/health" in _PUBLIC_PATHS
        assert "/api/status" in _PUBLIC_PATHS

    def test_public_paths_include_root_health(self):
        from realize_api.security_middleware import _PUBLIC_PATHS

        assert "/health" in _PUBLIC_PATHS
        assert "/status" in _PUBLIC_PATHS

    def test_is_public_matches_assets(self):
        from realize_api.security_middleware import _is_public

        assert _is_public("/assets/style.css") is True
        assert _is_public("/api/ventures") is False
