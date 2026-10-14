"""A scripted LLM behind the REAL provider adapters, one wire shape at a time.

``install_fake_llm(monkeypatch, shape)`` registers only that shape's real
provider in a fresh registry (``LLM_PRIMARY`` set to it) and mocks the
transport underneath it:

- ``anthropic``: ``ClaudeProvider``; the anthropic client returns real
  ``anthropic.types.Message`` objects (content blocks, ``tool_use``).
- ``openai`` / ``gemini`` / ``ollama``: ``OpenAIProvider`` / ``GeminiProvider`` /
  ``OllamaProvider``; ``litellm.acompletion`` returns OpenAI-shaped choices
  (``tool_calls``, ``finish_reason``). Ollama's ``/api/tags`` and ``/api/show``
  probes are answered too, with or without the "tools" capability.

Conversations are scripted shape-agnostically and consumed in call order::

    fake.script(text("Checking."), tool("kb_search", {"q": "budget"}), text("final [S1]"))

A transport that should not be used (the anthropic client under a LiteLLM
shape and vice versa) fails the test, so nothing can reach a real API.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import litellm  # loads .env once, before the installer sets or clears keys
from anthropic.types import Message

SHAPES = ("anthropic", "openai", "gemini", "ollama")

#: Shape -> registered provider name.
PROVIDER_NAMES = {"anthropic": "claude", "openai": "openai", "gemini": "gemini", "ollama": "ollama"}

_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GOOGLE_AI_API_KEY"}
_CLEARED_ENV = (
    "LLM_FALLBACK",
    "LLM_MODEL_FAST",
    "LLM_MODEL_STANDARD",
    "LLM_MODEL_DEEP",
    "LITELLM_MODEL",
    "LITELLM_API_BASE",
    "ANTHROPIC_WORKSPACE_ID",
)
OLLAMA_BASE = "http://ollama.test:11434"
OLLAMA_MODEL = "qwen3:8b"


@dataclass(frozen=True)
class Turn:
    """One scripted model turn."""

    text: str = ""
    tool: tuple[str, dict] | None = None
    outcome: str = "answer"  # "answer" | "refusal" (safety block) | "empty"


def text(value: str) -> Turn:
    """A plain answer."""
    return Turn(text=value)


def tool(name: str, args: dict | None = None, value: str = "") -> Turn:
    """A tool call (optionally with text before it)."""
    return Turn(text=value, tool=(name, args or {}))


def refusal() -> Turn:
    """The model's safety system blocked the answer (Gemini SAFETY, OpenAI content_filter, Claude refusal)."""
    return Turn(outcome="refusal")


def empty() -> Turn:
    """The model returned nothing at all."""
    return Turn(outcome="empty")


def _claude_message(turn: Turn, call_id: str) -> Message:
    content: list[dict] = []
    stop = "end_turn"
    if turn.outcome == "refusal":
        stop = "refusal"
    elif turn.outcome == "answer":
        if turn.text:
            content.append({"type": "text", "text": turn.text})
        if turn.tool:
            content.append({"type": "tool_use", "id": call_id, "name": turn.tool[0], "input": turn.tool[1]})
            stop = "tool_use"
    return Message.model_validate(
        {
            "id": "msg_fake",
            "type": "message",
            "role": "assistant",
            "model": "claude-fake",
            "content": content,
            "stop_reason": stop,
            "stop_sequence": None,
            "usage": {"input_tokens": 5, "output_tokens": 5},
        }
    )


def _litellm_response(turn: Turn, call_id: str) -> SimpleNamespace:
    tool_calls = None
    finish = "stop"
    content: str | None = turn.text or None
    if turn.outcome == "refusal":
        content, finish = None, "content_filter"  # how LiteLLM reports a Gemini SAFETY block
    elif turn.outcome == "empty":
        content = ""
    elif turn.tool:
        fn = SimpleNamespace(name=turn.tool[0], arguments=json.dumps(turn.tool[1]))
        tool_calls = [SimpleNamespace(id=call_id, type="function", function=fn)]
        finish = "tool_calls"
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5),
    )


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(
        part.get("text", "") for part in content or [] if isinstance(part, dict) and part.get("type") == "text"
    )


class FakeLLM:
    """The scripted model behind one real provider adapter."""

    def __init__(self, shape: str, provider: Any):
        self.shape = shape
        self.name = PROVIDER_NAMES[shape]
        self.provider = provider
        self.requests: list[dict] = []
        self._turns: list[Turn] = []

    def script(self, *turns: Turn) -> FakeLLM:
        """Queue turns; each model call consumes the next one."""
        self._turns.extend(turns)
        return self

    @property
    def unused(self) -> list[Turn]:
        return list(self._turns)

    def _next(self, kwargs: dict) -> tuple[Turn, str]:
        self.requests.append(copy.deepcopy(kwargs))
        if not self._turns:
            raise AssertionError(f"unscripted {self.shape} call #{len(self.requests)}")
        return self._turns.pop(0), f"call_{len(self.requests)}"

    async def _anthropic(self, **kwargs) -> Message:
        return _claude_message(*self._next(kwargs))

    async def _litellm(self, **kwargs) -> SimpleNamespace:
        return _litellm_response(*self._next(kwargs))

    # Views over the recorded requests, the same for every shape.

    def system_prompt(self, index: int = -1) -> str:
        request = self.requests[index]
        if "system" in request:  # anthropic
            return _text_of(request["system"])
        return "\n".join(_text_of(m["content"]) for m in request["messages"] if m["role"] == "system")

    def user_text(self, index: int = -1) -> str:
        """Text of the last user message of a request."""
        users = [m for m in self.requests[index]["messages"] if m["role"] == "user"]
        return _text_of(users[-1]["content"]) if users else ""

    def has_image(self, index: int = -1) -> bool:
        last = self.requests[index]["messages"][-1]["content"]
        return isinstance(last, list) and any(p.get("type") in ("image", "image_url") for p in last)


def _must_not_call(transport: str):
    async def _fail(*_a, **_k):
        raise AssertionError(f"{transport} must not be called for this provider")

    return _fail


def install_fake_llm(monkeypatch, shape: str, *, ollama_tools: bool = True) -> FakeLLM:
    """Make ``shape``'s real provider the only LLM, answering from a script.

    Everything is undone by ``monkeypatch`` (environment, registry singleton,
    transports, Ollama probes, router limits).
    """
    from realize_core import config
    from realize_core.llm import claude_client, router
    from realize_core.llm import registry as registry_mod
    from realize_core.llm.providers import gemini_provider, ollama_provider, openai_provider
    from realize_core.llm.providers.claude_provider import ClaudeProvider

    if shape not in SHAPES:
        raise ValueError(f"unknown shape {shape!r}; expected one of {SHAPES}")
    for var in _CLEARED_ENV:
        monkeypatch.delenv(var, raising=False)
    name = PROVIDER_NAMES[shape]
    monkeypatch.setenv("LLM_PRIMARY", name)
    if shape in _KEYS:
        monkeypatch.setenv(_KEYS[shape], "fake-key-for-tests")
    monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA_BASE)
    monkeypatch.setenv("OLLAMA_MODEL", OLLAMA_MODEL)

    if shape == "anthropic":
        provider = ClaudeProvider()
        keys = {"claude_sonnet": config.MODELS["claude_sonnet"], "claude_opus": config.MODELS["claude_opus"]}
    elif shape == "openai":
        provider, keys = openai_provider.OpenAIProvider(), openai_provider.model_keys()
    elif shape == "gemini":
        provider, keys = gemini_provider.GeminiProvider(), gemini_provider.model_keys()
    else:
        capabilities = ["completion", "vision"] + (["tools"] if ollama_tools else [])

        def _get(url, **_kw):
            assert url == f"{OLLAMA_BASE}/api/tags", url
            return SimpleNamespace(status_code=200)

        def _post(url, **_kw):
            assert url == f"{OLLAMA_BASE}/api/show", url
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"capabilities": capabilities})

        monkeypatch.setattr(ollama_provider, "httpx", SimpleNamespace(get=_get, post=_post))
        provider, keys = ollama_provider.OllamaProvider(), ollama_provider.model_keys()

    fake = FakeLLM(shape, provider)
    client = MagicMock()
    if shape == "anthropic":
        client.messages.create = AsyncMock(side_effect=fake._anthropic)
        monkeypatch.setattr(litellm, "acompletion", _must_not_call("litellm.acompletion"))
    else:
        client.messages.create = AsyncMock(side_effect=_must_not_call("the anthropic client"))
        monkeypatch.setattr(litellm, "acompletion", AsyncMock(side_effect=fake._litellm))
    monkeypatch.setattr(claude_client, "_get_client", lambda *_a, **_k: client)
    monkeypatch.setattr(litellm, "completion_cost", lambda *_a, **_k: 0.0)

    registry = registry_mod.ProviderRegistry()
    registry.register(provider, keys)
    registry.set_fallback_chain([name])
    monkeypatch.setattr(registry_mod, "_registry", registry)
    monkeypatch.setattr(router, "_check_rate_limit", lambda: True)
    monkeypatch.setattr(router, "_check_cost_limit", lambda: True)
    return fake
