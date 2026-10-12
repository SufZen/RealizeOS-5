"""
Tests for LLM fallback routing and Claude model health (QA 5.14, L-1 / L-2).

- L-2: when the primary provider fails, the next provider in the chain is tried
  (the loop used to ``break`` on the already-tried primary and never reach Gemini).
- L-1: a Claude model ID that returns 404 is remembered, skipped by routing and
  reported in Settings, and the defaults are IDs Anthropic actually serves.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest
from realize_core.llm.base_provider import BaseLLMProvider, Capability, LLMResponse, ModelInfo
from realize_core.llm.providers.claude_provider import ClaudeProvider
from realize_core.llm.registry import ProviderRegistry


def _fake_claude_client(**attrs) -> types.ModuleType:
    """A stand-in for realize_core.llm.claude_client.

    Some other test modules replace the real module in sys.modules at import
    time, so these tests install their own instead of patching attributes.
    """
    module = types.ModuleType("realize_core.llm.claude_client")
    module._log_usage = lambda *a, **k: None
    for name, value in attrs.items():
        setattr(module, name, value)
    return module


class _FakeProvider(BaseLLMProvider):
    """Provider stub that returns a fixed response and counts calls."""

    def __init__(self, provider_name: str, ok: bool = True, usable: bool = True):
        self._name = provider_name
        self._ok = ok
        self._usable = usable
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, system_prompt, messages, model=None, max_tokens=4096, temperature=0.7, timeout=60.0):
        self.calls += 1
        if self._ok:
            return LLMResponse(text=f"from {self._name}", model=model or "m", provider=self._name)
        return LLMResponse(text="", model=model or "m", provider=self._name, error="boom")

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(model_id=f"{self._name}-model", display_name=self._name, capabilities={Capability.TEXT})]

    def is_model_usable(self, model_id: str) -> bool:
        return self._usable


def _registry(*providers: _FakeProvider, primary: str) -> ProviderRegistry:
    reg = ProviderRegistry()
    for p in providers:
        keys = {"claude_sonnet": "claude-x"} if p.name == primary else {}
        reg.register(p, keys)
    reg.set_fallback_chain([p.name for p in providers])
    return reg


@pytest.fixture
def no_limits():
    """Disable rate/cost limits and the LiteLLM extended fallback."""
    with (
        patch("realize_core.llm.router._check_rate_limit", return_value=True),
        patch("realize_core.llm.router._check_cost_limit", return_value=True),
        patch("realize_core.llm.router._try_litellm_completion", new=AsyncMock(return_value=None)),
    ):
        yield


class TestFallbackChain:
    async def test_primary_failure_falls_through_to_next_provider(self, no_limits):
        from realize_core.llm.router import route_to_llm

        claude = _FakeProvider("claude", ok=False)
        gemini = _FakeProvider("gemini")
        reg = _registry(claude, gemini, primary="claude")

        with patch("realize_core.llm.registry.get_registry", return_value=reg):
            result = await route_to_llm("sys", [{"role": "user", "content": "hi"}], task_type="content")

        assert result == "from gemini"
        assert claude.calls == 1
        assert gemini.calls == 1

    async def test_skips_unusable_primary_model(self, no_limits):
        from realize_core.llm.router import route_to_llm

        claude = _FakeProvider("claude", usable=False)
        gemini = _FakeProvider("gemini")
        reg = _registry(claude, gemini, primary="claude")

        with patch("realize_core.llm.registry.get_registry", return_value=reg):
            result = await route_to_llm("sys", [{"role": "user", "content": "hi"}], task_type="content")

        assert result == "from gemini"
        # The primary attempt is skipped; claude is only re-tried later as a chain member.
        assert claude.calls <= 1

    async def test_max_retries_still_caps_fallback_attempts(self, no_limits):
        from realize_core.llm.router import route_to_llm

        claude = _FakeProvider("claude", ok=False)
        p1 = _FakeProvider("p1", ok=False)
        p2 = _FakeProvider("p2", ok=False)
        p3 = _FakeProvider("p3")
        reg = _registry(claude, p1, p2, p3, primary="claude")

        with (
            patch("realize_core.llm.registry.get_registry", return_value=reg),
            patch.dict(
                sys.modules,
                {
                    "realize_core.llm.claude_client": _fake_claude_client(
                        call_claude_sonnet=AsyncMock(return_value="last resort"),
                        call_claude_opus=AsyncMock(return_value="last resort"),
                    )
                },
            ),
        ):
            result = await route_to_llm("sys", [{"role": "user", "content": "hi"}], task_type="content", max_retries=2)

        assert (p1.calls, p2.calls, p3.calls) == (1, 1, 0)
        assert result == "last resort"


def _not_found() -> anthropic.NotFoundError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(404, request=request)
    return anthropic.NotFoundError("model: claude-retired", response=response, body=None)


@pytest.fixture
def claude_provider():
    """A ClaudeProvider with a key set, fixed model IDs and a clean dead-model list."""
    ClaudeProvider._dead_models = {}
    models = {"claude_sonnet": "claude-sonnet-test", "claude_opus": "claude-opus-test"}
    with (
        patch("realize_core.config.ANTHROPIC_API_KEY", "test-key"),
        patch.object(ClaudeProvider, "_MODELS", models),
    ):
        yield ClaudeProvider()
    ClaudeProvider._dead_models = {}


class TestClaudeModelHealth:
    def test_defaults_are_undated_ids(self):
        from realize_core.config import DEFAULT_CLAUDE_OPUS_MODEL, DEFAULT_CLAUDE_SONNET_MODEL

        assert DEFAULT_CLAUDE_SONNET_MODEL == "claude-sonnet-4-6"
        assert DEFAULT_CLAUDE_OPUS_MODEL == "claude-opus-4-6"

    async def test_404_marks_model_dead(self, claude_provider):
        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=_not_found())
        with patch.dict(
            sys.modules, {"realize_core.llm.claude_client": _fake_claude_client(_get_client=lambda: client)}
        ):
            response = await claude_provider.complete("sys", [{"role": "user", "content": "hi"}])

        assert response.error == "model_not_found"
        assert not claude_provider.is_model_usable("claude-sonnet-test")
        assert "claude-sonnet-test" in claude_provider.model_errors()
        # Opus still answers, so the provider as a whole stays available.
        assert claude_provider.is_available()

    async def test_provider_unavailable_when_all_models_dead(self, claude_provider):
        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=_not_found())
        with patch.dict(
            sys.modules, {"realize_core.llm.claude_client": _fake_claude_client(_get_client=lambda: client)}
        ):
            await claude_provider.complete("sys", [], model="claude-sonnet-test")
            await claude_provider.complete("sys", [], model="claude-opus-test")

        assert not claude_provider.is_available()

    def test_available_with_key_and_no_failures(self, claude_provider):
        assert claude_provider.is_available()
        assert claude_provider.model_errors() == {}
