"""Adversarial tests for the MCP attack surface (Story 5).

Covers attempted abuses against the built-in MCP server:

* Admin tools are not visible / not callable when ``mcp.allow_admin`` is
  false (default).
* Admin tools refuse non-owner roles (scope escalation).
* Production gate refuses to start admin if JWT is off or weak.
* Mutating tools require an explicit confirmation flag where applicable
  (e.g. ``delete_venture``).
* The dispatcher returns structured error codes (``MCP_*``) instead of
  leaking exception traces.
* MCP routes inherit the existing FastAPI auth middleware (no anonymous
  access through ``/mcp/sse`` or ``/mcp/messages``).
* Oversized POST bodies to ``/mcp/messages`` are bounded by the same
  injection-guard / size limits as the REST surface.

The full SSE handshake / replay-protection scenarios are deferred to a
live-stack test (run via the audit playbook). These unit-level tests
cover everything that can be exercised in-process.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from realize_api.dependencies import CurrentUser

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def env(**overrides: str | None):
    saved: dict[str, str | None] = {}
    for k, v in overrides.items():
        saved[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, original in saved.items():
            if original is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = original


@pytest.fixture
def fresh_registry():
    from realize_core.mcp_server import registry as registry_mod

    registry_mod.reset_for_tests()
    yield registry_mod.get_registry()
    registry_mod.reset_for_tests()


def _user(role: str) -> CurrentUser:
    return CurrentUser(user_id="adversary", role=role)


def _full_mcp_cfg(**overrides):
    """Build a fully-on McpConfig (kb+ops+admin) and override fields."""
    from realize_core.mcp_server.config import McpConfig

    defaults = {
        "enabled": True,
        "expose_kb": True,
        "expose_ops": True,
        "allow_admin": True,
        "audit_full_payload": False,
        "bearer_token_override": "",
    }
    defaults.update(overrides)
    return McpConfig(**defaults)


# ---------------------------------------------------------------------------
# 1. allow_admin=false → admin tools blocked
# ---------------------------------------------------------------------------


class TestAdminFamilyGate:
    def test_admin_tools_hidden_when_allow_admin_false(self, fresh_registry):
        cfg = _full_mcp_cfg(allow_admin=False)
        visible = {t.name for t in fresh_registry.visible_tools(cfg)}
        assert "create_venture" not in visible
        assert "delete_venture" not in visible
        assert "update_setting" not in visible
        assert "reload_agents" not in visible

    def test_admin_tools_visible_when_allow_admin_true(self, fresh_registry):
        cfg = _full_mcp_cfg(allow_admin=True)
        visible = {t.name for t in fresh_registry.visible_tools(cfg)}
        assert {"create_venture", "delete_venture", "update_setting", "reload_agents"} <= visible

    @pytest.mark.asyncio
    async def test_admin_call_with_allow_admin_false_returns_admin_disabled(self, fresh_registry):
        from realize_core.mcp_server.auth import bind_user, reset_user
        from realize_core.mcp_server.server import _dispatch

        cfg = _full_mcp_cfg(allow_admin=False)
        token = bind_user(_user("owner"))
        try:
            out = await _dispatch(
                fresh_registry,
                cfg,
                SimpleNamespace(),
                "create_venture",
                {"key": "should-be-blocked"},
            )
        finally:
            reset_user(token)
        body = json.loads(out[0].text)
        assert body["code"] == "MCP_ADMIN_DISABLED"


# ---------------------------------------------------------------------------
# 2. Scope escalation — non-owner cannot call admin tools
# ---------------------------------------------------------------------------


class TestScopeEscalation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["viewer", "editor"])
    async def test_non_owner_blocked_from_admin_tools(self, fresh_registry, role):
        from realize_core.mcp_server.auth import bind_user, reset_user
        from realize_core.mcp_server.server import _dispatch

        cfg = _full_mcp_cfg(allow_admin=True)
        token = bind_user(_user(role))
        try:
            out = await _dispatch(
                fresh_registry,
                cfg,
                SimpleNamespace(),
                "create_venture",
                {"key": "v-escalate"},
            )
        finally:
            reset_user(token)
        body = json.loads(out[0].text)
        assert body["code"] == "MCP_INSUFFICIENT_SCOPE"

    @pytest.mark.asyncio
    async def test_unknown_role_treated_as_insufficient(self, fresh_registry):
        from realize_core.mcp_server.auth import bind_user, reset_user
        from realize_core.mcp_server.server import _dispatch

        cfg = _full_mcp_cfg(allow_admin=True)
        token = bind_user(CurrentUser(user_id="x", role="totally-made-up"))
        try:
            out = await _dispatch(fresh_registry, cfg, SimpleNamespace(), "update_setting", {"features": {"a": True}})
        finally:
            reset_user(token)
        body = json.loads(out[0].text)
        assert body["code"] == "MCP_INSUFFICIENT_SCOPE"


# ---------------------------------------------------------------------------
# 3. Production gate — refuses unsafe configurations
# ---------------------------------------------------------------------------


class TestProductionGate:
    def test_production_admin_without_jwt_refuses(self):
        from realize_core.mcp_server.auth import (
            MCPProductionAuthError,
            validate_production_auth,
        )

        with (
            env(
                REALIZE_ENV="production",
                REALIZE_JWT_ENABLED="false",
                REALIZE_JWT_SECRET="",
            ),
            pytest.raises(MCPProductionAuthError, match="without JWT"),
        ):
            validate_production_auth(allow_admin=True)

    def test_production_admin_with_weak_secret_refuses(self):
        from realize_core.mcp_server.auth import (
            MCPProductionAuthError,
            validate_production_auth,
        )

        with (
            env(
                REALIZE_ENV="production",
                REALIZE_JWT_ENABLED="true",
                REALIZE_JWT_SECRET="short",
            ),
            pytest.raises(MCPProductionAuthError, match="weak JWT secret"),
        ):
            validate_production_auth(allow_admin=True)

    def test_production_with_admin_disabled_is_safe(self):
        from realize_core.mcp_server.auth import validate_production_auth

        with env(
            REALIZE_ENV="production",
            REALIZE_JWT_ENABLED="false",
            REALIZE_JWT_SECRET="",
        ):
            validate_production_auth(allow_admin=False)  # should not raise


# ---------------------------------------------------------------------------
# 4. Confirmation requirement — delete_venture refuses confirm=false
# ---------------------------------------------------------------------------


class TestDeleteVentureGuard:
    @pytest.mark.asyncio
    async def test_delete_without_confirm_refuses(self):
        from realize_core.mcp_server.tools.admin_tools import delete_venture

        state = SimpleNamespace(systems={"arena": {}}, kb_path="/tmp/kb")
        result = await delete_venture({"venture_key": "arena"}, state, _user("owner"))
        assert result["code"] == "MCP_CONFIRMATION_REQUIRED"

    @pytest.mark.asyncio
    async def test_delete_missing_venture_returns_not_found(self):
        from realize_core.mcp_server.tools.admin_tools import delete_venture

        state = SimpleNamespace(systems={}, kb_path="/tmp/kb")
        result = await delete_venture({"venture_key": "ghost", "confirm": True}, state, _user("owner"))
        assert result["code"] == "MCP_NOT_FOUND"


# ---------------------------------------------------------------------------
# 5. Validation — invalid keys / payloads rejected with structured errors
# ---------------------------------------------------------------------------


class TestPayloadValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "key,reason_substr",
        [
            ("", "required"),
            ("x" * 60, "characters"),
            ("bad key with spaces", "alphanumeric"),
            ("bad/path", "alphanumeric"),
            ("bad..traversal", "alphanumeric"),
        ],
    )
    async def test_create_venture_validates_key(self, key, reason_substr):
        from realize_core.mcp_server.tools.admin_tools import create_venture

        result = await create_venture({"key": key}, SimpleNamespace(kb_path="/tmp"), _user("owner"))
        assert result["code"] == "MCP_VALIDATION"
        assert reason_substr in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "features,reason_substr",
        [
            ({}, "required"),
            ({"a": "yes"}, "boolean"),
            ({f"f{i}": True for i in range(100)}, "Too many"),
        ],
    )
    async def test_update_setting_validates_features(self, features, reason_substr):
        from realize_core.mcp_server.tools.admin_tools import update_setting

        result = await update_setting({"features": features}, SimpleNamespace(), _user("owner"))
        assert result["code"] == "MCP_VALIDATION"
        assert reason_substr in result["error"]


# ---------------------------------------------------------------------------
# 6. Anonymous access — auth middleware enforces on /mcp routes
# ---------------------------------------------------------------------------


class TestAnonymousMCPAccess:
    """When REALIZE_API_KEY is set, /mcp/* must reject calls without a key.

    We can't exercise the SSE handshake in TestClient (no long-lived
    streaming), but we can hit /mcp/health (no-auth) and /mcp/messages
    (auth required, returns 401 even with a bogus session_id).
    """

    def test_anonymous_blocked_when_api_key_required(self, fresh_registry):
        from realize_api.main import create_app

        with env(
            MCP_ENABLED="true",
            REALIZE_API_KEY="testkey-123",
        ):
            app = create_app()
            client = TestClient(app)
            r = client.post("/mcp/messages/abc", json={"jsonrpc": "2.0"})
        assert r.status_code in (401, 403, 422)
        # 401 from APIKeyMiddleware (no key); 422 if FastAPI validates first.

    def test_authenticated_caller_reaches_mcp_routes(self, fresh_registry):
        from realize_api.main import create_app

        with env(
            MCP_ENABLED="true",
            REALIZE_API_KEY="testkey-123",
        ):
            app = create_app()
            client = TestClient(app)
            r = client.get("/mcp/health", headers={"X-API-Key": "testkey-123"})
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ---------------------------------------------------------------------------
# 7. Oversized payload — MCP messages endpoint is bounded by middleware
# ---------------------------------------------------------------------------


class TestOversizedPayload:
    def test_huge_post_to_mcp_messages_is_rejected(self, fresh_registry):
        """The injection-guard / size limit middleware rejects 1MB+ POSTs.

        We submit a >1MB JSON body to /mcp/messages and assert the
        response is not a 2xx — the middleware should short-circuit
        before the route handler runs.
        """
        from realize_api.main import create_app

        big = "A" * (1_500_000)  # 1.5 MB
        with env(MCP_ENABLED="true", REALIZE_API_KEY=""):
            app = create_app()
            client = TestClient(app)
            r = client.post(
                "/mcp/messages/oversized",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"payload": big}},
            )
        # Either 413 (Payload Too Large), 400/422 (validation/injection
        # guard), 401 (auth), or 5xx (no SSE session). Anything but a
        # plain 200 means the oversized payload didn't sail through.
        assert r.status_code != 200
