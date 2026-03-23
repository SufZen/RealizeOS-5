"""Tests for realize_core.llm.classifier — advanced task classification."""

from realize_core.llm.classifier import (
    Modality,
    TaskClassification,
    classify_task_advanced,
)


class TestModality:
    def test_all_modalities(self):
        expected = {
            "text",
            "code",
            "image_gen",
            "video_gen",
            "audio",
            "spreadsheet",
            "reasoning",
            "tool_use",
            "vision",
        }
        assert {m.value for m in Modality} == expected


class TestTaskClassification:
    def test_dataclass_fields(self):
        tc = TaskClassification(
            task_type="content",
            modality=Modality.TEXT,
            tier=2,
            confidence=0.8,
            requires_tools=False,
        )
        assert tc.task_type == "content"
        assert tc.modality == Modality.TEXT
        assert tc.tier == 2
        assert tc.confidence == 0.8
        assert not tc.requires_tools
        assert not tc.is_multimodal

    def test_multimodal_flag(self):
        tc = TaskClassification(
            task_type="code",
            modality=Modality.CODE,
            tier=2,
            confidence=0.7,
            requires_tools=False,
            secondary_modality=Modality.TEXT,
        )
        assert tc.is_multimodal

    def test_not_multimodal_when_none(self):
        tc = TaskClassification(
            task_type="simple",
            modality=Modality.TEXT,
            tier=1,
            confidence=0.5,
            requires_tools=False,
        )
        assert not tc.is_multimodal


class TestClassifyTaskAdvanced:
    def test_simple_question(self):
        result = classify_task_advanced("What is machine learning?")
        assert result.task_type == "simple"
        assert result.modality == Modality.TEXT
        assert result.tier == 1

    def test_content_creation(self):
        result = classify_task_advanced("Write a blog post about startups")
        # "write" is both in CONTENT_KEYWORDS and CODE_KEYWORDS, but
        # "blog" and "post" should push content higher
        assert result.modality in (Modality.TEXT, Modality.CODE)

    def test_code_task(self):
        result = classify_task_advanced("Write a Python function to sort a list")
        assert result.modality in (Modality.CODE, Modality.TEXT)

    def test_image_gen(self):
        result = classify_task_advanced("Generate image of a sunset over the ocean")
        assert result.task_type == "image_gen"
        assert result.modality == Modality.IMAGE_GEN
        assert result.requires_tools

    def test_video_gen(self):
        result = classify_task_advanced("Generate video of a product demo")
        assert result.task_type == "video_gen"
        assert result.modality == Modality.VIDEO_GEN
        assert result.tier == 3

    def test_empty_message_defaults_to_simple(self):
        result = classify_task_advanced("")
        assert result.task_type == "simple"
        assert result.tier == 1

    def test_financial_keywords(self):
        result = classify_task_advanced("Calculate the ROI and IRR for this investment")
        assert result.task_type == "financial"
        assert result.modality == Modality.REASONING

    def test_google_workspace(self):
        result = classify_task_advanced("Send an email to John about the meeting")
        assert result.task_type == "google"
        assert result.requires_tools

    def test_confidence_is_bounded(self):
        result = classify_task_advanced("Any random message")
        assert 0.0 <= result.confidence <= 1.0

    def test_vision_task(self):
        result = classify_task_advanced("Look at this image and describe what you see")
        assert result.modality == Modality.VISION

    def test_spreadsheet_task(self):
        result = classify_task_advanced("Create a spreadsheet with financial projections")
        # Both spreadsheet and financial keywords match
        assert result.modality in (Modality.SPREADSHEET, Modality.REASONING)

    def test_complex_cross_system(self):
        result = classify_task_advanced("Do a strategic analysis across all systems in the ecosystem")
        assert result.task_type == "complex"
        assert result.tier == 3
