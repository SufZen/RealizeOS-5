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
# Vision: Image understanding
# ---------------------------------------------------------------------------


async def analyze_image(
    image_data: bytes,
    mime_type: str = "image/jpeg",
    prompt: str = "Describe this image in detail.",
    model: str = "gemini_pro",
) -> MediaResult:
    """
    Analyze an image using a vision-capable LLM.

    Args:
        image_data: Raw image bytes
        mime_type: MIME type of the image
        prompt: What to analyze about the image
        model: Which vision model to use

    Returns:
        MediaResult with the analysis text
    """
    if not image_data:
        return MediaResult.fail("No image data provided")

    try:
        # Try Gemini Vision first (free, high quality)
        from realize_core.llm.gemini_client import query_gemini

        response = await query_gemini(
            prompt=prompt,
            image_data=image_data,
            image_media_type=mime_type,
        )
        return MediaResult.ok(response, MediaType.IMAGE, model=model)
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Gemini vision failed: {e}")

    try:
        # Fallback to Claude Vision
        from realize_core.llm.claude_client import query_claude

        response = await query_claude(
            prompt=prompt,
            image_data=image_data,
            image_media_type=mime_type,
        )
        return MediaResult.ok(response, MediaType.IMAGE, model="claude_sonnet")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Claude vision failed: {e}")

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
    Transcribe audio to text.

    Uses OpenAI Whisper API if available, otherwise returns guidance.

    Args:
        audio_data: Raw audio bytes
        mime_type: MIME type (audio/ogg, audio/mp3, etc.)
        language: ISO language code

    Returns:
        MediaResult with the transcription
    """
    if not audio_data:
        return MediaResult.fail("No audio data provided")

    # Try OpenAI Whisper
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            import io

            import httpx

            # Determine file extension from mime type
            ext_map = {
                "audio/ogg": "ogg",
                "audio/mp3": "mp3",
                "audio/mpeg": "mp3",
                "audio/wav": "wav",
                "audio/webm": "webm",
                "audio/m4a": "m4a",
            }
            ext = ext_map.get(mime_type, "ogg")

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data={"model": "whisper-1", "language": language},
                    files={"file": (f"audio.{ext}", io.BytesIO(audio_data), mime_type)},
                )
                resp.raise_for_status()
                text = resp.json().get("text", "")
                return MediaResult.ok(text, MediaType.AUDIO, model="whisper-1")
        except Exception as e:
            logger.warning(f"Whisper transcription failed: {e}")

    return MediaResult.fail("Audio transcription requires OPENAI_API_KEY for Whisper API")


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

    # Try to decode as text
    try:
        text = attachment.data.decode("utf-8")
        if len(text) > 50000:
            text = text[:50000] + "\n\n[...truncated]"
        return MediaResult.ok(text, MediaType.DOCUMENT, file_name=attachment.file_name)
    except UnicodeDecodeError:
        pass

    return MediaResult.fail(
        f"Cannot read document '{attachment.file_name}'. Binary formats (PDF, DOCX) require additional dependencies."
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
        api_key = os.environ.get("OPENAI_API_KEY", "")
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
