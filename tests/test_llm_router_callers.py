"""Every LLM caller outside the router works with only a non-Claude provider.

Each test registers a single fake "gemini" provider (no Claude anywhere) and
checks the caller gets its answer through ``route_completion``. Direct
provider-client calls and imports are kept out by
``scripts/check_provider_neutral.py`` (tests/test_check_provider_neutral.py).
"""

import json
from typing import ClassVar
from unittest.mock import patch

import pytest
from realize_core.config import MODELS
from realize_core.llm.base_provider import BaseLLMProvider, LLMResponse, ModelInfo
from realize_core.llm.registry import ProviderRegistry


class _FakeGemini(BaseLLMProvider):
    """The only registered provider; replies with ``reply`` and records calls."""

    tier_models: ClassVar[dict[str, str]] = {"fast": "gemini_flash", "standard": "gemini_pro", "deep": "gemini_pro"}

    def __init__(self):
        self.reply = ""
        self.calls: list[dict] = []

    @property
    def name(self):
        return "gemini"

    async def complete(self, system_prompt, messages, model=None, **kwargs):
        self.calls.append({"system_prompt": system_prompt, "messages": messages, "model": model, **kwargs})
        return LLMResponse(text=self.reply, model=model or "", provider="gemini")

    def list_models(self):
        return [ModelInfo(model_id="gemini/gemini-2.5-pro", display_name="Gemini Pro")]


@pytest.fixture
def gemini(monkeypatch):
    for tier in ("FAST", "STANDARD", "DEEP"):
        monkeypatch.delenv(f"LLM_MODEL_{tier}", raising=False)
    provider = _FakeGemini()
    reg = ProviderRegistry()
    reg.register(provider, {"gemini_pro": "gemini/gemini-2.5-pro"})
    reg.set_fallback_chain(["gemini"])
    with (
        patch("realize_core.llm.registry.get_registry", return_value=reg),
        patch("realize_core.llm.router._check_rate_limit", return_value=True),
        patch("realize_core.llm.router._check_cost_limit", return_value=True),
    ):
        yield provider


async def test_review_handler(gemini, monkeypatch):
    import realize_core.base_handler as bh

    monkeypatch.setattr(bh, "get_session", lambda *a: None)
    monkeypatch.setattr(bh, "get_history", lambda *a: [{"role": "assistant", "content": "a draft"}])
    monkeypatch.setattr(bh, "build_system_prompt", lambda **kw: "reviewer prompt")
    gemini.reply = "Verdict: APPROVED"

    result = await bh.handle_review("acme", "u1")

    assert result == "Verdict: APPROVED"
    assert gemini.calls[0]["model"] == "gemini/gemini-2.5-pro"  # standard tier
    assert "a draft" in gemini.calls[0]["messages"][0]["content"]


async def test_review_failure_is_not_stored_as_review(gemini, monkeypatch):
    import realize_core.base_handler as bh
    from realize_core.llm.base_provider import STOP_ERROR

    class _Session:
        drafts = ["d"]
        review = None
        stage = "drafting"
        active_agent = None
        saved = 0

        def latest_draft(self):
            return {"content": "a draft"}

        def save(self):
            self.saved += 1

        def summary(self):
            return "[summary]"

    session = _Session()

    async def broken(*_a, **_k):
        return LLMResponse(text="", error="provider down", stop_reason=STOP_ERROR)

    monkeypatch.setattr(gemini, "complete", broken)
    monkeypatch.setattr(bh, "get_session", lambda *a: session)
    monkeypatch.setattr(bh, "build_system_prompt", lambda **kw: "reviewer prompt")

    result = await bh.handle_review("acme", "u1")

    assert session.review is None
    assert session.stage != "approved"
    assert "review" in result.lower() and "could not" in result.lower()
    assert "An error occurred processing" not in result


async def test_semantic_match_default_llm(gemini):
    from realize_core.skills.semantic import semantic_match

    gemini.reply = json.dumps({"skill_key": "brand", "score": 0.9, "reason": "fits"})

    result = await semantic_match("position my brand", [{"key": "brand", "description": "Brand strategy"}])

    assert result is not None
    assert result.skill_key == "brand"
    assert gemini.calls[0]["response_schema"]["required"] == ["skill_key", "score", "reason"]


async def test_skill_creator_default_llm(gemini):
    from realize_core.skills.creator import create_skill

    gemini.reply = 'name: weekly_report\nversion: "2.0"\ndescription: Weekly report\ntriggers:\n  - weekly report\n'

    result = await create_skill("A skill that writes a weekly report")

    assert result["success"] is True
    assert result["skill_name"] == "weekly_report"
    assert gemini.calls[0]["model"] == "gemini/gemini-2.5-pro"  # standard tier


async def test_skill_creator_reports_llm_failure(gemini):
    from realize_core.skills.creator import create_skill

    async def boom(*a, **k):
        return LLMResponse(text="An error occurred", provider="gemini", error="boom")

    gemini.complete = boom

    result = await create_skill("anything")

    assert result["success"] is False


async def test_prompt_refiner(gemini, tmp_path):
    from realize_core.evolution.prompt_refiner import suggest_prompt_refinement

    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "writer.md").write_text("You are a writer.", encoding="utf-8")
    gemini.reply = json.dumps({"changes": [], "summary": "no change"})

    result = await suggest_prompt_refinement(
        "acme", "writer", ["too long"], kb_path=str(tmp_path), system_config={"agents": {"writer": "agents/writer.md"}}
    )

    assert result["summary"] == "no change"
    assert result["agent_key"] == "writer"
    assert gemini.calls[0]["max_tokens"] == 600
    assert "changes" in gemini.calls[0]["response_schema"]["properties"]


async def test_skill_suggester(gemini):
    from realize_core.evolution.skill_suggester import suggest_skill_from_gap

    gemini.reply = "name: competitor_watch\nversion: '2.0'\n"
    suggestion = {"description": "repeated competitor questions", "action_data": json.dumps({"samples": ["x"]})}

    result = await suggest_skill_from_gap(suggestion)

    assert result.startswith("name: competitor_watch")
    assert gemini.calls[0]["max_tokens"] == 800


async def test_evolution_intent(gemini):
    from realize_core.evolution.handler import analyze_evolution_intent

    gemini.reply = json.dumps({"action": "create_file", "system_key": "acme", "title": "SOP", "content": "x"})

    result = await analyze_evolution_intent("save this as an SOP", "acme")

    assert result["action"] == "create_file"
    assert gemini.calls[0]["model"] == MODELS["gemini_flash"]  # fast tier (legacy key alias)
    assert gemini.calls[0]["response_schema"]["required"] == ["action"]


async def test_evolution_intent_none(gemini):
    from realize_core.evolution.handler import analyze_evolution_intent

    gemini.reply = '{"action": "none"}'

    assert await analyze_evolution_intent("what is the weather", "acme") is None


def test_status_lists_registry_providers(gemini):
    """/status and MCP realize_status report providers from the registry, not env keys."""
    import asyncio

    from realize_core.mcp_server.tools.chat_tools import realize_status

    result = asyncio.run(realize_status({}, object(), None))

    assert result["llm"] == {"gemini": "available"}


def test_nightly_eval_counts_by_recorded_provider(gemini):
    from realize_core.evolution.nightly_eval import _llm_provider

    assert _llm_provider('{"provider": "ollama", "task_type": "simple"}') == "ollama"
    assert _llm_provider('{"model": "gemini/gemini-2.5-pro"}') == "gemini"  # owner looked up in the registry
    assert _llm_provider('{"task_type": "simple", "response_length": 10}') == "other"
    assert _llm_provider("not json mentioning claude") == "other"
