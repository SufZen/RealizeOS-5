"""Tests for the provider-neutral LLM types, tool-schema converter and LiteLLM adapter."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import litellm  # imported up front: it loads .env, which would re-set keys the fixtures delete
import pytest
from realize_core.llm.base_provider import (
    EMPTY_ERROR,
    REFUSAL_ERROR,
    STOP_END,
    STOP_ERROR,
    STOP_MAX_TOKENS,
    STOP_REFUSAL,
    STOP_TOOL_USE,
    BaseLLMProvider,
    LLMResponse,
    ToolCall,
    empty_or_text,
)
from realize_core.llm.litellm_provider import LiteLLMProvider
from realize_core.tools.base_tool import ToolSchema, convert_tool_schemas

CLAUDE_TOOL = {
    "name": "search_kb",
    "description": "Search the KB",
    "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
}
OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": "search_kb",
        "description": "Search the KB",
        "parameters": CLAUDE_TOOL["input_schema"],
    },
}


def _tc(call_id, name, arguments):
    return SimpleNamespace(id=call_id, type="function", function=SimpleNamespace(name=name, arguments=arguments))


def _resp(content="hi", tool_calls=None, finish="stop", prompt=10, completion=5):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


@pytest.fixture
def acompletion():
    """Patch litellm.acompletion with an AsyncMock (pricing stays real, offline)."""
    mock = AsyncMock()
    with patch.object(litellm, "acompletion", mock):
        yield mock


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("LITELLM_MODEL", "LITELLM_API_BASE", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


MSGS = [{"role": "user", "content": "hello"}]


# --- tool schema conversion ---------------------------------------------------


class TestConvertToolSchemas:
    def test_claude_is_unchanged(self):
        assert convert_tool_schemas([CLAUDE_TOOL], "claude") == [CLAUDE_TOOL]

    def test_openai_conversion(self):
        assert convert_tool_schemas([CLAUDE_TOOL], "openai") == [OPENAI_TOOL]

    def test_openai_passthrough_for_already_converted(self):
        assert convert_tool_schemas([OPENAI_TOOL], "openai") == [OPENAI_TOOL]

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError):
            convert_tool_schemas([CLAUDE_TOOL], "bogus")

    def test_tool_schema_to_openai_format(self):
        schema = ToolSchema(name="search_kb", description="Search the KB", input_schema=CLAUDE_TOOL["input_schema"])
        assert schema.to_openai_format() == OPENAI_TOOL


# --- neutral types and hooks ----------------------------------------------------


class TestNeutralTypes:
    def test_llm_response_defaults_keep_old_constructor_working(self):
        r = LLMResponse(text="x")
        assert r.tool_calls == []
        assert r.stop_reason == STOP_END
        assert r.assistant_message is None
        assert r.ok

    def test_empty_or_text(self):
        assert empty_or_text("hi") == ("hi", None)
        assert empty_or_text("  \n") == ("  \n", EMPTY_ERROR)
        assert empty_or_text(None) == ("", EMPTY_ERROR)

    def test_default_hooks_are_openai_shaped(self):
        p = LiteLLMProvider()
        assert p.tools_format == "openai"
        assert p.user_text_message("yo") == {"role": "user", "content": "yo"}
        out = p.tool_result_messages([(ToolCall("a", "t", {}), "fine", False), (ToolCall("b", "t", {}), "boom", True)])
        assert out == [
            {"role": "tool", "tool_call_id": "a", "content": "fine"},
            {"role": "tool", "tool_call_id": "b", "content": "ERROR: boom"},
        ]

    def test_hooks_live_on_base_class(self):
        assert BaseLLMProvider.tools_format == "openai"
        assert BaseLLMProvider.user_text_message is not None


# --- availability ------------------------------------------------------------------


class TestAvailability:
    def test_unavailable_without_keys_or_base(self):
        assert LiteLLMProvider().is_available() is False

    def test_available_with_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert LiteLLMProvider().is_available() is True

    def test_available_with_api_base_only(self, monkeypatch):
        monkeypatch.setenv("LITELLM_API_BASE", "http://localhost:11434")
        assert LiteLLMProvider().is_available() is True

    def test_env_read_at_call_time(self, monkeypatch):
        p = LiteLLMProvider()
        assert p.is_available() is False
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert p.is_available() is True

    def test_validate_environment_error_means_unavailable(self):
        with patch.object(litellm, "validate_environment", side_effect=RuntimeError("x")):
            assert LiteLLMProvider().is_available() is False

    def test_default_model_from_env(self, monkeypatch):
        assert LiteLLMProvider()._default_model == "gpt-4o-mini"
        monkeypatch.setenv("LITELLM_MODEL", "ollama/llama3")
        assert LiteLLMProvider()._default_model == "ollama/llama3"
        assert LiteLLMProvider(default_model="gpt-4o")._default_model == "gpt-4o"


# --- _acompletion_kwargs ------------------------------------------------------------


class TestAcompletionKwargs:
    def test_system_prepended_and_temperature_optional(self):
        kw = LiteLLMProvider()._acompletion_kwargs("sys", MSGS, "m", 100, None, 9.0, foo="bar")
        assert kw["messages"][0] == {"role": "system", "content": "sys"}
        assert kw["messages"][1:] == MSGS
        assert "temperature" not in kw
        assert "api_base" not in kw
        assert kw["foo"] == "bar"
        assert kw["timeout"] == 9.0

    def test_api_base_and_temperature_included(self, monkeypatch):
        monkeypatch.setenv("LITELLM_API_BASE", "http://host:1")
        kw = LiteLLMProvider()._acompletion_kwargs("", MSGS, "m", 100, 0.2)
        assert kw["api_base"] == "http://host:1"
        assert kw["temperature"] == 0.2
        assert kw["messages"] == MSGS


# --- complete ---------------------------------------------------------------------------


class TestComplete:
    @pytest.mark.asyncio
    async def test_success(self, acompletion):
        acompletion.return_value = _resp("hello there")
        r = await LiteLLMProvider().complete("sys", MSGS)
        assert r.ok
        assert r.text == "hello there"
        assert r.stop_reason == STOP_END
        assert r.input_tokens == 10
        assert r.output_tokens == 5

    @pytest.mark.asyncio
    async def test_api_base_passed_to_acompletion(self, acompletion, monkeypatch):
        monkeypatch.setenv("LITELLM_API_BASE", "http://host:1")
        acompletion.return_value = _resp("x")
        await LiteLLMProvider().complete("", MSGS)
        assert acompletion.call_args.kwargs["api_base"] == "http://host:1"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("content", ["", "   ", None])
    async def test_empty_text_is_error(self, acompletion, content):
        acompletion.return_value = _resp(content)
        r = await LiteLLMProvider().complete("", MSGS)
        assert r.error == EMPTY_ERROR
        assert not r.ok
        assert r.stop_reason == STOP_ERROR

    @pytest.mark.asyncio
    async def test_content_filter_is_refusal(self, acompletion):
        acompletion.return_value = _resp("I can't", finish="content_filter")
        r = await LiteLLMProvider().complete("", MSGS)
        assert r.refused
        assert r.error == REFUSAL_ERROR
        assert r.stop_reason == STOP_REFUSAL

    @pytest.mark.asyncio
    async def test_length_maps_to_max_tokens(self, acompletion):
        acompletion.return_value = _resp("cut off", finish="length")
        r = await LiteLLMProvider().complete("", MSGS)
        assert r.ok
        assert r.stop_reason == STOP_MAX_TOKENS

    @pytest.mark.asyncio
    async def test_exception_returns_error_response(self, acompletion):
        acompletion.side_effect = RuntimeError("down")
        r = await LiteLLMProvider().complete("", MSGS)
        assert r.error == "down"
        assert r.stop_reason == STOP_ERROR

    @pytest.mark.asyncio
    async def test_response_schema_native(self, acompletion):
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        acompletion.return_value = _resp('{"a": "b"}')
        with patch.object(litellm, "supports_response_schema", return_value=True):
            r = await LiteLLMProvider().complete("sys", MSGS, response_schema=schema)
        assert r.ok
        kw = acompletion.call_args.kwargs
        assert kw["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": schema, "strict": False},
        }
        assert kw["messages"][0]["content"] == "sys"

    @pytest.mark.asyncio
    async def test_response_schema_fallback_json_object(self, acompletion):
        schema = {"type": "object"}
        acompletion.return_value = _resp("{}")
        with patch.object(litellm, "supports_response_schema", return_value=False):
            await LiteLLMProvider().complete("sys", MSGS, response_schema=schema)
        kw = acompletion.call_args.kwargs
        assert kw["response_format"] == {"type": "json_object"}
        assert "Respond ONLY with JSON matching this schema: " + json.dumps(schema) in kw["messages"][0]["content"]
        assert kw["messages"][0]["content"].startswith("sys")

    @pytest.mark.asyncio
    async def test_response_schema_support_check_error_falls_back(self, acompletion):
        acompletion.return_value = _resp("{}")
        with patch.object(litellm, "supports_response_schema", side_effect=RuntimeError("?")):
            await LiteLLMProvider().complete("", MSGS, response_schema={"type": "object"})
        assert acompletion.call_args.kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_no_response_format_without_schema(self, acompletion):
        acompletion.return_value = _resp("x")
        await LiteLLMProvider().complete("", MSGS)
        assert "response_format" not in acompletion.call_args.kwargs


# --- complete_with_tools -----------------------------------------------------------------


class TestCompleteWithTools:
    @pytest.mark.asyncio
    async def test_tools_converted_to_openai(self, acompletion):
        acompletion.return_value = _resp("ok")
        await LiteLLMProvider().complete_with_tools("sys", MSGS, [CLAUDE_TOOL])
        assert acompletion.call_args.kwargs["tools"] == [OPENAI_TOOL]

    @pytest.mark.asyncio
    async def test_tool_calls_parsed(self, acompletion):
        acompletion.return_value = _resp(
            None,
            tool_calls=[_tc("c1", "search_kb", '{"q": "x"}'), _tc("c2", "other", "{}")],
            finish="tool_calls",
        )
        r = await LiteLLMProvider().complete_with_tools("", MSGS, [CLAUDE_TOOL])
        assert r.ok
        assert r.stop_reason == STOP_TOOL_USE
        assert r.tool_calls == [ToolCall("c1", "search_kb", {"q": "x"}), ToolCall("c2", "other", {})]
        assert r.assistant_message == {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "search_kb", "arguments": '{"q": "x"}'}},
                {"id": "c2", "type": "function", "function": {"name": "other", "arguments": "{}"}},
            ],
        }

    @pytest.mark.asyncio
    async def test_bad_json_arguments_become_empty_dict(self, acompletion, caplog):
        acompletion.return_value = _resp(None, tool_calls=[_tc("c1", "search_kb", "{not json")], finish="tool_calls")
        with caplog.at_level("WARNING"):
            r = await LiteLLMProvider().complete_with_tools("", MSGS, [CLAUDE_TOOL])
        assert r.tool_calls == [ToolCall("c1", "search_kb", {})]
        assert "invalid JSON" in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("finish", "expected"),
        [
            ("stop", STOP_END),
            ("tool_calls", STOP_TOOL_USE),
            ("function_call", STOP_TOOL_USE),
            ("length", STOP_MAX_TOKENS),
            ("content_filter", STOP_REFUSAL),
        ],
    )
    async def test_finish_reason_mapping(self, acompletion, finish, expected):
        acompletion.return_value = _resp("text", finish=finish)
        r = await LiteLLMProvider().complete_with_tools("", MSGS, [CLAUDE_TOOL])
        assert r.stop_reason == expected

    @pytest.mark.asyncio
    async def test_content_filter_sets_refusal_error(self, acompletion):
        acompletion.return_value = _resp("no", finish="content_filter")
        r = await LiteLLMProvider().complete_with_tools("", MSGS, [CLAUDE_TOOL])
        assert r.refused

    @pytest.mark.asyncio
    async def test_text_only_turn_has_no_tool_calls_key(self, acompletion):
        acompletion.return_value = _resp("done")
        r = await LiteLLMProvider().complete_with_tools("", MSGS, [CLAUDE_TOOL])
        assert r.assistant_message == {"role": "assistant", "content": "done"}
        assert r.tool_calls == []

    @pytest.mark.asyncio
    async def test_empty_without_tool_calls_is_error(self, acompletion):
        acompletion.return_value = _resp("")
        r = await LiteLLMProvider().complete_with_tools("", MSGS, [CLAUDE_TOOL])
        assert r.error == EMPTY_ERROR

    @pytest.mark.asyncio
    async def test_tool_only_turn_is_not_empty_error(self, acompletion):
        acompletion.return_value = _resp("", tool_calls=[_tc("c1", "t", "{}")], finish="tool_calls")
        r = await LiteLLMProvider().complete_with_tools("", MSGS, [CLAUDE_TOOL])
        assert r.ok

    @pytest.mark.asyncio
    async def test_exception_returns_error(self, acompletion):
        acompletion.side_effect = RuntimeError("boom")
        r = await LiteLLMProvider().complete_with_tools("", MSGS, [CLAUDE_TOOL])
        assert r.error == "boom"
        assert r.text == ""
        assert r.stop_reason == STOP_ERROR
