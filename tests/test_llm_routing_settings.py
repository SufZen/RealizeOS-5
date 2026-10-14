"""GET/PUT /api/llm/routing: configurable provider and per-tier models (RealizeOS 5.31)."""

from __future__ import annotations

import textwrap

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROUTING_ENV = (
    "LLM_PRIMARY",
    "LLM_FALLBACK",
    "LLM_MODEL_FAST",
    "LLM_MODEL_STANDARD",
    "LLM_MODEL_DEEP",
    "ANTHROPIC_API_KEY",
    "GOOGLE_AI_API_KEY",
    "OPENAI_API_KEY",
    "REALIZE_API_KEY",
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REALIZE_ROOT", str(tmp_path))
    for key in _ROUTING_ENV:
        monkeypatch.delenv(key, raising=False)
    # Keys for two providers so primary can move between them; Ollama is not probed.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-test-0000000000")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")  # nothing listens; probe fails fast
    from realize_api.routes import settings_llm
    from realize_core.llm.registry import reset_registry

    reset_registry()
    app = FastAPI()
    app.include_router(settings_llm.router, prefix="/api")
    yield TestClient(app)
    reset_registry()
    # _write_env_value puts values in os.environ directly; undo them.
    for key in _ROUTING_ENV:
        monkeypatch.delenv(key, raising=False)


def _env_text(tmp_path) -> str:
    path = tmp_path / ".env"
    return path.read_text(encoding="utf-8") if path.exists() else ""


class TestGet:
    def test_matches_the_router(self, client):
        from realize_core.llm.router import routing_table

        body = client.get("/api/llm/routing").json()
        table = routing_table()
        assert set(body["tiers"]) == {"fast", "standard", "deep"}
        for tier, row in table.items():
            assert body["tiers"][tier] == {"provider": row["provider"], "model": row["model"], "source": row["source"]}
            for task_type in row["task_types"]:
                rule = body["routing_rules"][task_type]
                assert (rule["tier"], rule["provider"], rule["model"]) == (tier, row["provider"], row["model"])
        assert "creative" not in body["routing_rules"]  # the old hardcoded table is gone

    def test_reflects_env_overrides(self, client, monkeypatch):
        monkeypatch.setenv("LLM_PRIMARY", "gemini")
        monkeypatch.setenv("LLM_MODEL_DEEP", "openai/gpt-4o")
        from realize_core.llm.registry import reset_registry

        reset_registry()
        body = client.get("/api/llm/routing").json()
        assert body["primary"] == "gemini"
        assert body["fallback"][0] == "gemini"
        assert body["tiers"]["deep"] == {"provider": "openai", "model": "openai/gpt-4o", "source": "env"}
        assert body["tiers"]["fast"]["source"] == "default"
        assert body["tiers"]["fast"]["provider"] == "gemini"
        assert body["settings"]["primary"] == "gemini"
        assert body["settings"]["tiers"]["deep"] == "openai/gpt-4o"
        assert body["routing_rules"]["complex"]["model"] == "openai/gpt-4o"

    def test_lists_providers_from_the_registry(self, client):
        providers = {p["name"]: p for p in client.get("/api/llm/routing").json()["providers"]}
        assert providers["claude"]["available"] is True
        assert providers["gemini"]["available"] is True
        assert providers["openai"]["available"] is False
        assert providers["openai"]["models"] == []
        assert "model_errors" in providers["claude"]


class TestPut:
    def test_writes_env_and_takes_effect_immediately(self, client, tmp_path):
        before = client.get("/api/llm/routing").json()
        assert before["primary"] == "claude"

        res = client.put(
            "/api/llm/routing",
            json={
                "primary": "gemini",
                "tiers": {"fast": "gemini/gemini-2.5-flash", "deep": "anthropic/claude-opus-5-5"},
                "fallback": ["gemini", "claude"],
            },
        )
        assert res.status_code == 200, res.text
        env = _env_text(tmp_path)
        assert "LLM_PRIMARY=gemini" in env
        assert "LLM_MODEL_FAST=gemini/gemini-2.5-flash" in env
        assert "LLM_MODEL_DEEP=anthropic/claude-opus-5-5" in env
        assert "LLM_FALLBACK=gemini,claude" in env

        # The PUT response and a fresh GET both show the new routing (no restart).
        for body in (res.json(), client.get("/api/llm/routing").json()):
            assert body["primary"] == "gemini"
            assert body["fallback"] == ["gemini", "claude"]
            assert body["tiers"]["fast"] == {"provider": "gemini", "model": "gemini/gemini-2.5-flash", "source": "env"}
            assert body["tiers"]["deep"]["provider"] == "claude"
            assert body["tiers"]["standard"]["source"] == "default"

    def test_partial_update_leaves_other_keys(self, client, tmp_path):
        client.put("/api/llm/routing", json={"primary": "gemini", "tiers": {"fast": "gemini/gemini-2.5-flash"}})
        res = client.put("/api/llm/routing", json={"tiers": {"standard": "openai/gpt-4o"}})
        assert res.status_code == 200
        env = _env_text(tmp_path)
        assert "LLM_PRIMARY=gemini" in env
        assert "LLM_MODEL_FAST=gemini/gemini-2.5-flash" in env
        assert "LLM_MODEL_STANDARD=openai/gpt-4o" in env

    def test_empty_string_unsets(self, client, tmp_path):
        client.put("/api/llm/routing", json={"primary": "gemini", "tiers": {"deep": "openai/gpt-4o"}})
        res = client.put("/api/llm/routing", json={"primary": "", "tiers": {"deep": ""}, "fallback": []})
        assert res.status_code == 200
        body = res.json()
        assert body["primary"] == "claude"
        assert body["tiers"]["deep"]["source"] == "default"
        assert body["settings"] == {"primary": "", "tiers": {"fast": "", "standard": "", "deep": ""}, "fallback": []}
        assert "LLM_PRIMARY=\n" in _env_text(tmp_path)

    def test_provider_aliases_accepted(self, client):
        res = client.put("/api/llm/routing", json={"primary": "Google"})
        assert res.status_code == 200
        assert res.json()["primary"] == "gemini"

    @pytest.mark.parametrize(
        "body",
        [
            {"primary": "skynet"},
            {"primary": 5},
            {"fallback": ["gemini", "skynet"]},
            {"fallback": ["claude", "anthropic"]},  # same provider twice
            {"fallback": ["gemini", "gemini"]},
            {"fallback": "gemini"},
            {"tiers": {"fast": "bad model!"}},
            {"tiers": {"fast": "gemini/../x y"}},
            {"tiers": {"fast": "a" * 201}},
            {"tiers": {"fast": 3}},
            {"tiers": {"turbo": "gemini/gemini-2.5-flash"}},
            {"tiers": ["fast"]},
            {"bogus": 1},
            {"primary": "gemini", "bogus": 1},
        ],
    )
    def test_rejects_invalid_input_and_writes_nothing(self, client, tmp_path, body):
        res = client.put("/api/llm/routing", json=body)
        assert res.status_code == 400, res.text
        assert _env_text(tmp_path) == ""

    def test_one_bad_field_blocks_the_valid_ones(self, client, tmp_path):
        res = client.put("/api/llm/routing", json={"primary": "gemini", "fallback": ["skynet"]})
        assert res.status_code == 400
        assert _env_text(tmp_path) == ""
        assert client.get("/api/llm/routing").json()["primary"] == "claude"


def test_setup_allow_list_has_the_routing_keys():
    from realize_api.routes.setup import _ALLOWED_ENV_KEYS, CONNECTION_DEFINITIONS

    expected = {
        "LLM_PRIMARY",
        "LLM_FALLBACK",
        "LLM_MODEL_FAST",
        "LLM_MODEL_STANDARD",
        "LLM_MODEL_DEEP",
        "GEMINI_FLASH_MODEL",
        "GEMINI_PRO_MODEL",
        "OLLAMA_MODEL",
        "LITELLM_MODEL",
        "LITELLM_API_BASE",
        "ANTHROPIC_WORKSPACE_ID",
    }
    assert expected <= _ALLOWED_ENV_KEYS
    by_key = {c["env_key"]: c for c in CONNECTION_DEFINITIONS}
    assert all(by_key[k]["category"] == "llm" for k in expected)
    assert by_key["LITELLM_MODEL"]["id"] == "litellm"
    ids = [c["id"] for c in CONNECTION_DEFINITIONS]
    assert len(ids) == len(set(ids))


def test_env_example_documents_the_keys():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    for key in (
        "LLM_PRIMARY",
        "LLM_FALLBACK",
        "LLM_MODEL_FAST",
        "LLM_MODEL_STANDARD",
        "LLM_MODEL_DEEP",
        "GEMINI_FLASH_MODEL",
        "GEMINI_PRO_MODEL",
        "OLLAMA_HOST",
        "OLLAMA_MODEL",
        "LITELLM_MODEL",
        "LITELLM_API_BASE",
        "ANTHROPIC_WORKSPACE_ID",
        "KB_EMBED_MODEL",
    ):
        assert key in text, key
    assert "At least one provider is required" not in text
    assert "Any ONE provider is enough" in text


# --- Auth: PUT needs the system-manage level and is closed to venture-limited callers ---

_USERS_YAML = textwrap.dedent(
    """
    users:
      - email: owner@realization.co.il
        role: owner
        password_hash: "$2b$12$owner"
      - email: dana@acme.io
        role: operator
        password_hash: "$2b$12$dana"
      - email: adam@acme.io
        role: admin
        ventures: [acme]
        password_hash: "$2b$12$adam"
    """
)


def _app_as(user_id: str, role: str) -> TestClient:
    from realize_api.main import create_app

    app = create_app()
    app.state.systems = {"acme": {"name": "Acme", "agents": {}}}
    app.state.config = {"features": {}}

    @app.middleware("http")
    async def as_principal(request, call_next):
        request.state.user_id = user_id
        request.state.role = role
        request.state.scopes = []
        return await call_next(request)

    return TestClient(app)


def test_put_requires_system_manage():
    from realize_core.security.venture_scope import required_permission

    assert required_permission("PUT", "/api/llm/routing") == "system:manage"


class TestPutAuth:
    @pytest.fixture(autouse=True)
    def _users(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("REALIZE_ROOT", str(tmp_path))
        monkeypatch.delenv("REALIZE_API_KEY", raising=False)
        (tmp_path / "users.yaml").write_text(_USERS_YAML, encoding="utf-8")
        yield
        from realize_core.llm.registry import reset_registry

        reset_registry()
        for key in _ROUTING_ENV:
            monkeypatch.delenv(key, raising=False)

    def test_operator_is_refused(self, tmp_path):
        res = _app_as("dana@acme.io", "operator").put("/api/llm/routing", json={"primary": "gemini"})
        assert res.status_code == 403
        assert "system:manage" in res.json()["detail"]
        assert not (tmp_path / ".env").exists()

    def test_venture_limited_admin_is_refused(self, tmp_path):
        res = _app_as("adam@acme.io", "admin").put("/api/llm/routing", json={"primary": "gemini"})
        assert res.status_code == 403
        assert "every venture" in res.json()["detail"]
        assert not (tmp_path / ".env").exists()

    def test_unscoped_owner_can_save(self, tmp_path):
        res = _app_as("owner@realization.co.il", "owner").put("/api/llm/routing", json={"primary": "gemini"})
        assert res.status_code == 200, res.text
        assert "LLM_PRIMARY=gemini" in _env_text(tmp_path)
