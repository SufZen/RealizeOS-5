"""Health, security and setup checks accept any one LLM provider (no provider is required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

OLLAMA_URL = "http://ollama.local:11434"


def _ollama_up():
    """httpx.get answering Ollama's /api/tags, /api/show refused (no real server)."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("httpx.get", MagicMock(return_value=httpx.Response(200, json={"models": []}))))
    stack.enter_context(patch("httpx.post", MagicMock(side_effect=httpx.ConnectError("no /api/show"))))
    return stack


@pytest.fixture(params=["ollama", "litellm", "openai"])
def single_provider(request, monkeypatch, tmp_path):
    """An install with exactly one provider, in the process env and in .env."""
    kind = request.param
    if kind == "ollama":
        env = {"OLLAMA_BASE_URL": OLLAMA_URL}
    elif kind == "litellm":
        env = {"LITELLM_API_BASE": "http://gateway.local:4000", "LITELLM_MODEL": "mistral/mistral-small-latest"}
    else:
        env = {"OPENAI_API_KEY": "sk-test-000000000000"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    (tmp_path / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")
    with _ollama_up() if kind == "ollama" else patch("httpx.get", MagicMock(side_effect=httpx.ConnectError("down"))):
        yield kind, env, tmp_path


def test_helper_reports_the_provider(single_provider):
    from realize_core.llm.registry import any_provider_available, available_providers

    kind, env, _ = single_provider
    assert kind in available_providers()
    assert any_provider_available()


def test_helper_reads_a_given_env_without_keeping_it(single_provider, monkeypatch):
    import os

    from realize_core.llm.registry import any_provider_available

    kind, env, _ = single_provider
    for k in env:
        monkeypatch.delenv(k)
    assert any_provider_available(env=env)
    assert not any(k in os.environ for k in env)


def test_helper_false_without_any_provider():
    from realize_core.llm.registry import any_provider_available

    with patch("httpx.get", MagicMock(side_effect=httpx.ConnectError("down"))):
        assert not any_provider_available()


def test_security_scan_passes(single_provider):
    from realize_core.security.scanner import run_security_scan

    _, _, root = single_provider
    checks = {c["name"]: c for c in run_security_scan(root)["checks"]}
    assert checks["LLM provider configured"]["status"] == "pass"


def test_health_check_env_passes(single_provider):
    from realize_core.devmode.health_check import CheckStatus, check_env_file

    _, env, root = single_provider
    assert check_env_file(root).status == CheckStatus.PASS


def test_health_check_env_warns_without_provider(tmp_path):
    from realize_core.devmode.health_check import CheckStatus, check_env_file

    (tmp_path / ".env").write_text("REALIZE_API_KEY=abcdefgh\n", encoding="utf-8")
    with patch("httpx.get", MagicMock(side_effect=httpx.ConnectError("down"))):
        result = check_env_file(tmp_path)
    assert result.status == CheckStatus.WARN
    assert "provider" in result.message.lower()


def test_workspace_state_has_provider(single_provider):
    from realize_core.config import discover_workspace_state

    _, _, root = single_provider
    state = discover_workspace_state(root, config={"systems": []})
    assert state["has_provider"] is True
    assert not any("provider" in w.lower() for w in state["warnings"])


def test_doctor_accepts_the_provider(single_provider, capsys):
    from realize_core.setup_wizard import run_doctor

    _, _, root = single_provider
    run_doctor(root)
    out = capsys.readouterr().out
    assert "LLM provider available" in out
    assert "no API keys" not in out
