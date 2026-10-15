"""Tests for realize_core.llm.router — task classification and model selection.

Covers:
- All task type classifications (simple, content, reasoning, financial, etc.)
- Edge cases: empty message, short message, mixed keywords, case insensitivity
- Tier selection, tier resolution (env overrides, per-provider defaults)
- route_completion fallback, route_to_llm, routing_table
- Self-tuning quality override mechanism
- Benchmark-based model selection (V5)
"""

from unittest.mock import patch

import pytest
from realize_core.config import MODELS
from realize_core.llm.base_provider import REFUSAL_ERROR, BaseLLMProvider, LLMResponse, ModelInfo
from realize_core.llm.registry import ProviderRegistry
from realize_core.llm.router import (
    ALL_FAILED_TEXT,
    COMPLEX_KEYWORDS,
    CONTENT_KEYWORDS,
    FINANCIAL_KEYWORDS,
    GOOGLE_KEYWORDS,
    REASONING_KEYWORDS,
    SIMPLE_KEYWORDS,
    TASK_TIERS,
    TIERS,
    WEB_ACTION_KEYWORDS,
    WEB_RESEARCH_KEYWORDS,
    _get_quality_override,
    classify_task,
    parse_model_string,
    resolve_tier,
    route_completion,
    route_to_llm,
    routing_table,
    select_model,
    select_model_by_benchmark,
)

# ---------------------------------------------------------------------------
# Task classification
# ---------------------------------------------------------------------------


class TestClassifyTask:
    """Test task classification for all supported types."""

    # Simple tasks
    def test_simple_greeting(self):
        assert classify_task("hello") == "simple"

    def test_simple_thanks(self):
        assert classify_task("thanks") == "simple"

    def test_simple_explain(self):
        assert classify_task("explain how this works") == "simple"

    def test_simple_status(self):
        assert classify_task("show me the status") == "simple"

    def test_simple_help(self):
        assert classify_task("help me understand this") == "simple"

    # Content tasks
    def test_content_write(self):
        assert classify_task("write a blog post about AI") == "content"

    def test_content_newsletter(self):
        assert classify_task("write a newsletter for our clients") == "content"

    def test_content_linkedin(self):
        assert classify_task("create a linkedin post") == "content"

    def test_content_headline(self):
        assert classify_task("write a headline for our campaign") == "content"

    # Financial tasks
    def test_financial_roi(self):
        assert classify_task("what's the roi on this deal") == "financial"

    def test_financial_revenue(self):
        assert classify_task("what's our revenue projection for Q2") == "financial"

    def test_financial_budget(self):
        assert classify_task("review the budget breakdown") == "financial"

    def test_financial_cash_flow(self):
        assert classify_task("analyze the cash flow statement") == "financial"

    # Reasoning tasks
    def test_reasoning_analyze(self):
        assert classify_task("analyze our market positioning") == "reasoning"

    def test_reasoning_strategy(self):
        assert classify_task("analyze our market positioning strategy") in ("reasoning", "strategy")

    def test_reasoning_contract(self):
        assert classify_task("review this contract for issues") == "reasoning"

    def test_reasoning_architecture(self):
        assert classify_task("design the system architecture") == "reasoning"

    # Complex tasks
    def test_complex_cross_system(self):
        assert classify_task("cross-system analysis of all ventures") == "complex"

    def test_complex_portfolio(self):
        assert classify_task("portfolio review across all systems") == "complex"

    def test_complex_ecosystem(self):
        assert classify_task("review our ecosystem strategy") == "complex"

    # Google Workspace tasks
    def test_google_email(self):
        assert classify_task("check my emails from today") == "google"

    def test_google_calendar(self):
        assert classify_task("what's on my calendar this week") == "google"

    def test_google_drive(self):
        assert classify_task("save this to google drive") == "google"

    # Web research tasks
    def test_web_research_search(self):
        assert classify_task("search the web for latest AI news") == "web_research"

    def test_web_research_lookup(self):
        assert classify_task("look up competitor pricing") == "web_research"

    def test_web_research_browse(self):
        assert classify_task("browse the latest market data") == "web_research"

    # Web action tasks
    def test_web_action_post(self):
        assert classify_task("post on linkedin") == "web_action"

    def test_web_action_navigate(self):
        assert classify_task("navigate to the registration page") == "web_action"

    # Edge cases
    def test_empty_message_defaults_to_simple(self):
        """Empty string should default to 'simple'."""
        result = classify_task("")
        assert result == "simple"

    def test_short_message_defaults_to_simple(self):
        """Very short unclassifiable message defaults to simple."""
        result = classify_task("ok")
        assert result == "simple"

    def test_case_insensitive(self):
        """Classification is case-insensitive."""
        assert classify_task("WRITE A BLOG POST") == "content"
        assert classify_task("What's Our REVENUE?") == "financial"

    def test_google_takes_priority_over_content(self):
        """Google keywords take priority because they're checked first."""
        result = classify_task("draft email about the newsletter")
        assert result == "google"  # "email" keyword matches Google first

    def test_unclassifiable_defaults_to_simple(self):
        """Messages with no matching keywords default to simple."""
        result = classify_task("abcdef xyz 12345")
        assert result == "simple"

    def test_general_question_reasonable(self):
        """General questions get a reasonable classification."""
        result = classify_task("what should we focus on next quarter")
        assert result in ("general", "strategy", "simple", "reasoning")


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------


class TestSelectModel:
    """select_model maps task types to provider-neutral tiers."""

    @pytest.fixture(autouse=True)
    def _no_feedback(self):
        with patch("realize_core.llm.router._get_quality_override", return_value=None):
            yield

    @pytest.mark.parametrize(
        "task_type,tier",
        [
            ("simple", "fast"),
            ("content", "standard"),
            ("reasoning", "standard"),
            ("financial", "standard"),
            ("google", "standard"),
            ("web_research", "standard"),
            ("web_action", "standard"),
            ("complex", "deep"),
        ],
    )
    def test_task_type_maps_to_tier(self, task_type, tier):
        assert select_model(task_type) == tier

    def test_unknown_task_type_defaults_to_fast(self):
        assert select_model("unknown_type_xyz") == "fast"

    def test_every_tier_is_known(self):
        assert set(TASK_TIERS.values()) <= set(TIERS)


# ---------------------------------------------------------------------------
# Quality override (self-tuning)
# ---------------------------------------------------------------------------


class TestQualityOverride:
    def test_no_signals_returns_none(self):
        """When no feedback signals exist, no override."""
        import sys

        with patch.dict(sys.modules, {"realize_core.memory.store": None}):
            result = _get_quality_override("simple")
            assert result is None

    def test_import_error_handled(self):
        """If memory module isn't available, override returns None gracefully."""
        # This should not raise — the function catches the ImportError
        result = _get_quality_override("simple")
        # Result depends on whether memory module exists; just verify no crash
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# Keyword sets are non-empty
# ---------------------------------------------------------------------------


class TestKeywordSetsIntegrity:
    """Ensure keyword sets haven't been accidentally emptied."""

    def test_complex_keywords_exist(self):
        assert len(COMPLEX_KEYWORDS) > 0

    def test_financial_keywords_exist(self):
        assert len(FINANCIAL_KEYWORDS) > 0

    def test_reasoning_keywords_exist(self):
        assert len(REASONING_KEYWORDS) > 0

    def test_content_keywords_exist(self):
        assert len(CONTENT_KEYWORDS) > 0

    def test_simple_keywords_exist(self):
        assert len(SIMPLE_KEYWORDS) > 0

    def test_google_keywords_exist(self):
        assert len(GOOGLE_KEYWORDS) > 0

    def test_web_research_keywords_exist(self):
        assert len(WEB_RESEARCH_KEYWORDS) > 0

    def test_web_action_keywords_exist(self):
        assert len(WEB_ACTION_KEYWORDS) > 0


# ---------------------------------------------------------------------------
# Benchmark-based model selection (V5)
# ---------------------------------------------------------------------------


class TestBenchmarkSelection:
    """Test benchmark-based model selection."""

    def test_returns_model_id_for_reasoning(self):
        """Benchmark selection returns a model for reasoning tasks."""
        result = select_model_by_benchmark("reasoning")
        assert result is not None
        assert isinstance(result, str)

    def test_returns_model_id_for_simple(self):
        result = select_model_by_benchmark("simple")
        assert result is not None

    def test_returns_model_id_for_content(self):
        result = select_model_by_benchmark("content")
        assert result is not None

    def test_cost_optimized_strategy(self):
        result = select_model_by_benchmark("simple", strategy="cost_optimized")
        assert result is not None

    def test_quality_first_strategy(self):
        result = select_model_by_benchmark("reasoning", strategy="quality_first")
        assert result is not None

    def test_speed_first_strategy(self):
        result = select_model_by_benchmark("simple", strategy="speed_first")
        assert result is not None

    def test_available_models_filter(self):
        """Only returns from available models when specified."""
        available = {"claude-sonnet-5-5"}
        result = select_model_by_benchmark("reasoning", available_models=available)
        assert result == "claude-sonnet-5-5"

    def test_returns_none_when_cache_fails(self):
        """Returns None gracefully when benchmark cache is unavailable."""
        with patch("realize_core.llm.benchmark_cache.get_benchmark_cache") as mock:
            mock.side_effect = Exception("Cache broken")
            result = select_model_by_benchmark("reasoning")
            assert result is None

    def test_all_task_types_return_result(self):
        """Every valid task type returns a benchmark result."""
        task_types = ["simple", "content", "reasoning", "financial", "complex"]
        for tt in task_types:
            result = select_model_by_benchmark(tt)
            assert result is not None, f"No benchmark result for task_type={tt}"


# ---------------------------------------------------------------------------
# Tier resolution, route_completion and routing_table
# ---------------------------------------------------------------------------


class _TierFake(BaseLLMProvider):
    """Provider stub with per-tier models that records each call."""

    def __init__(self, provider_name, models=None, tiers=None, ok=True, refuse=False, text=None):
        self._name = provider_name
        self._models = models or {}  # registry key -> model id
        self.tier_models = tiers or {}
        self._ok = ok
        self._refuse = refuse
        self._text = text
        self.calls: list[dict] = []

    @property
    def name(self):
        return self._name

    async def complete(self, system_prompt, messages, model=None, **kwargs):
        self.calls.append({"model": model, **kwargs})
        if self._refuse:
            return LLMResponse(text="declined", provider=self._name, error=REFUSAL_ERROR)
        if not self._ok:
            return LLMResponse(text="", provider=self._name, error="boom")
        return LLMResponse(text=self._text or f"from {self._name}", model=model or "", provider=self._name)

    def list_models(self):
        return [ModelInfo(model_id=m, display_name=m) for m in self._models.values()]


class _LegacyFake(BaseLLMProvider):
    """A provider whose complete() predates response_schema / timeout."""

    name = "legacy"

    async def complete(self, system_prompt, messages, model=None, max_tokens=4096, temperature=0.7):
        return LLMResponse(text="legacy ok", provider="legacy")

    def list_models(self):
        return []


def _reg(*providers):
    reg = ProviderRegistry()
    for p in providers:
        reg.register(p, getattr(p, "_models", None) or None)
    reg.set_fallback_chain([p.name for p in providers])
    return reg


@pytest.fixture
def routing_env(monkeypatch):
    """No rate/cost limits, no quality feedback, no tier env overrides."""
    for tier in ("FAST", "STANDARD", "DEEP"):
        monkeypatch.delenv(f"LLM_MODEL_{tier}", raising=False)
    with (
        patch("realize_core.llm.router._check_rate_limit", return_value=True),
        patch("realize_core.llm.router._check_cost_limit", return_value=True),
        patch("realize_core.llm.router._get_quality_override", return_value=None),
    ):
        yield monkeypatch


def _use(reg):
    return patch("realize_core.llm.registry.get_registry", return_value=reg)


class TestParseModelString:
    @pytest.mark.parametrize(
        "model,expected",
        [
            ("anthropic/claude-sonnet-5-5", ("claude", "claude-sonnet-5-5")),
            ("gemini/gemini-2.5-pro", ("gemini", "gemini/gemini-2.5-pro")),
            ("openai/gpt-4o", ("openai", "openai/gpt-4o")),
            ("ollama/qwen3", ("ollama", "ollama_chat/qwen3")),
            ("ollama_chat/qwen3", ("ollama", "ollama_chat/qwen3")),
            ("mistral/mistral-large-latest", ("litellm", "mistral/mistral-large-latest")),
            ("o3-mini", ("litellm", "o3-mini")),
        ],
    )
    def test_prefix_maps_to_provider(self, model, expected):
        assert parse_model_string(model) == expected


class TestResolveTier:
    def test_env_override_wins_and_maps_prefix(self, routing_env):
        gemini = _TierFake("gemini", {"g_flash": "g-flash"}, {"fast": "g_flash"})
        routing_env.setenv("LLM_MODEL_STANDARD", "anthropic/claude-sonnet-5-5")
        routing_env.setenv("LLM_MODEL_DEEP", "ollama/qwen3")
        with _use(_reg(gemini)):
            assert resolve_tier("standard") == ("claude", "claude-sonnet-5-5")
            assert resolve_tier("deep") == ("ollama", "ollama_chat/qwen3")
            assert resolve_tier("fast") == ("gemini", "g-flash")

    def test_env_override_unknown_prefix_goes_to_litellm(self, routing_env):
        routing_env.setenv("LLM_MODEL_FAST", "mistral/mistral-small")
        with _use(_reg(_TierFake("gemini"))):
            assert resolve_tier("fast") == ("litellm", "mistral/mistral-small")

    def test_env_override_accepts_legacy_key(self, routing_env):
        claude = _TierFake("claude", {"claude_opus": "x"})
        routing_env.setenv("LLM_MODEL_STANDARD", "claude_opus")
        with _use(_reg(claude)):
            assert resolve_tier("standard") == ("claude", MODELS["claude_opus"])

    def test_unknown_tier_raises(self, routing_env):
        with _use(_reg(_TierFake("gemini"))), pytest.raises(ValueError):
            resolve_tier("huge")

    def test_no_providers(self, routing_env):
        with _use(ProviderRegistry()):
            assert resolve_tier("fast") == (None, None)

    def test_primary_provider_defaults_per_provider(self, routing_env):
        """Each real provider class names its own model for every tier."""
        from realize_core.llm.litellm_provider import LiteLLMProvider
        from realize_core.llm.providers import gemini_provider, ollama_provider, openai_provider
        from realize_core.llm.providers.claude_provider import ClaudeProvider

        routing_env.setenv("OLLAMA_MODEL", "qwen3")
        routing_env.delenv("GEMINI_PRO_MODEL", raising=False)
        for cls in (
            ClaudeProvider,
            gemini_provider.GeminiProvider,
            openai_provider.OpenAIProvider,
            ollama_provider.OllamaProvider,
            LiteLLMProvider,
        ):
            routing_env.setattr(cls, "is_available", lambda self: True)
        routing_env.setattr(ollama_provider.OllamaProvider, "_model_has_tools", lambda self, m: False)

        providers = {
            "claude": (
                ClaudeProvider(),
                {"claude_sonnet": MODELS["claude_sonnet"], "claude_opus": MODELS["claude_opus"]},
            ),
            "gemini": (gemini_provider.GeminiProvider(), gemini_provider.model_keys()),
            "openai": (openai_provider.OpenAIProvider(), openai_provider.model_keys()),
            "ollama": (ollama_provider.OllamaProvider(), ollama_provider.model_keys()),
            "litellm": (LiteLLMProvider(default_model="mistral/mistral-small"), {}),
        }
        expected = {
            "claude": (MODELS["claude_sonnet"], MODELS["claude_sonnet"], MODELS["claude_opus"]),
            "gemini": (MODELS["gemini_flash"], "gemini/gemini-2.5-pro", "gemini/gemini-2.5-pro"),
            "openai": ("openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4o"),
            "ollama": ("ollama_chat/qwen3",) * 3,
            "litellm": ("mistral/mistral-small",) * 3,
        }
        for primary, models in expected.items():
            reg = ProviderRegistry()
            for p, keys in providers.values():
                reg.register(p, keys)
            reg.set_fallback_chain([primary] + [n for n in providers if n != primary])
            with _use(reg):
                got = tuple(resolve_tier(t) for t in TIERS)
            assert got == tuple((primary, m) for m in models), primary


class TestQualityOverrideTiers:
    def test_simple_upgrades_to_standard(self):
        with patch("realize_core.memory.store.get_feedback_signals", return_value={"negative": 3, "positive": 0}):
            assert _get_quality_override("simple") == "standard"

    def test_content_upgrades_to_deep(self):
        with patch("realize_core.memory.store.get_feedback_signals", return_value={"reset": 3, "positive": 0}):
            assert _get_quality_override("content") == "deep"
            assert select_model("content") == "deep"


class TestRouteCompletion:
    async def test_uses_primary_provider_tier_model(self, routing_env):
        gemini = _TierFake("gemini", {"gemini_pro": "g-pro"}, {"standard": "gemini_pro"})
        with _use(_reg(gemini)):
            response = await route_completion("sys", [{"role": "user", "content": "hi"}], task_type="content")
        assert response.ok
        assert response.text == "from gemini"
        assert gemini.calls == [{"model": "g-pro"}]

    async def test_passes_schema_and_max_tokens_only_when_set(self, routing_env):
        gemini = _TierFake("gemini")
        schema = {"type": "object"}
        with _use(_reg(gemini)):
            await route_completion("s", [], tier="fast", response_schema=schema, max_tokens=600)
            await route_completion("s", [], tier="fast")
        assert gemini.calls[0] == {"model": None, "max_tokens": 600, "response_schema": schema}
        assert gemini.calls[1] == {"model": None}

    async def test_legacy_provider_signature_still_works(self, routing_env):
        with _use(_reg(_LegacyFake())):
            response = await route_completion("s", [], tier="fast")
        assert response.text == "legacy ok"

    async def test_fallback_walks_chain_with_each_providers_tier_model(self, routing_env):
        gemini = _TierFake("gemini", {"gemini_pro": "g-pro"}, {"deep": "gemini_pro"}, ok=False)
        openai = _TierFake("openai", {"gpt4o": "o-4o"}, {"deep": "gpt4o"}, ok=False)
        ollama = _TierFake("ollama", {"ollama": "ollama_chat/qwen3"}, {"deep": "ollama"})
        reg = _reg(gemini, openai, ollama)
        with _use(reg):
            response = await route_completion("s", [], tier="deep")
        assert response.text == "from ollama"
        assert [c["model"] for c in gemini.calls + openai.calls + ollama.calls] == [
            "g-pro",
            "o-4o",
            "ollama_chat/qwen3",
        ]

    async def test_fallback_uses_public_registry_api(self, routing_env):
        """The router reads the chain through fallback_chain(), not private attributes."""
        gemini = _TierFake("gemini", ok=False)
        openai = _TierFake("openai")
        reg = _reg(gemini, openai)
        reg._fallback_chain = ["gemini"]  # the private list is ignored when the public API says otherwise
        with _use(reg), patch.object(reg, "fallback_chain", return_value=["gemini", "openai"]):
            response = await route_completion("s", [], tier="fast")
        assert response.text == "from openai"

    async def test_refusal_is_final(self, routing_env):
        gemini = _TierFake("gemini", refuse=True)
        openai = _TierFake("openai")
        with _use(_reg(gemini, openai)):
            response = await route_completion("s", [], tier="fast")
        assert response.refused
        assert openai.calls == []

    async def test_explicit_model_beats_tier(self, routing_env):
        gemini = _TierFake("gemini", {"g_flash": "g-flash"}, {"fast": "g_flash"})
        openai = _TierFake("openai", {"gpt4o": "openai/gpt-4o"})
        with _use(_reg(gemini, openai)):
            await route_completion("s", [], tier="fast", model="openai/gpt-4o")
            await route_completion("s", [], tier="fast", model="gpt4o")
        assert [c["model"] for c in openai.calls] == ["openai/gpt-4o", "openai/gpt-4o"]
        assert gemini.calls == []

    async def test_failed_pinned_model_retries_its_provider_with_the_tier_model(self, routing_env):
        """A dead pinned model must not stop the primary from answering with its own tier model."""

        class _DeadPin(_TierFake):
            async def complete(self, system_prompt, messages, model=None, **kwargs):
                if model == "gemini/gemini-retired":
                    self.calls.append({"model": model, **kwargs})
                    return LLMResponse(text="", provider=self._name, error="model not found")
                return await super().complete(system_prompt, messages, model=model, **kwargs)

        gemini = _DeadPin("gemini", {"g_flash": "g-flash"}, {"fast": "g_flash"})
        openai = _TierFake("openai")
        with _use(_reg(gemini, openai)):
            response = await route_completion("s", [], tier="fast", model="gemini/gemini-retired")
        assert response.text == "from gemini"
        assert [c["model"] for c in gemini.calls] == ["gemini/gemini-retired", "g-flash"]
        assert openai.calls == []

    async def test_failed_tier_model_is_not_retried_on_the_same_provider(self, routing_env):
        gemini = _TierFake("gemini", {"g_flash": "g-flash"}, {"fast": "g_flash"}, ok=False)
        openai = _TierFake("openai")
        with _use(_reg(gemini, openai)):
            response = await route_completion("s", [], tier="fast", model="g_flash")
        assert response.text == "from openai"
        assert [c["model"] for c in gemini.calls] == ["g-flash"]

    async def test_env_tier_override_is_used(self, routing_env):
        gemini = _TierFake("gemini", {"g_flash": "g-flash"}, {"fast": "g_flash"})
        openai = _TierFake("openai")
        routing_env.setenv("LLM_MODEL_FAST", "openai/gpt-4o-mini")
        with _use(_reg(gemini, openai)):
            await route_completion("s", [], task_type="simple")
        assert openai.calls == [{"model": "openai/gpt-4o-mini"}]
        assert gemini.calls == []

    async def test_all_fail_returns_error_response(self, routing_env):
        with _use(_reg(_TierFake("gemini", ok=False))):
            response = await route_completion("s", [], tier="fast")
        assert not response.ok
        assert response.text == ALL_FAILED_TEXT

    async def test_rate_limit_returns_error_response(self, routing_env):
        with patch("realize_core.llm.router._check_rate_limit", return_value=False):
            response = await route_completion("s", [], tier="fast")
        assert not response.ok
        assert "too many requests" in response.text


class TestRouteToLLM:
    async def test_returns_text(self, routing_env):
        with _use(_reg(_TierFake("gemini"))):
            assert await route_to_llm("s", [{"role": "user", "content": "hi"}], task_type="simple") == "from gemini"

    async def test_returns_error_text_when_all_fail(self, routing_env):
        with _use(_reg(_TierFake("gemini", ok=False))):
            assert await route_to_llm("s", [], task_type="simple") == ALL_FAILED_TEXT

    async def test_benchmark_model_goes_through_route_completion(self, routing_env):
        openai = _TierFake("openai", {"gpt4o": "openai/gpt-4o"})
        gemini = _TierFake("gemini")
        with (
            _use(_reg(gemini, openai)),
            patch("realize_core.llm.router.select_model_by_benchmark", return_value="openai/gpt-4o"),
        ):
            text = await route_to_llm("s", [], task_type="reasoning", use_benchmark=True)
        assert text == "from openai"
        assert openai.calls == [{"model": "openai/gpt-4o"}]


class TestRoutingTable:
    def test_shape_and_values(self, routing_env):
        gemini = _TierFake(
            "gemini",
            {"g_flash": "g-flash", "gemini_pro": "g-pro"},
            {"fast": "g_flash", "standard": "gemini_pro", "deep": "gemini_pro"},
        )
        routing_env.setenv("LLM_MODEL_DEEP", "anthropic/claude-opus-5-5")
        with _use(_reg(gemini)):
            table = routing_table()
        assert set(table) == set(TIERS)
        assert table["fast"] == {
            "task_types": ["simple"],
            "provider": "gemini",
            "model": "g-flash",
            "source": "default",
        }
        assert table["standard"]["model"] == "g-pro"
        assert "content" in table["standard"]["task_types"]
        assert table["deep"] == {
            "task_types": ["complex"],
            "provider": "claude",
            "model": "claude-opus-5-5",
            "source": "env",
        }
