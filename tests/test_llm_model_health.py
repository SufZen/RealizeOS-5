"""
Tests for LLM fallback routing and Claude model health (QA 5.14, L-1 / L-2).

- L-2: when the primary provider fails, the next provider in the chain is tried
  (the loop used to ``break`` on the already-tried primary and never reach Gemini).
- L-1: a Claude model ID that returns 404 is remembered, skipped by routing and
  reported in Settings, and the defaults are IDs Anthropic actually serves.
"""

import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest
import realize_core.llm.claude_models as cm
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

    def __init__(self, provider_name: str, ok: bool = True, usable: bool = True, refuse: bool = False):
        self._name = provider_name
        self._ok = ok
        self._refuse = refuse
        self._usable = usable
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, system_prompt, messages, model=None, max_tokens=4096, temperature=0.7, timeout=60.0):
        self.calls += 1
        if self._refuse:
            return LLMResponse(text="declined", model=model or "m", provider=self._name, error="refusal")
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

    async def test_refusal_is_final_and_not_retried_elsewhere(self, no_limits):
        from realize_core.llm.router import route_to_llm

        claude = _FakeProvider("claude", refuse=True)
        gemini = _FakeProvider("gemini")
        reg = _registry(claude, gemini, primary="claude")

        with patch("realize_core.llm.registry.get_registry", return_value=reg):
            result = await route_to_llm("sys", [{"role": "user", "content": "hi"}], task_type="content")

        assert result == "declined"
        assert gemini.calls == 0

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
    def test_defaults_are_newest_models(self):
        from realize_core.config import DEFAULT_CLAUDE_OPUS_MODEL, DEFAULT_CLAUDE_SONNET_MODEL

        assert DEFAULT_CLAUDE_SONNET_MODEL == "claude-sonnet-5-5"
        assert DEFAULT_CLAUDE_OPUS_MODEL == "claude-opus-5-5"

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


class TestRequestShape:
    """Newer models reject sampling params and think by default (QA follow-up)."""

    @pytest.mark.parametrize(
        "model",
        ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"],
    )
    def test_legacy_models_keep_temperature(self, model):
        assert cm.request_params(model, 4096, 0.7) == {"max_tokens": 4096, "temperature": 0.7}

    @pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-4-7", "claude-fable-5-1"])
    def test_new_models_drop_temperature_and_raise_max_tokens(self, model):
        params = cm.request_params(model, 4096, 0.7)
        assert "temperature" not in params
        assert params["max_tokens"] >= cm.THINKING_MIN_MAX_TOKENS

    def test_pricing_by_model(self):
        assert cm.claude_price("claude-opus-5-5") == (4.0, 20.0)
        assert cm.claude_price("claude-sonnet-5-5") == (2.0, 10.0)
        assert cm.claude_price("claude-opus-4-6") == (5.0, 25.0)
        assert cm.claude_price("claude-opus-4-1-20250805") == (15.0, 75.0)

    async def test_text_read_past_thinking_block(self, claude_provider):
        reply = SimpleNamespace(
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text="hello")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=reply)
        with patch.dict(
            sys.modules, {"realize_core.llm.claude_client": _fake_claude_client(_get_client=lambda: client)}
        ):
            response = await claude_provider.complete(
                "sys", [{"role": "user", "content": "hi"}], model="claude-opus-5-5"
            )

        assert response.ok
        assert response.text == "hello"
        sent = client.messages.create.call_args.kwargs
        assert "temperature" not in sent
        assert sent["max_tokens"] >= 16000

    async def test_refusal_is_reported_as_refused(self, claude_provider):
        reply = SimpleNamespace(
            content=[],
            stop_reason="refusal",
            stop_details=SimpleNamespace(category="cyber"),
            usage=SimpleNamespace(input_tokens=10, output_tokens=0),
        )
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=reply)
        with patch.dict(
            sys.modules, {"realize_core.llm.claude_client": _fake_claude_client(_get_client=lambda: client)}
        ):
            response = await claude_provider.complete(
                "sys", [{"role": "user", "content": "hi"}], model="claude-sonnet-5-5"
            )

        assert response.refused
        assert not response.ok


class TestToolPathModelHealth:
    """F15: a dead model on the native tool path is marked and the next Claude model is used."""

    @staticmethod
    def _reply():
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="done")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    async def _call(self, claude_provider, side_effect):
        calls = AsyncMock(side_effect=side_effect)
        with patch.dict(
            sys.modules, {"realize_core.llm.claude_client": _fake_claude_client(call_claude_with_tools=calls)}
        ):
            response = await claude_provider.complete_with_tools("sys", [{"role": "user", "content": "hi"}], tools=[])
        return response, calls

    async def test_404_marks_dead_and_uses_next_model(self, claude_provider):
        reply = self._reply()
        response, calls = await self._call(claude_provider, [cm.ClaudeModelNotFoundError("claude-sonnet-test"), reply])

        assert response.ok
        assert response.model == "claude-opus-test"
        assert response.raw is reply
        assert [c.kwargs["model"] for c in calls.call_args_list] == ["claude-sonnet-test", "claude-opus-test"]
        assert "claude-sonnet-test" in claude_provider.model_errors()

    async def test_dead_model_is_skipped_on_the_next_turn(self, claude_provider):
        await self._call(claude_provider, [cm.ClaudeModelNotFoundError("claude-sonnet-test"), self._reply()])
        _, calls = await self._call(claude_provider, [self._reply()])

        assert [c.kwargs["model"] for c in calls.call_args_list] == ["claude-opus-test"]

    async def test_all_models_dead_returns_error(self, claude_provider):
        response, calls = await self._call(
            claude_provider,
            [cm.ClaudeModelNotFoundError("claude-sonnet-test"), cm.ClaudeModelNotFoundError("claude-opus-test")],
        )

        assert response.error == "model_not_found"
        assert response.raw is None
        assert calls.await_count == 2

    async def test_transient_error_does_not_switch_models(self, claude_provider):
        response, calls = await self._call(claude_provider, [RuntimeError("Rate limit hit.")])

        assert response.error == "Rate limit hit."
        assert calls.await_count == 1
        assert claude_provider.model_errors() == {}
