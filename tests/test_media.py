"""Tests for realize_core.media — media pipeline."""

import pytest
from realize_core.media import (
    MediaAttachment,
    MediaResult,
    MediaType,
    detect_media_type,
)


class TestMediaType:
    def test_all_types(self):
        assert len(MediaType) == 5  # image, audio, video, document, unknown

    def test_values(self):
        assert MediaType.IMAGE.value == "image"
        assert MediaType.AUDIO.value == "audio"
        assert MediaType.UNKNOWN.value == "unknown"


class TestDetectMediaType:
    def test_image_types(self):
        assert detect_media_type("image/jpeg") == MediaType.IMAGE
        assert detect_media_type("image/png") == MediaType.IMAGE
        assert detect_media_type("image/webp") == MediaType.IMAGE

    def test_audio_types(self):
        assert detect_media_type("audio/ogg") == MediaType.AUDIO
        assert detect_media_type("audio/mp3") == MediaType.AUDIO

    def test_video_types(self):
        assert detect_media_type("video/mp4") == MediaType.VIDEO

    def test_document_types(self):
        assert detect_media_type("application/pdf") == MediaType.DOCUMENT
        assert detect_media_type("text/plain") == MediaType.DOCUMENT

    def test_unknown(self):
        assert detect_media_type("") == MediaType.UNKNOWN
        assert detect_media_type("foo/bar") == MediaType.UNKNOWN


class TestMediaAttachment:
    def test_defaults(self):
        att = MediaAttachment(media_type=MediaType.IMAGE)
        assert not att.has_data
        assert not att.has_url

    def test_with_data(self):
        att = MediaAttachment(
            media_type=MediaType.IMAGE,
            data=b"fake-image-data",
            mime_type="image/jpeg",
        )
        assert att.has_data
        assert not att.has_url

    def test_with_url(self):
        att = MediaAttachment(
            media_type=MediaType.IMAGE,
            url="https://example.com/image.jpg",
        )
        assert att.has_url
        assert not att.has_data


class TestMediaResult:
    def test_ok(self):
        result = MediaResult.ok("Description of image", MediaType.IMAGE)
        assert result.success
        assert result.output == "Description of image"
        assert result.error is None

    def test_fail(self):
        result = MediaResult.fail("No vision model available")
        assert not result.success
        assert result.error == "No vision model available"

    def test_ok_with_metadata(self):
        result = MediaResult.ok("text", model="whisper-1")
        assert result.metadata["model"] == "whisper-1"


class TestProcessAttachment:
    @pytest.mark.asyncio
    async def test_no_image_data(self):
        from realize_core.media import analyze_image

        result = await analyze_image(b"")
        assert not result.success
        assert "No image data" in result.error

    @pytest.mark.asyncio
    async def test_no_audio_data(self):
        from realize_core.media import transcribe_audio

        result = await transcribe_audio(b"")
        assert not result.success

    @pytest.mark.asyncio
    async def test_process_text_document(self):
        from realize_core.media import process_attachment

        att = MediaAttachment(
            media_type=MediaType.DOCUMENT,
            data=b"Hello, this is a text file.",
            mime_type="text/plain",
            file_name="readme.txt",
        )
        result = await process_attachment(att)
        assert result.success
        assert "Hello" in result.output

    @pytest.mark.asyncio
    async def test_process_unsupported_video(self):
        from realize_core.media import process_attachment

        att = MediaAttachment(
            media_type=MediaType.VIDEO,
            data=b"fake-video",
            mime_type="video/mp4",
        )
        result = await process_attachment(att)
        assert not result.success
        assert "not yet implemented" in result.error


class TestRouteMediaGeneration:
    @pytest.mark.asyncio
    async def test_audio_generation_not_ready(self):
        from realize_core.media import route_media_generation

        result = await route_media_generation("Say hello", MediaType.AUDIO)
        assert not result.success
        assert "not yet implemented" in result.error

    @pytest.mark.asyncio
    async def test_video_generation_not_ready(self):
        from realize_core.media import route_media_generation

        result = await route_media_generation("Make intro", MediaType.VIDEO)
        assert not result.success
