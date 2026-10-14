"""The agent tool loop follows tier and model routing (LLM_MODEL_<TIER>, primary, fallback)."""

from __future__ import annotations

import pytest
from realize_core.llm.base_provider import STOP_END, BaseLLMProvider, Capability, LLMResponse, ModelInfo
from realize_core.llm.registry import ProviderRegistry

TOOLS = [{"name": "kb_search", "description": "search", "input_schema": {"type": "object", "properties": {}}}]


class _Fake(BaseLLMProvider):
    def __init__(self, name, *, tools=True, tier_models=None, models=()):
        self._name = name
        self._caps = {Capability.TEXT} | ({Capability.TOOLS} if tools else set())
        self.tier_models = dict(tier_models or {})
        self._models = list(models) or [f"{name}-default"]
        self.calls: list[str | None] = []

    @property
    def name(self):
        return self._name

    async def complete(self, system_prompt, messages, **kwargs):
        return LLMResponse(text="plain", provider=self._name)

    async def complete_with_tools(self, system_prompt, messages, tools, model=None, **kwargs):
        self.calls.append(model)
        return LLMResponse(text=f"{self._name}:{model}", provider=self._name, model=model or "", stop_reason=STOP_END)

    def list_models(self):
        return [ModelInfo(model_id=m, capabilities=self._caps) for m in self._models]

    def default_model_id(self):
        return self._models[0]


@pytest.fixture
def providers(monkeypatch):
    import realize_core.base_handler as bh
    import realize_core.llm.registry as llm_registry

    claude = _Fake("claude", tier_models={"standard": "fk_sonnet"}, models=["claude-sonnet-x", "claude-opus-x"])
    gemini = _Fake(
        "gemini",
        tier_models={"fast": "fk_flash", "standard": "fk_pro"},
        models=["gemini/gemini-2.5-flash", "gemini/gemini-2.5-pro"],
    )
    textonly = _Fake("litellm", tools=False, models=["mistral/mistral-small"])
    reg = ProviderRegistry()
    reg.register(claude, {"fk_sonnet": "claude-sonnet-x"})
    reg.register(gemini, {"fk_flash": "gemini/gemini-2.5-flash", "fk_pro": "gemini/gemini-2.5-pro"})
    reg.register(textonly, {"fk_small": "mistral/mistral-small"})
    reg.set_fallback_chain(["claude", "gemini", "litellm"])
    monkeypatch.setattr(llm_registry, "get_registry", lambda: reg)
    monkeypatch.setattr(bh, "agent_tool_schemas", lambda *_a, **_k: TOOLS)
    for tier in ("FAST", "STANDARD", "DEEP"):
        monkeypatch.delenv(f"LLM_MODEL_{tier}", raising=False)
    return reg, claude, gemini, textonly


async def _answer(message):
    from realize_core.base_handler import _answer_with_tools

    return await _answer_with_tools("prompt", [{"role": "user", "content": message}], "agent", None, {}, message=message)


@pytest.mark.asyncio
async def test_pinned_standard_tier_runs_tool_loop_on_that_model(providers, monkeypatch):
    _, claude, gemini, _ = providers
    monkeypatch.setenv("LLM_MODEL_STANDARD", "gemini/gemini-2.5-pro")

    answer, lost = await _answer("what is the budget?")

    assert (answer, lost) == ("gemini:gemini/gemini-2.5-pro", False)
    assert gemini.calls == ["gemini/gemini-2.5-pro"]
    assert claude.calls == []


@pytest.mark.asyncio
async def test_unclassified_message_uses_standard_tier_of_primary(providers):
    _, claude, _, _ = providers

    answer, _ = await _answer("good morning team")

    assert answer == "claude:claude-sonnet-x"
    assert claude.calls == ["claude-sonnet-x"]


@pytest.mark.asyncio
async def test_tier_pinned_to_non_tools_provider_falls_back_with_its_own_tier_model(providers, monkeypatch):
    reg, claude, gemini, textonly = providers
    reg.set_fallback_chain(["gemini", "claude", "litellm"])
    monkeypatch.setenv("LLM_MODEL_STANDARD", "mistral/mistral-small")

    answer, lost = await _answer("what is the budget?")

    assert lost is False
    assert gemini.calls == ["gemini/gemini-2.5-pro"]  # gemini's own standard model
    assert claude.calls == [] and textonly.calls == []


@pytest.mark.asyncio
async def test_tool_capable_provider_stays_monkeypatchable(providers, monkeypatch):
    import realize_core.agents.tool_loop as tl

    reg, _, _, textonly = providers
    reg.set_fallback_chain(["litellm"])
    monkeypatch.setenv("LLM_MODEL_STANDARD", "mistral/mistral-small")
    stub = _Fake("stub", models=["stub-model"])
    monkeypatch.setattr(tl, "tool_capable_provider", lambda: stub)

    answer, _ = await _answer("what is the budget?")

    assert answer == "stub:stub-model"
    assert textonly.calls == []


def test_message_tier():
    from realize_core.llm.router import message_tier

    assert message_tier("good morning team") == "standard"
    assert message_tier("what is the status?") == "fast"
    assert message_tier("review all ventures") == "deep"
    assert message_tier("good morning", default="fast") == "fast"
