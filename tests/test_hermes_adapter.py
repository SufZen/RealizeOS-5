"""
Tests for the Hermes Runtime Adapter.

Hermetic: no real network. We drive ``httpx.AsyncClient`` through a custom
``MockTransport`` so health_check / invoke exercise the real adapter code paths
against canned responses (and simulated transport errors).
"""

import json

import pytest

httpx = pytest.importorskip("httpx")

from realize_core.runtimes.contract import (  # noqa: E402
    AgentRuntime,
    CapabilitySet,
    Context,
    MissionStep,
)
from realize_core.runtimes.events import (  # noqa: E402
    ErrorEvent,
    FinalResultEvent,
    ProgressEvent,
    TextEvent,
)
from realize_core.runtimes.hermes import HermesAdapter  # noqa: E402

BASE_URL = "http://hermes.test:8642/v1"


def _make_step() -> MissionStep:
    return MissionStep(
        step_id="s1",
        mission_id="m1",
        description="Say hello",
        inputs={"prompt": "Hello Hermes"},
    )


def _sse(*chunks: str) -> bytes:
    """Build an OpenAI-style SSE body from content chunks."""
    lines = []
    for c in chunks:
        payload = {"choices": [{"delta": {"content": c}}]}
        lines.append(f"data: {json.dumps(payload)}")
    lines.append("data: [DONE]")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _patch_transport(monkeypatch, handler):
    """Patch httpx.AsyncClient so it routes through a MockTransport(handler)."""
    real_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


# ─── Structural conformance ───────────────────────────────────────────────────


def test_adapter_satisfies_protocol():
    adapter = HermesAdapter(base_url=BASE_URL)
    assert isinstance(adapter, AgentRuntime)
    assert isinstance(adapter.capabilities(), CapabilitySet)
    assert adapter.runtime_id == "hermes"


def test_from_config_resolves_env_secret(monkeypatch):
    monkeypatch.setenv("HERMES_TEST_KEY", "sekret")
    adapter = HermesAdapter.from_config({"base_url": BASE_URL, "api_key": "${HERMES_TEST_KEY}", "model": "hermes-x"})
    assert adapter.api_key == "sekret"
    assert adapter.model == "hermes-x"
    assert adapter.base_url == BASE_URL  # trailing-slash safe


# ─── health_check ─────────────────────────────────────────────────────────────


async def test_health_check_healthy(monkeypatch):
    def handler(request):
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json={"data": [{"id": "hermes-3"}]})

    _patch_transport(monkeypatch, handler)

    adapter = HermesAdapter(base_url=BASE_URL)
    status = await adapter.health_check()
    assert status.ready is True
    assert status.runtime_version == "hermes-3"


async def test_health_check_offline_on_connection_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    _patch_transport(monkeypatch, handler)

    adapter = HermesAdapter(base_url=BASE_URL)
    status = await adapter.health_check()
    assert status.ready is False
    assert status.error  # populated, not raised


async def test_health_check_offline_on_non_2xx(monkeypatch):
    def handler(request):
        return httpx.Response(503, text="unavailable")

    _patch_transport(monkeypatch, handler)

    adapter = HermesAdapter(base_url=BASE_URL)
    status = await adapter.health_check()
    assert status.ready is False


# ─── invoke ───────────────────────────────────────────────────────────────────


async def test_invoke_streams_text_and_final(monkeypatch):
    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content)
        assert body["stream"] is True
        return httpx.Response(200, content=_sse("Hel", "lo!"))

    _patch_transport(monkeypatch, handler)

    adapter = HermesAdapter(base_url=BASE_URL)
    events = [e async for e in adapter.invoke(_make_step(), Context())]

    assert isinstance(events[0], ProgressEvent)
    texts = [e for e in events if isinstance(e, TextEvent)]
    assert len(texts) >= 1
    assert "".join(t.delta for t in texts) == "Hello!"
    assert isinstance(events[-1], FinalResultEvent)
    assert events[-1].status == "success"
    assert events[-1].output["text"] == "Hello!"


async def test_invoke_yields_error_on_transport_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("boom")

    _patch_transport(monkeypatch, handler)

    adapter = HermesAdapter(base_url=BASE_URL)
    events = [e async for e in adapter.invoke(_make_step(), Context())]

    assert isinstance(events[0], ProgressEvent)
    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].error_type == "upstream"


async def test_invoke_yields_error_on_http_500(monkeypatch):
    def handler(request):
        return httpx.Response(500, text="server error")

    _patch_transport(monkeypatch, handler)

    adapter = HermesAdapter(base_url=BASE_URL)
    events = [e async for e in adapter.invoke(_make_step(), Context())]

    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].retryable is True


async def test_invoke_without_base_url_errors():
    adapter = HermesAdapter(base_url="")
    events = [e async for e in adapter.invoke(_make_step(), Context())]
    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].error_type == "invalid_input"
