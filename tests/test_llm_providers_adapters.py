"""Tests for the LiteLLM-backed provider adapters, Claude normalisation and registry fallback order."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import litellm  # imported up front: it loads .env, which would re-set keys the fixtures delete
import pytest
from realize_core.llm import claude_client
from realize_core.llm.base_provider import (
    EMPTY_ERROR,
    STOP_END,
    STOP_ERROR,
    STOP_MAX_TOKENS,
    STOP_PAUSE,
    STOP_REFUSAL,
    STOP_TOOL_USE,
    BaseLLMProvider,
    Capability,
    LLMResponse,
    ModelInfo,
    ToolCall,
)
from realize_core.llm.providers.claude_provider import ClaudeProvider
from realize_core.llm.providers.gemini_provider import GeminiProvider
from realize_core.llm.providers.ollama_provider import OllamaProvider
from realize_core.llm.providers.openai_provider import OpenAIProvider
from realize_core.llm.registry import ProviderRegistry

MSGS = [{"role": "user", "content": "hello"}]
CLAUDE_TOOL = {
    "name": "search_kb",
    "description": "Search",
    "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
}

_ENV_VARS = (
    "GOOGLE_AI_API_KEY",
    "OPENAI_API_KEY",
    "OLLAMA_BASE_URL",
    "OLLAMA_HOST",
    "OLLAMA_MODEL",
    "LITELLM_API_BASE",
    "LLM_PRIMARY",
    "LLM_FALLBACK",
    "ANTHROPIC_WORKSPACE_ID",
    "GEMINI_PRO_MODEL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def acompletion():
    mock = AsyncMock()
    with (
        patch.object(litellm, "acompletion", mock),
        patch.object(litellm, "cost_per_token", autospec=True, return_value=(0.0015, 0.0005)),
    ):
        yield mock


def _resp(content="hi", tool_calls=None, finish="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _tool_call(call_id="call_1", name="search_kb", arguments='{"q": "x"}'):
    return SimpleNamespace(id=call_id, type="function", function=SimpleNamespace(name=name, arguments=arguments))


# --- Gemini --------------------------------------------------------------------


class TestGemini:
    async def test_passes_prefixed_model_and_api_key(self, acompletion, monkeypatch):
        monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-key")
        acompletion.return_value = _resp("ok")
        resp = await GeminiProvider().complete("sys", MSGS, model="gemini-2.5-flash", max_tokens=100)
        kwargs = acompletion.call_args.kwargs
        assert kwargs["model"] == "gemini/gemini-2.5-flash"
        assert kwargs["api_key"] == "g-key"
        assert kwargs["reasoning_effort"] == "low"
        assert resp.ok
        assert resp.text == "ok"
        assert resp.provider == "gemini"
        assert resp.cost_usd == pytest.approx(0.002)  # from litellm.cost_per_token, not a hardcoded rate

    async def test_max_tokens_floor_for_thinking(self, acompletion, monkeypatch):
        monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-key")
        acompletion.return_value = _resp("ok")
        await GeminiProvider().complete("sys", MSGS, max_tokens=512)
        assert acompletion.call_args.kwargs["max_tokens"] == 8192
        await GeminiProvider().complete("sys", MSGS, max_tokens=20000)
        assert acompletion.call_args.kwargs["max_tokens"] == 20000

    async def test_no_reasoning_effort_for_non_thinking_model(self, acompletion, monkeypatch):
        monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-key")
        acompletion.return_value = _resp("ok")
        await GeminiProvider().complete("sys", MSGS, model="gemini/gemini-1.5-flash")
        assert "reasoning_effort" not in acompletion.call_args.kwargs

    async def test_litellm_api_base_not_applied(self, acompletion, monkeypatch):
        monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-key")
        monkeypatch.setenv("LITELLM_API_BASE", "http://gateway.example")
        acompletion.return_value = _resp("ok")
        await GeminiProvider().complete("sys", MSGS)
        assert "api_base" not in acompletion.call_args.kwargs

    async def test_empty_response_is_an_error_so_router_falls_back(self, acompletion, monkeypatch):
        monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-key")
        acompletion.return_value = _resp("")
        resp = await GeminiProvider().complete("sys", MSGS)
        assert resp.error == EMPTY_ERROR
        assert not resp.ok
        assert resp.stop_reason == STOP_ERROR

    async def test_safety_block_is_a_refusal(self, acompletion, monkeypatch):
        monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-key")
        acompletion.return_value = _resp("", finish="content_filter")
        resp = await GeminiProvider().complete("sys", MSGS)
        assert resp.refused
        assert resp.stop_reason == STOP_REFUSAL

    async def test_vision_goes_through_litellm_with_key(self, acompletion, monkeypatch):
        monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-key")
        acompletion.return_value = _resp("a cat")
        resp = await GeminiProvider().complete_with_vision("sys", MSGS, b"\x89PNG", media_type="image/png")
        kwargs = acompletion.call_args.kwargs
        assert resp.text == "a cat"
        assert kwargs["model"] == "gemini/gemini-2.5-flash"
        assert kwargs["api_key"] == "g-key"
        image_part = kwargs["messages"][-1]["content"][1]
        assert image_part["image_url"]["url"].startswith("data:image/png;base64,")

    def test_models_and_availability(self, monkeypatch):
        provider = GeminiProvider()
        ids = {m.model_id for m in provider.list_models()}
        assert ids == {"gemini/gemini-2.5-flash", "gemini/gemini-2.5-pro"}
        assert all(Capability.TOOLS in m.capabilities for m in provider.list_models())
        assert not provider.is_available()
        monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-key")
        assert provider.is_available()

    def test_pro_model_env_override(self, monkeypatch):
        monkeypatch.setenv("GEMINI_PRO_MODEL", "gemini-3-pro")
        assert "gemini/gemini-3-pro" in {m.model_id for m in GeminiProvider().list_models()}


# --- OpenAI --------------------------------------------------------------------


class TestOpenAI:
    def test_advertises_tools_and_availability(self, monkeypatch):
        provider = OpenAIProvider()
        assert provider.supports(Capability.TOOLS)
        assert not provider.is_available()
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert provider.is_available()

    async def test_complete_with_tools_returns_tool_calls(self, acompletion):
        acompletion.return_value = _resp(None, tool_calls=[_tool_call()], finish="tool_calls")
        resp = await OpenAIProvider().complete_with_tools("sys", MSGS, [CLAUDE_TOOL], model="gpt-4o")
        kwargs = acompletion.call_args.kwargs
        assert kwargs["model"] == "openai/gpt-4o"
        assert kwargs["tools"][0]["function"]["name"] == "search_kb"
        assert resp.provider == "openai"
        assert resp.stop_reason == STOP_TOOL_USE
        assert resp.tool_calls == [ToolCall(id="call_1", name="search_kb", arguments={"q": "x"})]
        assert resp.assistant_message["tool_calls"][0]["id"] == "call_1"

    def test_uses_openai_message_shapes(self):
        provider = OpenAIProvider()
        assert provider.tools_format == "openai"
        assert provider.user_text_message("hi") == {"role": "user", "content": "hi"}
        msgs = provider.tool_result_messages([(ToolCall("c1", "t", {}), "out", False)])
        assert msgs == [{"role": "tool", "tool_call_id": "c1", "content": "out"}]


# --- Ollama --------------------------------------------------------------------


def _httpx_fake(show_capabilities, tags_status=200):
    def get(url, **kwargs):
        return SimpleNamespace(status_code=tags_status)

    def post(url, **kwargs):
        resp = MagicMock()
        resp.json.return_value = {"capabilities": show_capabilities}
        return resp

    return get, post


class TestOllama:
    def test_base_url_prefers_base_url_over_host(self, monkeypatch):
        from realize_core import config

        assert config.ollama_base_url() == "http://localhost:11434"
        monkeypatch.setenv("OLLAMA_HOST", "box:11434")
        assert config.ollama_base_url() == "http://box:11434"
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://primary:1234/")
        assert config.ollama_base_url() == "http://primary:1234"

    async def test_complete_uses_env_model_and_base_url(self, acompletion, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://primary:1234")
        monkeypatch.setenv("OLLAMA_HOST", "http://ignored:1")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
        acompletion.return_value = _resp("local reply")
        resp = await OllamaProvider().complete("sys", MSGS)
        kwargs = acompletion.call_args.kwargs
        assert kwargs["model"] == "ollama_chat/qwen3:8b"
        assert kwargs["api_base"] == "http://primary:1234"
        assert resp.text == "local reply"
        assert resp.provider == "ollama"
        assert resp.cost_usd == 0.0

    def test_tools_capability_from_api_show(self):
        get, post = _httpx_fake(["completion", "tools"])
        with patch("httpx.get", get), patch("httpx.post", post):
            provider = OllamaProvider()
            assert provider.supports(Capability.TOOLS)
            assert provider.supports(Capability.TEXT)

    def test_no_tools_when_model_does_not_list_them(self):
        get, post = _httpx_fake(["completion"])
        with patch("httpx.get", get), patch("httpx.post", post):
            assert not OllamaProvider().supports(Capability.TOOLS)

    def test_probe_failure_means_no_tools_and_is_cached(self):
        get = lambda url, **kw: SimpleNamespace(status_code=200)  # noqa: E731
        post = MagicMock(side_effect=RuntimeError("boom"))
        with patch("httpx.get", get), patch("httpx.post", post):
            provider = OllamaProvider()
            assert not provider.supports(Capability.TOOLS)
            assert not provider.supports(Capability.TOOLS)
        assert post.call_count == 1

    def test_availability_is_cached_for_ttl(self):
        get = MagicMock(return_value=SimpleNamespace(status_code=200))
        with patch("httpx.get", get):
            provider = OllamaProvider()
            assert provider.is_available()
            assert provider.is_available()
            assert get.call_count == 1
            with patch("realize_core.llm.providers.ollama_provider.time.monotonic", return_value=1e9):
                provider.is_available()
            assert get.call_count == 2

    def test_unreachable_server_is_unavailable(self):
        with patch("httpx.get", MagicMock(side_effect=OSError("down"))):
            provider = OllamaProvider()
            assert not provider.is_available()
            assert not provider.supports(Capability.TOOLS)  # no /api/show call when the server is down


# --- Claude --------------------------------------------------------------------


def _block(**fields):
    block = MagicMock()
    for key, value in fields.items():
        setattr(block, key, value)
    block.model_dump = lambda exclude_none=False, _f=fields: dict(_f)
    return block


def _message(content, stop_reason="end_turn"):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        stop_details=None,
        usage=SimpleNamespace(input_tokens=7, output_tokens=3),
    )


@pytest.fixture
def claude_call():
    """Patch the module-level Claude tool call used by ClaudeProvider.complete_with_tools."""
    with patch("realize_core.llm.claude_client.call_claude_with_tools", new_callable=AsyncMock) as mock:
        yield mock


class TestClaude:
    def test_tools_format_and_message_shapes(self):
        provider = ClaudeProvider()
        assert provider.tools_format == "claude"
        assert provider.user_text_message("hi") == {"role": "user", "content": [{"type": "text", "text": "hi"}]}

    def test_tool_result_messages_is_one_user_message(self):
        results = [
            (ToolCall("tu_1", "a", {}), "fine", False),
            (ToolCall("tu_2", "b", {}), "bad", True),
        ]
        msgs = ClaudeProvider().tool_result_messages(results)
        assert msgs == [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": "fine"},
                    {"type": "tool_result", "tool_use_id": "tu_2", "content": "bad", "is_error": True},
                ],
            }
        ]

    async def test_tool_use_response_becomes_tool_calls(self, claude_call):
        text_block = _block(type="text", text="Looking.")
        tool_block = _block(type="tool_use", id="tu_1", name="search_kb", input={"q": "x"})
        claude_call.return_value = _message([text_block, tool_block], stop_reason="tool_use")
        resp = await ClaudeProvider().complete_with_tools("sys", MSGS, [CLAUDE_TOOL])
        assert resp.stop_reason == STOP_TOOL_USE
        assert resp.text == "Looking."
        assert resp.tool_calls == [ToolCall(id="tu_1", name="search_kb", arguments={"q": "x"})]
        assert resp.assistant_message == {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Looking."},
                {"type": "tool_use", "id": "tu_1", "name": "search_kb", "input": {"q": "x"}},
            ],
        }
        assert resp.raw is claude_call.return_value
        assert resp.input_tokens == 7

    @pytest.mark.parametrize(
        ("stop", "expected"),
        [
            ("end_turn", STOP_END),
            ("stop_sequence", STOP_END),
            ("max_tokens", STOP_MAX_TOKENS),
        ],
    )
    async def test_stop_reason_mapping(self, claude_call, stop, expected):
        claude_call.return_value = _message([_block(type="text", text="answer")], stop_reason=stop)
        resp = await ClaudeProvider().complete_with_tools("sys", MSGS, [CLAUDE_TOOL])
        assert resp.stop_reason == expected
        assert resp.ok
        assert resp.tool_calls == []

    async def test_pause_turn_without_text_is_not_an_error(self, claude_call):
        claude_call.return_value = _message([_block(type="server_tool_use", id="s1")], stop_reason="pause_turn")
        resp = await ClaudeProvider().complete_with_tools("sys", MSGS, [CLAUDE_TOOL])
        assert resp.stop_reason == STOP_PAUSE
        assert resp.ok

    async def test_refusal(self, claude_call):
        claude_call.return_value = _message([], stop_reason="refusal")
        resp = await ClaudeProvider().complete_with_tools("sys", MSGS, [CLAUDE_TOOL])
        assert resp.refused
        assert resp.stop_reason == STOP_REFUSAL

    async def test_empty_text_without_tool_calls_is_an_error(self, claude_call):
        claude_call.return_value = _message([_block(type="text", text="  ")])
        resp = await ClaudeProvider().complete_with_tools("sys", MSGS, [CLAUDE_TOOL])
        assert resp.error == EMPTY_ERROR
        assert resp.stop_reason == STOP_ERROR

    async def test_complete_sets_stop_reason_and_maps_empty(self):
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_message([_block(type="text", text="done")]))
        with patch("realize_core.llm.claude_client._get_client", return_value=client):
            resp = await ClaudeProvider().complete("sys", MSGS)
        assert resp.ok
        assert resp.text == "done"
        assert resp.stop_reason == STOP_END

        client.messages.create = AsyncMock(return_value=_message([_block(type="text", text="")]))
        with patch("realize_core.llm.claude_client._get_client", return_value=client):
            resp = await ClaudeProvider().complete("sys", MSGS)
        assert resp.error == EMPTY_ERROR


class TestWorkspaceHeader:
    @pytest.fixture(autouse=True)
    def _fresh_client(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setattr(claude_client, "_client", None)
        monkeypatch.setattr(claude_client, "_client_key", "")
        monkeypatch.setattr(claude_client, "_client_workspace", "")

    def test_header_sent_when_workspace_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_123")
        client = claude_client._get_client()
        assert client.default_headers["anthropic-workspace-id"] == "wrkspc_123"

    def test_no_header_when_unset(self):
        client = claude_client._get_client()
        assert "anthropic-workspace-id" not in client.default_headers

    def test_client_rebuilt_when_workspace_changes(self, monkeypatch):
        first = claude_client._get_client()
        assert claude_client._get_client() is first
        monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_456")
        second = claude_client._get_client()
        assert second is not first
        assert second.default_headers["anthropic-workspace-id"] == "wrkspc_456"


# --- Registry ------------------------------------------------------------------


class _Fake(BaseLLMProvider):
    def __init__(self, name, available=True, caps=(Capability.TEXT,), model_id=None):
        self._name = name
        self._available = available
        self._caps = set(caps)
        self._model_id = model_id or f"{name}-model"

    @property
    def name(self):
        return self._name

    async def complete(self, system_prompt, messages, **kwargs):
        return LLMResponse(text="x", provider=self._name)

    def list_models(self):
        return [ModelInfo(model_id=self._model_id, capabilities=self._caps)]

    def is_available(self):
        return self._available


def _registry(*names):
    reg = ProviderRegistry()
    for name in names:
        reg.register(_Fake(name), {f"{name}_key": f"{name}-model"})
    return reg


ALL = ("claude", "gemini", "openai", "ollama", "litellm")


class TestRegistryFallbackOrder:
    def test_default_order(self):
        assert _registry(*ALL)._resolve_fallback_chain() == list(ALL)

    def test_default_order_ignores_registration_order_and_appends_unknown(self):
        reg = _registry("litellm", "extra", "gemini", "claude")
        assert reg._resolve_fallback_chain() == ["claude", "gemini", "litellm", "extra"]

    def test_llm_primary_goes_first(self, monkeypatch):
        monkeypatch.setenv("LLM_PRIMARY", "openai")
        assert _registry(*ALL)._resolve_fallback_chain() == ["openai", "claude", "gemini", "ollama", "litellm"]

    @pytest.mark.parametrize(
        ("alias", "expected"), [("anthropic", "claude"), ("google", "gemini"), ("google_ai", "gemini")]
    )
    def test_llm_primary_aliases(self, monkeypatch, alias, expected):
        monkeypatch.setenv("LLM_PRIMARY", alias)
        assert _registry(*ALL)._resolve_fallback_chain()[0] == expected

    def test_unknown_primary_is_ignored(self, monkeypatch):
        monkeypatch.setenv("LLM_PRIMARY", "nonsense")
        assert _registry(*ALL)._resolve_fallback_chain() == list(ALL)

    def test_llm_fallback_follows_primary_and_drops_unknown(self, monkeypatch):
        monkeypatch.setenv("LLM_PRIMARY", "claude")
        monkeypatch.setenv("LLM_FALLBACK", "ollama, bogus ,gemini")
        assert _registry(*ALL)._resolve_fallback_chain() == ["claude", "ollama", "gemini"]

    def test_llm_primary_is_not_overridden_by_llm_fallback(self, monkeypatch):
        monkeypatch.setenv("LLM_PRIMARY", "openai")
        monkeypatch.setenv("LLM_FALLBACK", "gemini,ollama")
        assert _registry(*ALL)._resolve_fallback_chain() == ["openai", "gemini", "ollama"]

    def test_llm_fallback_dedupes_primary_and_folds_aliases(self, monkeypatch):
        monkeypatch.setenv("LLM_PRIMARY", "anthropic")
        monkeypatch.setenv("LLM_FALLBACK", "google,claude,google_ai,ollama")
        assert _registry(*ALL)._resolve_fallback_chain() == ["claude", "gemini", "ollama"]

    def test_llm_fallback_without_primary(self, monkeypatch):
        monkeypatch.setenv("LLM_FALLBACK", "ollama,gemini")
        assert _registry(*ALL)._resolve_fallback_chain() == ["ollama", "gemini"]

    def test_llm_fallback_with_no_valid_names_uses_default(self, monkeypatch):
        monkeypatch.setenv("LLM_FALLBACK", "bogus")
        assert _registry(*ALL)._resolve_fallback_chain() == list(ALL)

    def test_public_chain_accessors(self):
        reg = ProviderRegistry()
        reg.register(_Fake("claude", available=False))
        reg.register(_Fake("gemini"))
        reg.set_fallback_chain(["claude", "gemini"])
        assert reg.fallback_chain() == ["claude", "gemini"]
        reg.fallback_chain().append("x")  # a copy
        assert reg.fallback_chain() == ["claude", "gemini"]
        assert reg.primary_provider_name() == "gemini"

    def test_primary_provider_none_when_nothing_available(self):
        reg = ProviderRegistry()
        reg.register(_Fake("claude", available=False))
        reg.set_fallback_chain(["claude"])
        assert reg.primary_provider_name() is None

    def test_auto_register_honours_env(self, monkeypatch):
        monkeypatch.setenv("LLM_FALLBACK", "ollama,claude")
        reg = ProviderRegistry()
        with patch("httpx.get", MagicMock(side_effect=OSError("down"))):
            reg.auto_register()
        assert reg.fallback_chain() == ["ollama", "claude"]


class TestRegistryCapabilities:
    def test_filters_unavailable_and_keeps_chain_order(self):
        reg = ProviderRegistry()
        tools = (Capability.TEXT, Capability.TOOLS)
        reg.register(_Fake("a", caps=tools))
        reg.register(_Fake("b", available=False, caps=tools))
        reg.register(_Fake("c", caps=tools))
        reg.register(_Fake("d", caps=(Capability.TEXT,)))
        reg.set_fallback_chain(["c", "b", "a"])
        assert [p.name for p in reg.providers_with_capability(Capability.TOOLS)] == ["c", "a"]
        assert [p.name for p in reg.providers_with_capability(Capability.TOOLS, available_only=False)] == [
            "c",
            "b",
            "a",
        ]

    def test_resolve_model_id_for_new_keys_uses_provider_models(self):
        reg = ProviderRegistry()
        with patch("httpx.get", MagicMock(side_effect=OSError("down"))):
            reg.auto_register()
        assert reg.resolve_model_id("gpt4o") == "openai/gpt-4o"
        assert reg.resolve_model_id("gemini_pro") == "gemini/gemini-2.5-pro"
        assert reg.resolve_model_id("ollama") == "ollama_chat/llama3.1:8b"
        assert reg.resolve_model_id("no_such_key") is None

    def test_resolve_model_id_keeps_existing_keys(self):
        from realize_core.config import MODELS

        reg = ProviderRegistry()
        assert reg.resolve_model_id("claude_sonnet") == MODELS["claude_sonnet"]
        assert reg.resolve_model_id("gemini_flash") == MODELS["gemini_flash"]

    def test_resolve_model_id_returns_none_when_provider_dropped_the_model(self):
        reg = ProviderRegistry()
        provider = _Fake("p", model_id="old")
        reg.register(provider, {"k": "old"})
        provider._model_id = "new"
        assert reg.resolve_model_id("k") is None
