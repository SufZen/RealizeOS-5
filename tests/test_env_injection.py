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


# Characters str.splitlines() treats as line boundaries besides CR/LF (5.31 follow-up #1).
UNICODE_BREAKS = ["\u2028", "\u2029", "\u0085", "\v", "\f", "\x1c", "\x1d", "\x1e"]
_BREAK_IDS = ["u2028", "u2029", "u0085", "vt", "ff", "x1c", "x1d", "x1e"]


@pytest.mark.parametrize("sep", UNICODE_BREAKS, ids=_BREAK_IDS)
def test_setup_connection_rejects_unicode_line_separators(app, tmp_path, sep):
    res = app.put("/api/setup/connection", json={"id": "openai", "value": f"sk-x{sep}REALIZE_API_KEY="})
    assert res.status_code == 400
    assert "line break" in res.json()["detail"]
    assert "REALIZE_API_KEY" not in _env(tmp_path)
    assert "OPENAI_API_KEY" not in _env(tmp_path)


@pytest.mark.parametrize("sep", UNICODE_BREAKS, ids=_BREAK_IDS)
def test_llm_routing_rejects_unicode_line_separators(app, tmp_path, sep):
    for body in ({"tiers": {"fast": f"openai/gpt-4o{sep}X=1"}}, {"primary": f"gemini{sep}X=1"}):
        res = app.put("/api/llm/routing", json=body)
        assert res.status_code == 400
    _assert_clean(tmp_path)
    assert _env(tmp_path) == ""


@pytest.mark.parametrize("sep", UNICODE_BREAKS, ids=_BREAK_IDS)
def test_writer_refuses_unicode_line_separators(tmp_path, monkeypatch, sep):
    monkeypatch.setenv("REALIZE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from realize_api.routes.setup import _write_env_value

    with pytest.raises(ValueError, match="line break"):
        _write_env_value("OPENAI_API_KEY", f"sk-x{sep}REALIZE_API_KEY=")
    with pytest.raises(ValueError, match="line break"):
        _write_env_value(f"OPENAI_API_KEY{sep}X", "v")
    assert _env(tmp_path) == ""
    assert "OPENAI_API_KEY" not in os.environ


def test_existing_separator_in_a_value_does_not_become_a_key(tmp_path, monkeypatch):
    """A .env that already holds U+2028 inside a value is read and rewritten as one line."""
    monkeypatch.setenv("REALIZE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_MODEL_FAST", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-x\u2028REALIZE_API_KEY=\nOTHER=1\n", encoding="utf-8")
    from realize_api.routes.setup import _read_env_file, _write_env_value

    values = _read_env_file()
    assert "REALIZE_API_KEY" not in values
    assert values["OPENAI_API_KEY"] == "sk-x\u2028REALIZE_API_KEY="
    assert values["OTHER"] == "1"

    _write_env_value("LLM_MODEL_FAST", "gemini/gemini-2.5-flash")
    text = _env(tmp_path)
    lines = text.split("\n")
    assert not any(line.startswith("REALIZE_API_KEY") for line in lines)
    assert "REALIZE_API_KEY" not in _read_env_file()
    assert _read_env_file()["LLM_MODEL_FAST"] == "gemini/gemini-2.5-flash"
