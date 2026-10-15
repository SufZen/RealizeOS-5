"""No value written to .env through the API can add a line (newline injection)."""

from __future__ import annotations

import os

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

CR = chr(13)
LF = chr(10)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REALIZE_ROOT", str(tmp_path))
    config_path = tmp_path / "realize-os.yaml"
    config_path.write_text(yaml.safe_dump({"systems": [], "features": {}}), encoding="utf-8")
    monkeypatch.setenv("REALIZE_CONFIG", str(config_path))
    for key in ("EVIL", "X", "ANTHROPIC_API_KEY", "LLM_PRIMARY", "LLM_FALLBACK", "LLM_MODEL_FAST"):
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
    from realize_api.routes import settings_llm, setup

    api = FastAPI()
    api.include_router(setup.router, prefix="/api")
    api.include_router(settings_llm.router, prefix="/api")
    api.state.kb_path = tmp_path
    return TestClient(api)


def _env(tmp_path) -> str:
    path = tmp_path / ".env"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _assert_clean(tmp_path):
    text = _env(tmp_path)
    assert "EVIL" not in text
    assert f"{LF}X=" not in text
    assert not text.startswith("X=")
    assert "EVIL" not in os.environ
    assert not os.environ.get("X")


@pytest.mark.parametrize("value", [f"x{LF}EVIL=1", f"x{CR}EVIL=1", f"x{CR}{LF}EVIL=1"])
def test_setup_connection_rejects_newlines(app, tmp_path, value):
    res = app.put("/api/setup/connection", json={"id": "anthropic", "value": value})
    assert res.status_code == 400
    assert "line break" in res.json()["detail"]
    _assert_clean(tmp_path)
    assert "ANTHROPIC_API_KEY" not in _env(tmp_path)


@pytest.mark.parametrize(
    "body",
    [
        {"tiers": {"fast": f"x{LF}EVIL=1"}},
        {"tiers": {"fast": f"openai/gpt-4o{CR}EVIL=1"}},
        {"tiers": {"fast": "a=b"}},
        {"primary": f"gemini{LF}X=1"},
        {"fallback": ["gemini", f"ollama{LF}X=1"]},
    ],
    ids=["model-lf", "model-cr", "model-equals", "primary-lf", "fallback-lf"],
)
def test_llm_routing_rejects_injection(app, tmp_path, body):
    res = app.put("/api/llm/routing", json=body)
    assert res.status_code == 400
    _assert_clean(tmp_path)
    assert _env(tmp_path) == ""


def test_writer_refuses_line_breaks(tmp_path, monkeypatch):
    monkeypatch.setenv("REALIZE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    from realize_api.routes.setup import _write_env_value

    for value in (f"a{LF}EVIL=1", f"a{CR}b"):
        with pytest.raises(ValueError, match="line break"):
            _write_env_value("LLM_MODEL_FAST", value)
    assert _env(tmp_path) == ""


def test_a_normal_value_still_saves(app, tmp_path):
    res = app.put("/api/llm/routing", json={"tiers": {"fast": "gemini/gemini-2.5-flash"}})
    assert res.status_code == 200, res.text
    assert "LLM_MODEL_FAST=gemini/gemini-2.5-flash" in _env(tmp_path)
