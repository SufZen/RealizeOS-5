"""
Media Pipeline: Handles media attachments across channels.

Supports:
- Image understanding via vision-capable LLMs
- Voice/audio transcription
- Media ingestion (download from channel, process, store)
- Media generation routing (images, video, audio)
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MediaType(Enum):
    """Supported media types."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


@dataclass
class MediaAttachment:
    """A media attachment from any channel."""

    media_type: MediaType
    mime_type: str = ""
    data: bytes = b""
    url: str = ""  # Remote URL (for download)
    file_name: str = ""
    file_size: int = 0
    channel: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_data(self) -> bool:
        return len(self.data) > 0

    @property
    def has_url(self) -> bool:
        return bool(self.url)


@dataclass
class MediaResult:
    """Result of processing a media attachment."""

    success: bool
    output: str  # Human-readable output (transcription, description)
    media_type: MediaType = MediaType.UNKNOWN
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def ok(output: str, media_type: MediaType = MediaType.UNKNOWN, **kwargs) -> "MediaResult":
        return MediaResult(success=True, output=output, media_type=media_type, metadata=kwargs)

    @staticmethod
    def fail(error: str) -> "MediaResult":
        return MediaResult(success=False, output="", error=error)


def detect_media_type(mime_type: str) -> MediaType:
    """Detect MediaType from MIME type string."""
    if not mime_type:
        return MediaType.UNKNOWN
    mime = mime_type.lower()
    if mime.startswith("image/"):
        return MediaType.IMAGE
    if mime.startswith("audio/"):
        return MediaType.AUDIO
    if mime.startswith("video/"):
        return MediaType.VIDEO
    if mime.startswith("application/") or mime.startswith("text/"):
        return MediaType.DOCUMENT
    return MediaType.UNKNOWN


# ---------------------------------------------------------------------------
# Vision: Image understanding (and PDFs)
# ---------------------------------------------------------------------------

PDF_MIME = "application/pdf"
_VISION_SYSTEM_PROMPT = "You read images and documents carefully and answer accurately."
#: Longest PDF text sent to a model that reads it as text.
_MAX_PDF_TEXT = 50000


def extract_pdf_text(data: bytes) -> str:
    """The text layer of a PDF (empty when there is none or ``pypdf`` is missing)."""
    try:
        import io

        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf is not installed; PDF text can't be extracted")
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return ""
    if len(text) > _MAX_PDF_TEXT:
        text = text[:_MAX_PDF_TEXT] + "\n\n[...truncated]"
    return text


async def analyze_image(
    image_data: bytes,
    mime_type: str = "image/jpeg",
    prompt: str = "Describe this image in detail.",
    model: str | None = None,
) -> MediaResult:
    """
    Analyze an image (or a PDF) with any vision-capable provider.

    Providers are tried in fallback-chain order until one answers. A PDF goes
    to a provider's vision call only when it reads PDFs natively
    (``supports_pdf_input``); other providers get the PDF's extracted text.

    Args:
        image_data: Raw image (or PDF) bytes
        mime_type: MIME type of the data
        prompt: What to analyze about the image
        model: Optional model id for the provider (None = the provider's default)

    Returns:
        MediaResult with the analysis text
    """
    if not image_data:
        return MediaResult.fail("No image data provided")

    from realize_core.llm.base_provider import Capability
    from realize_core.llm.registry import get_registry

    is_pdf = mime_type == PDF_MIME
    media_type = MediaType.DOCUMENT if is_pdf else MediaType.IMAGE
    messages = [{"role": "user", "content": prompt}]
    pdf_text: str | None = None

    for provider in get_registry().providers_with_capability(Capability.VISION):
        try:
            if is_pdf and not getattr(provider, "supports_pdf_input", False):
                if pdf_text is None:
                    pdf_text = extract_pdf_text(image_data)
                if not pdf_text:
                    continue
                content = f"{prompt}\n\n--- Document text ---\n{pdf_text}"
                response = await provider.complete(
                    _VISION_SYSTEM_PROMPT, [{"role": "user", "content": content}], model=model
                )
            else:
                response = await provider.complete_with_vision(
                    _VISION_SYSTEM_PROMPT, messages, image_data, media_type=mime_type, model=model
                )
        except Exception as e:
            logger.warning(f"Vision via {provider.name} failed: {e}")
            continue
        if response.ok and response.text:
            return MediaResult.ok(response.text, media_type, model=response.model, provider=provider.name)
        logger.warning(f"Vision via {provider.name} failed: {response.error or 'empty response'}")

    if is_pdf:
        # No vision provider read it: any text-capable provider can read the extracted text.
        if pdf_text is None:
            pdf_text = extract_pdf_text(image_data)
        if pdf_text:
            from realize_core.llm.router import route_completion

            content = f"{prompt}\n\n--- Document text ---\n{pdf_text}"
            response = await route_completion(
                _VISION_SYSTEM_PROMPT, [{"role": "user", "content": content}], tier="fast", model=model
            )
            if response.ok and response.text:
                return MediaResult.ok(response.text, media_type, model=response.model, provider=response.provider)
            logger.warning(f"Reading the PDF text failed: {response.error or 'empty response'}")
            return MediaResult.fail("No provider could read this PDF")
        return MediaResult.fail("No provider could read this PDF (no text layer, and no provider reads PDFs natively)")
    return MediaResult.fail("No vision-capable model available")


# ---------------------------------------------------------------------------
# Audio: Transcription
# ---------------------------------------------------------------------------


async def transcribe_audio(
    audio_data: bytes,
    mime_type: str = "audio/ogg",
    language: str = "en",
) -> MediaResult:
    """
    Transcribe audio to text with any transcription-capable provider.

    Providers are asked in fallback-chain order (``supports_transcription()``):
    OpenAI (Whisper) and the generic LiteLLM provider (any
    ``LITELLM_TRANSCRIPTION_MODEL``, e.g. ``groq/whisper-large-v3``) go through
    ``litellm.atranscription``; Gemini reads the audio in a chat message. The
    first transcript wins.

    Args:
        audio_data: Raw audio bytes
        mime_type: MIME type (audio/ogg, audio/mp3, etc.)
        language: ISO language code

    Returns:
        MediaResult with the transcription
    """
    if not audio_data:
        return MediaResult.fail("No audio data provided")

    from realize_core.llm.base_provider import Capability
    from realize_core.llm.registry import get_registry

    tried = False
    for provider in get_registry().providers_with_capability(Capability.TEXT):
        try:
            if not provider.supports_transcription():
                continue
            tried = True
            response = await provider.transcribe(audio_data, mime_type=mime_type, language=language)
        except Exception as e:
            logger.warning(f"Transcription via {provider.name} failed: {e}")
            continue
        if response.ok and response.text.strip():
            return MediaResult.ok(response.text, MediaType.AUDIO, model=response.model, provider=provider.name)
        logger.warning(f"Transcription via {provider.name} failed: {response.error or 'empty transcript'}")

    if tried:
        return MediaResult.fail("Audio transcription failed on every transcription-capable provider")
    return MediaResult.fail(
        "No transcription-capable provider configured. Any one of: an OpenAI key (Whisper), a Gemini key, "
        "or LITELLM_TRANSCRIPTION_MODEL (e.g. groq/whisper-large-v3) for the LiteLLM provider."
    )


# ---------------------------------------------------------------------------
# Auto-ingestion pipeline
# ---------------------------------------------------------------------------


async def process_attachment(
    attachment: MediaAttachment,
    prompt: str = "",
) -> MediaResult:
    """
    Auto-process any media attachment based on its type.

    This is the main entry point for the ingestion pipeline.
    Routes to the appropriate handler based on media type.

    Args:
        attachment: The media attachment to process
        prompt: Optional prompt/instruction for processing

    Returns:
        MediaResult with the processing outcome
    """
    media_type = attachment.media_type
    if media_type == MediaType.UNKNOWN:
        media_type = detect_media_type(attachment.mime_type)

    if media_type == MediaType.IMAGE:
        return await analyze_image(
            image_data=attachment.data,
            mime_type=attachment.mime_type,
            prompt=prompt or "Describe this image in detail. Include any text visible in the image.",
        )

    if media_type == MediaType.AUDIO:
        return await transcribe_audio(
            audio_data=attachment.data,
            mime_type=attachment.mime_type,
        )

    if media_type == MediaType.VIDEO:
        # Video: extract first frame for vision, or return guidance
        return MediaResult.fail("Video processing not yet implemented. Tip: Extract key frames and send as images.")

    if media_type == MediaType.DOCUMENT:
        # Documents: extract text
        return await _process_document(attachment)

    return MediaResult.fail(f"Unsupported media type: {attachment.mime_type}")


async def _process_document(attachment: MediaAttachment) -> MediaResult:
    """Extract text from a document attachment."""
    if not attachment.data:
        return MediaResult.fail("No document data")

    if attachment.mime_type == PDF_MIME:
        text = extract_pdf_text(attachment.data)
        if text:
            return MediaResult.ok(text, MediaType.DOCUMENT, file_name=attachment.file_name)
        return MediaResult.fail(f"No text could be read from PDF '{attachment.file_name}'.")

    # Try to decode as text
    try:
        text = attachment.data.decode("utf-8")
        if len(text) > 50000:
            text = text[:50000] + "\n\n[...truncated]"
        return MediaResult.ok(text, MediaType.DOCUMENT, file_name=attachment.file_name)
    except UnicodeDecodeError:
        pass

    return MediaResult.fail(
        f"Cannot read document '{attachment.file_name}'. Binary formats (such as DOCX) require additional dependencies."
    )


# ---------------------------------------------------------------------------
# Media generation routing
# ---------------------------------------------------------------------------


async def route_media_generation(
    prompt: str,
    media_type: MediaType,
    channel: str = "",
) -> MediaResult:
    """
    Route a media generation request to the appropriate service.

    Args:
        prompt: Description of what to generate
        media_type: Type of media to generate
        channel: Target channel (affects format/size)

    Returns:
        MediaResult with generation outcome or guidance
    """
    if media_type == MediaType.IMAGE:
        # Try image generation providers
        api_key = os.environ.get(
            "OPENAI_API_KEY", ""
        )  # provider-neutral: ok image generation is an unimplemented stub naming DALL-E
        if api_key:
            return MediaResult.ok(
                f"Image generation ready. Prompt: '{prompt[:100]}'. Use DALL-E 3 or Imagen via the routing engine.",
                MediaType.IMAGE,
                provider="openai",
                action="generate",
            )

        return MediaResult.fail(
            "Image generation requires OPENAI_API_KEY (for DALL-E) or Google Cloud credentials (for Imagen)."
        )

    if media_type == MediaType.AUDIO:
        return MediaResult.fail(
            "Audio generation (TTS) is planned but not yet implemented. Consider using ElevenLabs or Google Cloud TTS."
        )

    if media_type == MediaType.VIDEO:
        return MediaResult.fail(
            "Video generation is planned but not yet implemented. Consider using Google Veo or Runway when available."
        )

    return MediaResult.fail(f"Cannot generate media of type: {media_type.value}")
