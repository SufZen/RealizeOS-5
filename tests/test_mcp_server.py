"""Unit + integration tests for the built-in RealizeOS MCP server.

Covers:

* Registry — chat family loads and only chat tools are visible until
  KB/ops/admin land in subsequent stories.
* Config resolver — env vars override yaml, defaults match spec.
* Scope enforcement — owner > editor > read.
* Dispatch — list_tools returns the configured surface; call_tool wires
  through to the existing REST handler.
* FastAPI mount — routes appear only when MCP is enabled.
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
    """Temporarily set/unset environment variables."""
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
    """Reset the singleton registry between tests."""
    from realize_core.mcp_server import registry as registry_mod

    registry_mod.reset_for_tests()
    yield registry_mod.get_registry()
    registry_mod.reset_for_tests()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestMcpConfig:
    def test_defaults_off(self):
        from realize_core.mcp_server.config import mcp_config_from_env

        with env(MCP_ENABLED=None, MCP_EXPOSE_KB=None, MCP_EXPOSE_OPS=None, MCP_ALLOW_ADMIN=None):
            cfg = mcp_config_from_env({})
        assert cfg.enabled is False
        assert cfg.allow_admin is False
        assert cfg.families == ["chat", "kb", "ops"]  # kb/ops default true; admin default false

    def test_env_overrides_yaml(self):
        from realize_core.mcp_server.config import mcp_config_from_env

        yaml = {"mcp": {"enabled": False, "allow_admin": False}}
        with env(MCP_ENABLED="true", MCP_ALLOW_ADMIN="true"):
            cfg = mcp_config_from_env(yaml)
        assert cfg.enabled is True
        assert cfg.allow_admin is True
        assert "admin" in cfg.families

    def test_families_when_kb_off(self):
        from realize_core.mcp_server.config import mcp_config_from_env

        with env(MCP_EXPOSE_KB="false", MCP_EXPOSE_OPS="false"):
            cfg = mcp_config_from_env({})
        assert cfg.families == ["chat"]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_chat_family_registered(self, fresh_registry):
        names = {t.name for t in fresh_registry.all()}
        assert {
            "realize_chat",
            "realize_health",
            "realize_status",
            "list_systems",
            "list_agents",
            "list_skills",
        } <= names

    def test_registered_families_progress_with_stories(self, fresh_registry):
        # Tracks story completion: chat (Story 2), kb (Story 3), ops
        # (Story 4), admin (Story 5). New families append here as each
        # story lands.
        families = {t.family for t in fresh_registry.all()}
        assert "chat" in families
        assert "kb" in families  # Story 3
        # ops / admin land in Stories 4 / 5.

    def test_visible_tools_respects_config(self, fresh_registry):
        from realize_core.mcp_server.config import McpConfig

        cfg = McpConfig(
            enabled=True,
            expose_kb=False,
            expose_ops=False,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        visible = fresh_registry.visible_tools(cfg)
        assert visible, "chat family must always be visible"
        assert all(t.family == "chat" for t in visible)
        # Hidden families (kb / ops / admin) reduce visible vs total once
        # they're registered.
        total = len(fresh_registry.all())
        assert len(visible) <= total

    def test_double_register_raises(self, fresh_registry):
        from realize_core.mcp_server.registry import MCPTool

        async def _noop(args, app_state, user):
            return {}

        dup = MCPTool(
            name="realize_chat",
            family="chat",
            description="dup",
            input_schema={"type": "object"},
            scope="read",
            handler=_noop,
        )
        with pytest.raises(ValueError, match="already registered"):
            fresh_registry.register(dup)

    def test_unknown_family_rejected(self):
        from realize_core.mcp_server.registry import MCPTool

        async def _noop(args, app_state, user):
            return {}

        with pytest.raises(ValueError, match="Unknown family"):
            MCPTool(
                name="x",
                family="bogus",
                description="",
                input_schema={"type": "object"},
                scope="read",
                handler=_noop,
            )


# ---------------------------------------------------------------------------
# Scope enforcement
# ---------------------------------------------------------------------------


class TestScopes:
    @pytest.mark.parametrize(
        "role,scope,expected",
        [
            ("owner", "read", True),
            ("owner", "editor", True),
            ("owner", "owner", True),
            ("editor", "read", True),
            ("editor", "editor", True),
            ("editor", "owner", False),
            ("viewer", "read", True),
            ("viewer", "editor", False),
            ("viewer", "owner", False),
            ("", "read", False),
            (None, "read", False),
            ("unknown_role", "read", False),
        ],
    )
    def test_role_meets_scope(self, role, scope, expected):
        from realize_core.mcp_server.registry import role_meets_scope

        assert role_meets_scope(role, scope) is expected


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class TestDispatch:
    @pytest.mark.asyncio
    async def test_realize_health_returns_ok(self, fresh_registry):
        from realize_core.mcp_server.config import McpConfig
        from realize_core.mcp_server.server import _dispatch

        cfg = McpConfig(
            enabled=True,
            expose_kb=False,
            expose_ops=False,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        out = await _dispatch(fresh_registry, cfg, SimpleNamespace(), "realize_health", {})
        assert len(out) == 1
        payload = json.loads(out[0].text)
        assert payload["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_structured_error(self, fresh_registry):
        from realize_core.mcp_server.config import McpConfig
        from realize_core.mcp_server.server import MCPErrorCode, _dispatch

        cfg = McpConfig(
            enabled=True,
            expose_kb=False,
            expose_ops=False,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        out = await _dispatch(fresh_registry, cfg, SimpleNamespace(), "no_such_tool", {})
        body = json.loads(out[0].text)
        assert body["code"] == MCPErrorCode.NOT_FOUND

    @pytest.mark.asyncio
    async def test_insufficient_scope_returns_403_code(self, fresh_registry):
        from realize_core.mcp_server.auth import bind_user, reset_user
        from realize_core.mcp_server.config import McpConfig
        from realize_core.mcp_server.server import MCPErrorCode, _dispatch

        cfg = McpConfig(
            enabled=True,
            expose_kb=False,
            expose_ops=False,
            allow_admin=False,
            audit_full_payload=False,
            bearer_token_override="",
        )
        token = bind_user(CurrentUser(user_id="u", role="viewer"))
        try:
            out = await _dispatch(
                fresh_registry, cfg, SimpleNamespace(), "clear_history", {"system_key": "s", "user_id": "u"}
            )
        finally:
            reset_user(token)
        body = json.loads(out[0].text)
        assert body["code"] == MCPErrorCode.INSUFFICIENT_SCOPE


# ---------------------------------------------------------------------------
# Production auth gate
# ---------------------------------------------------------------------------


class TestProductionAuth:
    def test_dev_mode_no_op(self):
        from realize_core.mcp_server.auth import validate_production_auth

        with env(REALIZE_ENV="development"):
            validate_production_auth(allow_admin=True)  # should not raise

    def test_production_admin_requires_jwt(self):
        from realize_core.mcp_server.auth import (
            MCPProductionAuthError,
            validate_production_auth,
        )

        with env(REALIZE_ENV="production", REALIZE_JWT_ENABLED="false", REALIZE_JWT_SECRET=""):
            with pytest.raises(MCPProductionAuthError, match="without JWT"):
                validate_production_auth(allow_admin=True)

    def test_production_admin_requires_strong_secret(self):
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

    def test_production_admin_disabled_is_safe(self):
        from realize_core.mcp_server.auth import validate_production_auth

        with env(REALIZE_ENV="production", REALIZE_JWT_ENABLED="false"):
            validate_production_auth(allow_admin=False)  # should not raise


# ---------------------------------------------------------------------------
# FastAPI mount
# ---------------------------------------------------------------------------


@pytest.fixture
def app_factory(fresh_registry):
    """Build a fresh FastAPI app for each test (MCP enabled/disabled via env)."""

    def _build():
        from realize_api.main import create_app

        return create_app()

    return _build


class TestFastAPIMount:
    def test_health_route_exists_when_enabled(self, app_factory):
        with env(MCP_ENABLED="true"):
            app = app_factory()
            client = TestClient(app)
            r = client.get("/mcp/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["tools"] >= 6  # at least the 10 chat-family tools, minus admin

    def test_disabled_route_not_registered(self, app_factory):
        """When MCP is disabled the /mcp/* router is not mounted.

        FastAPI's catch-all SPA route then serves dashboard HTML for
        these paths, but the MCP JSON endpoint must not respond.
        """
        with env(MCP_ENABLED="false"):
            app = app_factory()
            mounted_paths = {getattr(r, "path", None) for r in app.routes}
        assert "/mcp/health" not in mounted_paths
        assert "/mcp/sse" not in mounted_paths
