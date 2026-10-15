"""Media vision and PDF reading on any vision-capable provider (no Claude required)."""

from __future__ import annotations

import io
from unittest.mock import patch

import litellm  # noqa: F401  (imported before any test clears provider keys)
import pytest
from realize_core.llm.base_provider import BaseLLMProvider, Capability, LLMResponse, ModelInfo
from realize_core.llm.registry import ProviderRegistry


class _FakeVision(BaseLLMProvider):
    """A vision provider that records how it was called."""

    def __init__(self, name: str, *, fail: bool = False, pdf_native: bool = False):
        self._name = name
        self.fail = fail
        self.supports_pdf_input = pdf_native
        self.vision_calls: list[dict] = []
        self.text_calls: list[dict] = []

    @property
    def name(self):
        return self._name

    async def complete(self, system_prompt, messages, model=None, **kwargs):
        self.text_calls.append({"messages": messages, "model": model})
        return LLMResponse(text=f"{self._name} read the text", provider=self._name)

    async def complete_with_vision(self, system_prompt, messages, image_data, media_type="image/jpeg", **kwargs):
        self.vision_calls.append({"messages": messages, "media_type": media_type, "size": len(image_data), **kwargs})
        if self.fail:
            raise RuntimeError("vision is down")
        return LLMResponse(text=f"{self._name} sees a cat", model="m", provider=self._name)

    def list_models(self):
        return [ModelInfo(model_id=f"{self._name}-model", capabilities={Capability.TEXT, Capability.VISION})]


class _TextOnly(_FakeVision):
    def list_models(self):
        return [ModelInfo(model_id="text-model", capabilities={Capability.TEXT})]


def _registry(*providers):
    reg = ProviderRegistry()
    for p in providers:
        reg.register(p)
    reg.set_fallback_chain([p.name for p in providers])
    return patch("realize_core.llm.registry.get_registry", return_value=reg)


def _pdf(text: str) -> bytes:
    """A one-page PDF whose text layer says ``text``."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(content)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def test_image_uses_a_non_claude_vision_provider():
    from realize_core.media import MediaType, analyze_image

    gemini = _FakeVision("gemini")
    with _registry(_TextOnly("textonly"), gemini):
        result = await analyze_image(b"\x89PNG...", mime_type="image/png", prompt="What is this?")

    assert result.success
    assert result.output == "gemini sees a cat"
    assert result.media_type == MediaType.IMAGE
    assert result.metadata["provider"] == "gemini"
    assert gemini.vision_calls[0]["media_type"] == "image/png"
    assert gemini.vision_calls[0]["messages"][-1]["content"] == "What is this?"


async def test_image_falls_through_to_the_next_vision_provider():
    from realize_core.media import analyze_image

    first, second = _FakeVision("openai", fail=True), _FakeVision("ollama")
    with _registry(first, second):
        result = await analyze_image(b"img")

    assert result.success
    assert result.output == "ollama sees a cat"
    assert len(first.vision_calls) == 1


async def test_no_vision_provider_fails_cleanly():
    from realize_core.media import analyze_image

    with _registry(_TextOnly("textonly")):
        result = await analyze_image(b"img")

    assert not result.success
    assert "vision" in result.error


async def test_pdf_on_a_provider_without_native_pdf_sends_the_extracted_text():
    from realize_core.media import MediaType, analyze_image

    gemini = _FakeVision("gemini")
    with _registry(gemini):
        result = await analyze_image(_pdf("Invoice 4521 total 360000"), mime_type="application/pdf", prompt="Summarise")

    assert result.success
    assert result.media_type == MediaType.DOCUMENT
    assert gemini.vision_calls == []
    sent = gemini.text_calls[0]["messages"][-1]["content"]
    assert "Summarise" in sent
    assert "Invoice 4521 total 360000" in sent


async def test_pdf_on_a_native_pdf_provider_goes_through_vision():
    from realize_core.media import analyze_image

    native = _FakeVision("native", pdf_native=True)
    with _registry(native):
        result = await analyze_image(b"%PDF-1.4 ...", mime_type="application/pdf")

    assert result.success
    assert native.vision_calls[0]["media_type"] == "application/pdf"
    assert native.text_calls == []


async def test_pdf_attachment_document_text_is_extracted():
    from realize_core.media import MediaAttachment, MediaType, process_attachment

    att = MediaAttachment(MediaType.DOCUMENT, mime_type="application/pdf", data=_pdf("Hello PDF"), file_name="a.pdf")
    result = await process_attachment(att)

    assert result.success
    assert "Hello PDF" in result.output


def test_claude_provider_declares_native_pdf():
    from realize_core.llm.base_provider import BaseLLMProvider
    from realize_core.llm.providers.claude_provider import ClaudeProvider

    assert ClaudeProvider.supports_pdf_input is True
    assert BaseLLMProvider.supports_pdf_input is False


@pytest.mark.parametrize("name", ["query_gemini", "query_claude", "gemini_pro"])
def test_media_names_no_provider(name):
    from pathlib import Path

    from realize_core import media

    assert name not in Path(media.__file__).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# PDFs on text-only providers, audio on any transcription-capable provider
# ---------------------------------------------------------------------------


@pytest.fixture
def no_limits():
    with (
        patch("realize_core.llm.router._check_rate_limit", return_value=True),
        patch("realize_core.llm.router._check_cost_limit", return_value=True),
    ):
        yield


async def test_pdf_with_only_a_text_provider_is_read_as_text(no_limits):
    from realize_core.media import MediaType, analyze_image

    ollama = _TextOnly("ollama")
    with _registry(ollama):
        result = await analyze_image(_pdf("Invoice 4521 total 360000"), mime_type="application/pdf", prompt="Summarise")

    assert result.success, result.error
    assert result.media_type == MediaType.DOCUMENT
    assert result.output == "ollama read the text"
    sent = ollama.text_calls[0]["messages"][-1]["content"]
    assert "Summarise" in sent
    assert "Invoice 4521 total 360000" in sent


async def test_image_with_only_a_text_provider_still_fails_cleanly(no_limits):
    from realize_core.media import analyze_image

    ollama = _TextOnly("ollama")
    with _registry(ollama):
        result = await analyze_image(b"img")

    assert not result.success
    assert ollama.text_calls == []


class _FakeTranscriber(_TextOnly):
    def __init__(self, name, *, transcribes=True, fail=False):
        super().__init__(name)
        self._transcribes = transcribes
        self._fail = fail
        self.audio_calls: list[dict] = []

    def supports_transcription(self):
        return self._transcribes

    async def transcribe(self, audio_data, mime_type="audio/ogg", language=None):
        self.audio_calls.append({"size": len(audio_data), "mime_type": mime_type, "language": language})
        if self._fail:
            return LLMResponse(text="", provider=self._name, error="stt down")
        return LLMResponse(text=f"{self._name} heard hello", model=f"{self._name}-stt", provider=self._name)


async def test_audio_uses_the_first_transcription_capable_provider():
    from realize_core.media import MediaType, transcribe_audio

    textonly = _FakeTranscriber("claude", transcribes=False)
    broken = _FakeTranscriber("gemini", fail=True)
    groq = _FakeTranscriber("litellm")
    with _registry(textonly, broken, groq):
        result = await transcribe_audio(b"OggS...", mime_type="audio/ogg", language="he")

    assert result.success, result.error
    assert result.output == "litellm heard hello"
    assert result.media_type == MediaType.AUDIO
    assert result.metadata["provider"] == "litellm"
    assert textonly.audio_calls == []
    assert broken.audio_calls[0] == {"size": 7, "mime_type": "audio/ogg", "language": "he"}


async def test_audio_without_a_transcription_provider_says_so():
    from realize_core.media import transcribe_audio

    with _registry(_FakeTranscriber("ollama", transcribes=False)):
        result = await transcribe_audio(b"OggS...")

    assert not result.success
    assert "no transcription-capable provider" in result.error.lower()


def test_transcription_capability_of_the_adapters(monkeypatch):
    from realize_core.llm.litellm_provider import LiteLLMProvider
    from realize_core.llm.providers.claude_provider import ClaudeProvider
    from realize_core.llm.providers.gemini_provider import GeminiProvider
    from realize_core.llm.providers.ollama_provider import OllamaProvider
    from realize_core.llm.providers.openai_provider import OpenAIProvider

    assert OpenAIProvider().supports_transcription()
    assert GeminiProvider().supports_transcription()
    assert not ClaudeProvider().supports_transcription()
    assert not OllamaProvider().supports_transcription()
    assert not LiteLLMProvider().supports_transcription()
    monkeypatch.setenv("LITELLM_TRANSCRIPTION_MODEL", "groq/whisper-large-v3")
    assert LiteLLMProvider().supports_transcription()


async def test_openai_and_litellm_transcribe_through_litellm(monkeypatch):
    from unittest.mock import AsyncMock

    from realize_core.llm.litellm_provider import LiteLLMProvider
    from realize_core.llm.providers.openai_provider import OpenAIProvider

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LITELLM_TRANSCRIPTION_MODEL", "groq/whisper-large-v3")
    fake = AsyncMock(return_value=type("T", (), {"text": "shalom"})())
    with patch("litellm.atranscription", fake):
        openai_resp = await OpenAIProvider().transcribe(b"abc", "audio/ogg", "he")
        groq_resp = await LiteLLMProvider().transcribe(b"abc", "audio/mpeg")

    assert openai_resp.ok
    assert openai_resp.text == "shalom"
    assert groq_resp.text == "shalom"
    first, second = (c.kwargs for c in fake.call_args_list)
    assert first["model"] == "openai/whisper-1"
    assert first["language"] == "he"
    assert first["file"][0] == "audio.ogg"
    assert first["file"][1] == b"abc"
    assert second["model"] == "groq/whisper-large-v3"
    assert "language" not in second


async def test_gemini_transcribes_with_an_audio_content_part(monkeypatch):
    import base64
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from realize_core.llm.providers.gemini_provider import GeminiProvider

    monkeypatch.setenv("GOOGLE_AI_API_KEY", "g-test")
    reply = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="hello there", tool_calls=None), finish_reason="stop")
        ],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2),
    )
    fake = AsyncMock(return_value=reply)
    with patch("litellm.acompletion", fake):
        resp = await GeminiProvider().transcribe(b"wavdata", "audio/wav", "en")

    assert resp.ok
    assert resp.text == "hello there"
    kwargs = fake.call_args.kwargs
    assert kwargs["model"].startswith("gemini/")
    parts = kwargs["messages"][-1]["content"]
    audio = next(p for p in parts if p["type"] == "input_audio")
    assert audio["input_audio"] == {"data": base64.b64encode(b"wavdata").decode(), "format": "wav"}
