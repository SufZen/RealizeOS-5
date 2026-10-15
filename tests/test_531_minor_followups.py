"""5.31 follow-up #7: the cheap deferred minors.

- Ollama tool/vision support is checked per model when a tier pins one.
- A pause turn without an assistant message does not resend the same conversation.
- A failed tool loop does not emit its own error text before the routed answer.
- LiteLLM keeps non-ASCII tool arguments readable in history.
- A KB search never wipes vectors written under another KB_EMBED_MODEL.
- The niqqud regex is written with escapes.
- The router warns once when LLM_MODEL_<TIER> pins an unregistered/unavailable provider.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import litellm
import pytest
from realize_core.llm.base_provider import STOP_END, STOP_PAUSE, BaseLLMProvider, Capability, LLMResponse, ModelInfo
from realize_core.llm.registry import ProviderRegistry

# ---------------------------------------------------------------------------
# Ollama: per-model capabilities
# ---------------------------------------------------------------------------


def _ollama_server(caps_by_model: dict[str, list[str]]):
    """httpx patches: /api/tags answers, /api/show lists ``caps_by_model[model]``."""

    def show(url, json=None, **kwargs):
        resp = MagicMock()
        resp.json.return_value = {"capabilities": caps_by_model.get(json["model"], ["completion"])}
        return resp

    return (
        patch("httpx.get", MagicMock(return_value=SimpleNamespace(status_code=200))),
        patch("httpx.post", MagicMock(side_effect=show)),
    )


def test_ollama_supports_model_probes_that_model(monkeypatch):
    from realize_core.llm.providers.ollama_provider import OllamaProvider

    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")
    get, post = _ollama_server({"llama3.1:8b": ["completion", "tools"], "llava:7b": ["completion", "vision"]})
    with get, post:
        provider = OllamaProvider()
        assert provider.supports(Capability.TOOLS)  # the default model has tools
        assert provider.supports_model("ollama_chat/llama3.1:8b", Capability.TOOLS)
        assert not provider.supports_model("ollama_chat/llava:7b", Capability.TOOLS)
        assert provider.supports_model("ollama/llava:7b", Capability.VISION)
        assert provider.supports_model("llava:7b", Capability.TEXT)


def test_base_supports_model_defaults_to_the_provider_capability():
    class P(BaseLLMProvider):
        name = "p"

        async def complete(self, *a, **k):
            return LLMResponse(text="")

        def list_models(self):
            return [ModelInfo(model_id="m", capabilities={Capability.TEXT, Capability.TOOLS})]

    assert P().supports_model("anything", Capability.TOOLS)
    assert not P().supports_model("anything", Capability.VISION)


class _Fake(BaseLLMProvider):
    def __init__(self, name, model):
        self._name = name
        self._model = model
        self.calls: list[str | None] = []
        self.tier_models = {}

    @property
    def name(self):
        return self._name

    async def complete(self, system_prompt, messages, **kwargs):
        return LLMResponse(text="plain", provider=self._name)

    async def complete_with_tools(self, system_prompt, messages, tools, model=None, **kwargs):
        self.calls.append(model)
        return LLMResponse(text=f"{self._name}:{model}", provider=self._name, stop_reason=STOP_END)

    def list_models(self):
        return [ModelInfo(model_id=self._model, capabilities={Capability.TEXT, Capability.TOOLS})]

    def default_model_id(self):
        return self._model


class _FakeOllama(_Fake):
    """Tools on its default model only (like a real Ollama install with one tool model)."""

    def supports_model(self, model_id, capability):
        return capability == Capability.TEXT or model_id == self._model


@pytest.fixture
def ollama_and_gemini(monkeypatch):
    import realize_core.base_handler as bh
    import realize_core.llm.registry as llm_registry

    ollama = _FakeOllama("ollama", "ollama_chat/llama3.1:8b")
    gemini = _Fake("gemini", "gemini/gemini-2.5-pro")
    reg = ProviderRegistry()
    reg.register(gemini, {"fk_pro": "gemini/gemini-2.5-pro"})
    reg.register(ollama, {"ollama": "ollama_chat/llama3.1:8b"})
    reg.set_fallback_chain(["gemini", "ollama"])
    monkeypatch.setattr(llm_registry, "get_registry", lambda: reg)
    tools = [{"name": "kb_search", "description": "s", "input_schema": {"type": "object", "properties": {}}}]
    monkeypatch.setattr(bh, "agent_tool_schemas", lambda *_a, **_k: tools)
    return ollama, gemini


async def _answer(message):
    from realize_core.base_handler import _answer_with_tools

    return await _answer_with_tools("p", [{"role": "user", "content": message}], "agent", None, {}, message=message)


async def test_pinned_ollama_model_without_tools_is_not_used_for_the_tool_loop(ollama_and_gemini, monkeypatch):
    ollama, gemini = ollama_and_gemini
    monkeypatch.setenv("LLM_MODEL_STANDARD", "ollama/gemma2:2b")  # a model without tool support

    answer, lost = await _answer("good morning team")

    assert lost is False
    assert "ollama_chat/gemma2:2b" not in ollama.calls
    assert gemini.calls == ["gemini/gemini-2.5-pro"]


async def test_pinned_ollama_model_with_tools_is_used(ollama_and_gemini, monkeypatch):
    ollama, gemini = ollama_and_gemini
    monkeypatch.setenv("LLM_MODEL_STANDARD", "ollama/llama3.1:8b")

    answer, _ = await _answer("good morning team")

    assert answer == "ollama:ollama_chat/llama3.1:8b"
    assert gemini.calls == []


# ---------------------------------------------------------------------------
# Tool loop: pause without assistant_message; single final text event on error
# ---------------------------------------------------------------------------


class _Scripted:
    name = "scripted"
    tools_format = "openai"

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests: list[list[dict]] = []

    def is_available(self):
        return True

    def user_text_message(self, text):
        return {"role": "user", "content": text}

    def tool_result_messages(self, results):
        return []

    async def complete_with_tools(self, system_prompt, messages, tools, model=None, max_tokens=4096):
        self.requests.append([dict(m) for m in messages])
        return self._responses.pop(0)


@pytest.fixture
def no_limits(monkeypatch):
    from realize_core.llm import router

    monkeypatch.setattr(router, "_check_rate_limit", lambda: True)
    monkeypatch.setattr(router, "_check_cost_limit", lambda: True)


async def _loop(provider):
    from realize_core.agents.tool_loop import run_tool_loop

    events: list[dict] = []
    tools = [{"name": "t", "description": "t", "input_schema": {"type": "object"}}]
    result = await run_tool_loop(
        "s", [{"role": "user", "content": "q"}], tools, registry=MagicMock(), provider=provider, emit=events.append
    )
    return result, events


async def test_pause_without_assistant_message_appends_the_text(no_limits):
    provider = _Scripted(
        LLMResponse(text="thinking so far", stop_reason=STOP_PAUSE, assistant_message=None),
        LLMResponse(text="final", stop_reason=STOP_END),
    )

    result, _ = await _loop(provider)

    assert result.text == "final"
    second = provider.requests[1]
    assert second != provider.requests[0], "the same conversation was sent again"
    assert second[-1] == {"role": "assistant", "content": "thinking so far"}


async def test_pause_without_message_or_text_ends_the_loop(no_limits):
    provider = _Scripted(LLMResponse(text="", stop_reason=STOP_PAUSE, assistant_message=None))

    result, _ = await _loop(provider)

    assert len(provider.requests) == 1
    assert result.stop_reason == STOP_END


async def test_failed_loop_emits_no_text_event(no_limits):
    provider = _Scripted(LLMResponse(text="Sorry, the AI service is down", error="boom"))

    result, events = await _loop(provider)

    assert result.stop_reason == "error"
    assert [e for e in events if e["type"] == "text"] == []


# ---------------------------------------------------------------------------
# LiteLLM: readable non-ASCII tool arguments
# ---------------------------------------------------------------------------


async def test_litellm_tool_arguments_keep_hebrew_readable(monkeypatch):
    from realize_core.llm.litellm_provider import LiteLLMProvider

    monkeypatch.setenv("LITELLM_API_BASE", "http://127.0.0.1:4000")
    args = {"query": "תקציב"}
    fn = SimpleNamespace(name="kb_search", arguments=json.dumps(args))
    message = SimpleNamespace(content=None, tool_calls=[SimpleNamespace(id="c1", type="function", function=fn)])
    reply = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )
    tools = [{"type": "function", "function": {"name": "kb_search", "parameters": {"type": "object"}}}]
    with patch.object(litellm, "acompletion", AsyncMock(return_value=reply)):
        response = await LiteLLMProvider(default_model="openai/x").complete_with_tools(
            "s", [{"role": "user", "content": "q"}], tools
        )

    stored = response.assistant_message["tool_calls"][0]["function"]["arguments"]
    assert "תקציב" in stored
    assert json.loads(stored) == args


# ---------------------------------------------------------------------------
# KB: a search does not touch vectors from another embedding model
# ---------------------------------------------------------------------------


def test_search_does_not_wipe_vectors_of_another_model(tmp_path, monkeypatch):
    from realize_core.kb import indexer

    db_path = tmp_path / "kb_index.db"
    monkeypatch.setenv("KB_EMBED_MODEL", "model-a")
    indexer._init_index_db(db_path)
    indexer._sync_embed_model(db_path)
    conn = indexer._get_conn(db_path)
    conn.execute(
        "INSERT INTO kb_files (path, system_key, content, embedding) VALUES ('a.md', 's', 'budget', X'0000803F')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("KB_EMBED_MODEL", "model-b")  # another process, another model
    used_vectors: list[bool] = []
    monkeypatch.setattr(indexer, "_embed_text", lambda text: b"\x00\x00\x80?")
    monkeypatch.setattr(indexer, "_vector_search", lambda *a, **k: used_vectors.append(True) or [])
    indexer.semantic_search("budget", db_path=db_path)

    conn = indexer._get_conn(db_path)
    try:
        assert conn.execute("SELECT embedding FROM kb_files").fetchone()[0] is not None
        assert conn.execute("SELECT value FROM kb_meta WHERE key = 'embed_model'").fetchone()[0] == "model-a"
    finally:
        conn.close()
    assert used_vectors == [], "vectors from another model were compared with this model's query"


def test_index_run_still_clears_vectors_of_another_model(tmp_path, monkeypatch):
    from realize_core.kb import indexer

    monkeypatch.setattr(indexer, "_get_embedder", lambda: None)
    kb_dir = tmp_path / "systems" / "acme" / "B-brain"
    kb_dir.mkdir(parents=True)
    (kb_dir / "a.md").write_text("# A\nbudget", encoding="utf-8")
    db_path = tmp_path / "kb_index.db"
    monkeypatch.setenv("KB_EMBED_MODEL", "model-a")
    assert indexer.index_kb_files(str(tmp_path), db_path=db_path) == 1
    conn = indexer._get_conn(db_path)
    conn.execute("UPDATE kb_files SET embedding = X'0000803F'")
    conn.commit()
    conn.close()

    monkeypatch.setenv("KB_EMBED_MODEL", "model-b")
    indexer.index_kb_files(str(tmp_path), db_path=db_path)

    conn = indexer._get_conn(db_path)
    try:
        assert [r[0] for r in conn.execute("SELECT embedding FROM kb_files")] == [None]
        assert conn.execute("SELECT value FROM kb_meta WHERE key = 'embed_model'").fetchone()[0] == "model-b"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# fts: escapes, not literal combining marks
# ---------------------------------------------------------------------------


def test_niqqud_regex_source_is_ascii():
    from realize_core.utils import fts

    source = Path(fts.__file__).read_text(encoding="utf-8")
    assert not [c for c in source if 0x0591 <= ord(c) <= 0x05C7], "literal combining marks in fts.py"
    assert fts._HEBREW_MARKS.sub("", "שָׁלוֹם") == "שלום"


# ---------------------------------------------------------------------------
# Router: warn once about a tier pinned to a missing provider
# ---------------------------------------------------------------------------


def test_tier_pinned_to_unregistered_provider_warns_once(monkeypatch, caplog):
    from realize_core.llm import router

    reg = ProviderRegistry()
    reg.register(_Fake("gemini", "gemini/gemini-2.5-flash"), {"fk": "gemini/gemini-2.5-flash"})
    monkeypatch.setattr(router, "_warned_tier_pins", set())
    monkeypatch.setenv("LLM_MODEL_FAST", "mistral/mistral-small-latest")  # -> the litellm provider, not registered

    with caplog.at_level(logging.WARNING, logger="realize_core.llm.router"):
        router._resolve_tier(reg, "fast")
        router._resolve_tier(reg, "fast")

    warnings = [r for r in caplog.records if "LLM_MODEL_FAST" in r.getMessage()]
    assert len(warnings) == 1
    assert "litellm" in warnings[0].getMessage()


def test_tier_pinned_to_unavailable_provider_warns(monkeypatch, caplog):
    from realize_core.llm import router

    class Down(_Fake):
        def is_available(self):
            return False

    reg = ProviderRegistry()
    reg.register(Down("openai", "openai/gpt-4o"), {"fk": "openai/gpt-4o"})
    monkeypatch.setattr(router, "_warned_tier_pins", set())
    monkeypatch.setenv("LLM_MODEL_DEEP", "openai/gpt-4o")

    with caplog.at_level(logging.WARNING, logger="realize_core.llm.router"):
        router._resolve_tier(reg, "deep")

    assert any("LLM_MODEL_DEEP" in r.getMessage() and "not available" in r.getMessage() for r in caplog.records)


def test_tier_pinned_to_available_provider_is_quiet(monkeypatch, caplog):
    from realize_core.llm import router

    reg = ProviderRegistry()
    reg.register(_Fake("openai", "openai/gpt-4o"), {"fk": "openai/gpt-4o"})
    monkeypatch.setattr(router, "_warned_tier_pins", set())
    monkeypatch.setenv("LLM_MODEL_DEEP", "openai/gpt-4o")

    with caplog.at_level(logging.WARNING, logger="realize_core.llm.router"):
        router._resolve_tier(reg, "deep")

    assert not [r for r in caplog.records if "LLM_MODEL_DEEP" in r.getMessage()]
