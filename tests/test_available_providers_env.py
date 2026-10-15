"""``available_providers(env=...)`` reads the given mapping without touching ``os.environ``.

5.31 follow-up #3: it used to lay ``env`` over ``os.environ`` for the duration of the
check (process-wide, from an async route), so a concurrent request could see the
overlaid keys. It now evaluates availability from the mapping directly.
"""

from __future__ import annotations

import asyncio
import os
import threading
from unittest.mock import MagicMock, patch

import httpx
import pytest

_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_AI_API_KEY",
    "OLLAMA_BASE_URL",
    "OLLAMA_HOST",
    "LITELLM_API_BASE",
    "LITELLM_MODEL",
)


@pytest.fixture(autouse=True)
def _no_provider_env(monkeypatch):
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)


def _down(*args, **kwargs):
    raise httpx.ConnectError("down")


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"OPENAI_API_KEY": "sk-test-000000000000"}, "openai"),
        ({"GOOGLE_AI_API_KEY": "g-test"}, "gemini"),
        ({"ANTHROPIC_API_KEY": "sk-ant-test-00000000000000"}, "claude"),
        ({"LITELLM_API_BASE": "http://gateway.local:4000"}, "litellm"),
    ],
    ids=["openai", "gemini", "claude", "litellm"],
)
def test_env_is_read_without_mutating_os_environ(env, expected):
    from realize_core.llm.registry import available_providers

    before = dict(os.environ)
    seen_during_call: list[bool] = []

    def probe(*args, **kwargs):
        seen_during_call.append(any(k in os.environ for k in env))
        raise httpx.ConnectError("down")

    with patch("httpx.get", MagicMock(side_effect=probe)):
        result = available_providers(env=env)

    assert expected in result
    assert dict(os.environ) == before
    assert not any(seen_during_call), "env was laid over os.environ during the check"


def test_ollama_is_probed_at_the_given_base_url():
    from realize_core.llm.registry import available_providers

    before = dict(os.environ)
    get = MagicMock(return_value=httpx.Response(200, json={"models": []}))
    with patch("httpx.get", get):
        result = available_providers(env={"OLLAMA_BASE_URL": "http://ollama.example:11434/"})

    assert result == ["ollama"]
    assert get.call_args.args[0] == "http://ollama.example:11434/api/tags"
    assert dict(os.environ) == before


def test_an_empty_env_reports_nothing():
    from realize_core.llm.registry import available_providers

    with patch("httpx.get", MagicMock(side_effect=_down)):
        assert available_providers(env={}) == []


def test_process_env_still_counts(monkeypatch):
    """The mapping is laid over the process environment (read-only), as before."""
    from realize_core.llm.registry import available_providers

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-000000000000")
    with patch("httpx.get", MagicMock(side_effect=_down)):
        assert "openai" in available_providers(env={"GOOGLE_AI_API_KEY": "g-test"})


def test_devmode_check_runs_off_the_event_loop(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from realize_api.routes import devmode
    from realize_core.devmode import health_check

    record: dict = {}

    def fake_check(root, quick=False):
        record["thread"] = threading.current_thread()
        try:
            asyncio.get_running_loop()
            record["on_loop"] = True
        except RuntimeError:
            record["on_loop"] = False
        return []

    monkeypatch.setattr(health_check, "run_health_check", fake_check)
    monkeypatch.chdir(tmp_path)
    api = FastAPI()
    api.include_router(devmode.router, prefix="/api")
    res = TestClient(api).post("/api/devmode/check")
    assert res.status_code == 200, res.text
    assert record["on_loop"] is False, "the health check (provider probe) ran on the event loop"


# --- parity with the adapters (fix round) ------------------------------------------------

_OLLAMA_UP_HOST = "ollama.test"


def _fake_ollama_get(url, *args, **kwargs):
    """Only http://ollama.test:11434 answers /api/tags; every other URL is down."""
    if url.startswith(f"http://{_OLLAMA_UP_HOST}:11434/"):
        return httpx.Response(200, json={"models": []})
    raise httpx.ConnectError("down")


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"OPENAI_API_KEY": "sk-test-000000000000"}, ["openai", "litellm"]),
        ({"ANTHROPIC_API_KEY": "sk-ant-test-00000000000000", "GOOGLE_AI_API_KEY": "g-test"}, ["claude", "gemini"]),
        ({"LITELLM_API_BASE": "http://gateway.local:4000"}, ["litellm"]),
        ({"LITELLM_MODEL": "groq/x"}, []),
        ({"LITELLM_MODEL": "groq/x", "GROQ_API_KEY": "gsk-test"}, ["litellm"]),
        ({"OLLAMA_HOST": f"{_OLLAMA_UP_HOST}:11434"}, ["ollama"]),
        ({"OLLAMA_HOST": f"{_OLLAMA_UP_HOST}:11434", "OLLAMA_BASE_URL": "http://down.test:11434"}, []),
    ],
    ids=[
        "openai",
        "anthropic+google",
        "litellm-api-base",
        "litellm-groq-no-key",
        "litellm-groq-with-key",
        "ollama-host-only",
        "ollama-base-url-wins",
    ],
)
def test_env_check_matches_a_fresh_registry(monkeypatch, env, expected):
    """available_providers(env=...) must agree with the adapters' own is_available()."""
    from realize_core.llm.providers.claude_provider import ClaudeProvider
    from realize_core.llm.registry import ProviderRegistry, available_providers

    monkeypatch.setattr(ClaudeProvider, "_dead_models", {})  # no 404 history from other tests
    for key in (*_KEYS, "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    with (
        patch("httpx.get", MagicMock(side_effect=_fake_ollama_get)),
        patch("httpx.post", MagicMock(side_effect=httpx.ConnectError("no /api/show"))),
    ):
        from_env = available_providers(env=env)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        registry = ProviderRegistry()
        registry.auto_register()
        from_adapters = registry.list_available()

    assert from_env == from_adapters
    assert from_env == expected  # the cases are not vacuous
