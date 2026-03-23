"""
Advanced Task Classifier: Classifies user messages into multi-modal task types.

Extends the original classify_task() with support for:
- Image generation, video generation, audio, spreadsheet, code
- Modality detection for routing to specialized providers
- Confidence scoring for classification
"""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Modality(Enum):
    """Output modality that a task requires."""

    TEXT = "text"
    CODE = "code"
    IMAGE_GEN = "image_gen"
    VIDEO_GEN = "video_gen"
    AUDIO = "audio"
    SPREADSHEET = "spreadsheet"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    VISION = "vision"


@dataclass
class TaskClassification:
    """Result of classifying a user's message."""

    task_type: str  # Legacy task type for backward compat
    modality: Modality  # Primary output modality
    tier: int  # Recommended model tier (1=cheap, 2=mid, 3=premium)
    confidence: float  # 0.0 to 1.0 classification confidence
    requires_tools: bool  # Whether the task needs tool calling
    secondary_modality: Modality | None = None  # Optional second modality

    @property
    def is_multimodal(self) -> bool:
        return self.secondary_modality is not None


# Extended keyword sets for multi-modal classification
IMAGE_GEN_KEYWORDS = {
    "generate image",
    "create image",
    "draw",
    "design a logo",
    "create a graphic",
    "generate a picture",
    "make an image",
    "illustration",
    "visual design",
    "mockup",
    "wireframe",
    "generate art",
    "create art",
    "image of",
}

VIDEO_GEN_KEYWORDS = {
    "generate video",
    "create video",
    "make a video",
    "video clip",
    "animate",
    "animation",
    "render video",
    "video content",
    "produce video",
}

AUDIO_KEYWORDS = {
    "generate audio",
    "text to speech",
    "voice over",
    "create music",
    "sound effect",
    "podcast",
    "audio file",
    "narration",
    "voice",
}

CODE_KEYWORDS = {
    "write code",
    "code",
    "function",
    "class",
    "debug",
    "script",
    "program",
    "algorithm",
    "api",
    "endpoint",
    "refactor",
    "implement",
    "unit test",
    "test case",
    "python",
    "javascript",
    "typescript",
    "sql",
    "fix the bug",
    "pull request",
    "code review",
}

SPREADSHEET_KEYWORDS = {
    "spreadsheet",
    "excel",
    "csv",
    "table",
    "pivot table",
    "chart",
    "graph",
    "data visualization",
    "calculate",
    "formula",
    "financial model",
    "projection",
    "forecast",
}

VISION_KEYWORDS = {
    "look at this image",
    "analyze this image",
    "describe this photo",
    "what's in this picture",
    "screenshot",
    "scan this",
    "read this document",
    "ocr",
    "extract from image",
}

# Import the legacy keyword sets from router for backward compat
_LEGACY_KEYWORD_SETS = None


def _get_legacy_keywords():
    global _LEGACY_KEYWORD_SETS
    if _LEGACY_KEYWORD_SETS is None:
        from realize_core.llm.router import (
            COMPLEX_KEYWORDS,
            CONTENT_KEYWORDS,
            FINANCIAL_KEYWORDS,
            GOOGLE_KEYWORDS,
            REASONING_KEYWORDS,
            SIMPLE_KEYWORDS,
            WEB_ACTION_KEYWORDS,
            WEB_RESEARCH_KEYWORDS,
        )

        _LEGACY_KEYWORD_SETS = {
            "complex": COMPLEX_KEYWORDS,
            "financial": FINANCIAL_KEYWORDS,
            "reasoning": REASONING_KEYWORDS,
            "content": CONTENT_KEYWORDS,
            "simple": SIMPLE_KEYWORDS,
            "google": GOOGLE_KEYWORDS,
            "web_research": WEB_RESEARCH_KEYWORDS,
            "web_action": WEB_ACTION_KEYWORDS,
        }
    return _LEGACY_KEYWORD_SETS


def classify_task_advanced(message: str, system_key: str = None) -> TaskClassification:
    """
    Classify a user message into a multi-modal task type.

    This extends the original classify_task() with modality detection,
    confidence scoring, and multi-modal support.

    Args:
        message: The user's message text
        system_key: The target system key (optional)

    Returns:
        TaskClassification with task_type, modality, tier, and confidence
    """
    msg_lower = message.lower()

    # Score each modality
    scores: dict[str, float] = {}

    # Multi-modal task types (check first — these are specific)
    scores["image_gen"] = _keyword_score(msg_lower, IMAGE_GEN_KEYWORDS)
    scores["video_gen"] = _keyword_score(msg_lower, VIDEO_GEN_KEYWORDS)
    scores["audio"] = _keyword_score(msg_lower, AUDIO_KEYWORDS)
    scores["code"] = _keyword_score(msg_lower, CODE_KEYWORDS)
    scores["spreadsheet"] = _keyword_score(msg_lower, SPREADSHEET_KEYWORDS)
    scores["vision"] = _keyword_score(msg_lower, VISION_KEYWORDS)

    # Legacy task types
    legacy = _get_legacy_keywords()
    scores["google"] = _keyword_score(msg_lower, legacy["google"])
    scores["web_action"] = _keyword_score(msg_lower, legacy["web_action"])
    scores["web_research"] = _keyword_score(msg_lower, legacy["web_research"])
    scores["complex"] = _keyword_score(msg_lower, legacy["complex"])
    scores["financial"] = _keyword_score(msg_lower, legacy["financial"])
    scores["reasoning"] = _keyword_score(msg_lower, legacy["reasoning"])
    scores["content"] = _keyword_score(msg_lower, legacy["content"])
    scores["simple"] = _keyword_score(msg_lower, legacy["simple"])

    # Find top two scores
    sorted_types = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_type, top_score = sorted_types[0]
    second_type, second_score = sorted_types[1] if len(sorted_types) > 1 else (None, 0)

    # If no keywords matched, default to simple
    if top_score == 0:
        return TaskClassification(
            task_type="simple",
            modality=Modality.TEXT,
            tier=1,
            confidence=0.5,
            requires_tools=False,
        )

    # Map to modality and tier
    modality, tier, requires_tools = _type_to_modality(top_type)
    secondary = _type_to_modality(second_type)[0] if second_score > 0 and second_type else None

    # Calculate confidence (normalized score + gap from second)
    confidence = min(1.0, top_score * 0.7 + (top_score - second_score) * 0.3) if top_score > 0 else 0.5

    return TaskClassification(
        task_type=top_type,
        modality=modality,
        tier=tier,
        confidence=confidence,
        requires_tools=requires_tools,
        secondary_modality=secondary if secondary != modality else None,
    )


def _keyword_score(msg: str, keywords: set[str]) -> float:
    """Score a message against a keyword set. Returns match ratio."""
    matches = sum(1 for kw in keywords if kw in msg)
    return matches / max(len(keywords), 1)


def _type_to_modality(task_type: str) -> tuple[Modality, int, bool]:
    """Map a task type to (modality, tier, requires_tools)."""
    mapping = {
        "simple": (Modality.TEXT, 1, False),
        "content": (Modality.TEXT, 2, False),
        "reasoning": (Modality.REASONING, 2, False),
        "financial": (Modality.REASONING, 2, False),
        "complex": (Modality.REASONING, 3, False),
        "google": (Modality.TOOL_USE, 2, True),
        "web_research": (Modality.TOOL_USE, 2, True),
        "web_action": (Modality.TOOL_USE, 2, True),
        "code": (Modality.CODE, 2, False),
        "image_gen": (Modality.IMAGE_GEN, 2, True),
        "video_gen": (Modality.VIDEO_GEN, 3, True),
        "audio": (Modality.AUDIO, 2, True),
        "spreadsheet": (Modality.SPREADSHEET, 2, False),
        "vision": (Modality.VISION, 2, False),
    }
    return mapping.get(task_type, (Modality.TEXT, 1, False))
