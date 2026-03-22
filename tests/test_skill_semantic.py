"""
Tests for realize_core.skills.semantic — LLM-based semantic matching.

Covers:
- Successful semantic match (mocked LLM)
- No match when score below threshold
- Graceful handling when no LLM available
- JSON extraction from various response formats
- Empty inputs
- Batch matching
"""
import json
import sys
import types
from unittest.mock import AsyncMock

import pytest

# Pre-register mock modules for LLM clients
if "realize_core.llm.claude_client" not in sys.modules:
    _mock_claude = types.ModuleType("realize_core.llm.claude_client")
    _mock_claude.call_claude = AsyncMock()
    sys.modules["realize_core.llm.claude_client"] = _mock_claude

from realize_core.skills.base import TriggerMethod
from realize_core.skills.semantic import (
    _extract_json,
    _parse_semantic_response,
    semantic_match,
    semantic_match_batch,
)

# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

class TestExtractJson:

    def test_plain_json(self):
        text = '{"skill_key": "test", "score": 0.8, "reason": "match"}'
        assert _extract_json(text) == text

    def test_json_in_code_block(self):
        text = '```json\n{"skill_key": "test", "score": 0.8}\n```'
        result = _extract_json(text)
        assert result is not None
        data = json.loads(result)
        assert data["skill_key"] == "test"

    def test_json_in_generic_block(self):
        text = '```\n{"skill_key": "test", "score": 0.8}\n```'
        result = _extract_json(text)
        assert result is not None
        data = json.loads(result)
        assert data["skill_key"] == "test"

    def test_json_embedded_in_text(self):
        text = 'Here is the match: {"skill_key": "test", "score": 0.9} end'
        result = _extract_json(text)
        assert result is not None
        data = json.loads(result)
        assert data["skill_key"] == "test"

    def test_no_json(self):
        assert _extract_json("No JSON here at all") is None

    def test_empty_string(self):
        assert _extract_json("") is None


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

class TestParseSemanticResponse:

    def test_valid_match(self):
        response = json.dumps({
            "skill_key": "content_pipeline",
            "score": 0.85,
            "reason": "Strong match for content creation"
        })
        result = _parse_semantic_response(response, threshold=0.6)
        assert result is not None
        assert result.skill_key == "content_pipeline"
        assert result.score == 0.85
        assert result.trigger_method == TriggerMethod.SEMANTIC
        assert "content creation" in result.confidence_reason

    def test_below_threshold(self):
        response = json.dumps({
            "skill_key": "some_skill",
            "score": 0.3,
            "reason": "Weak match"
        })
        result = _parse_semantic_response(response, threshold=0.6)
        assert result is None

    def test_no_match_response(self):
        result = _parse_semantic_response("NO_MATCH", threshold=0.6)
        assert result is None

    def test_null_skill_key(self):
        response = json.dumps({
            "skill_key": None,
            "score": 0.0,
            "reason": "No match found"
        })
        result = _parse_semantic_response(response, threshold=0.6)
        assert result is None

    def test_empty_response(self):
        assert _parse_semantic_response("", threshold=0.6) is None
        assert _parse_semantic_response(None, threshold=0.6) is None

    def test_invalid_json(self):
        result = _parse_semantic_response("not json {broken", threshold=0.6)
        # Should gracefully return None
        assert result is None


# ---------------------------------------------------------------------------
# Semantic match (mocked LLM)
# ---------------------------------------------------------------------------

class TestSemanticMatch:

    @pytest.mark.asyncio
    async def test_successful_match(self):
        """LLM returns a match above threshold."""
        async def mock_llm(**kwargs):
            return json.dumps({
                "skill_key": "strategy_session",
                "score": 0.88,
                "reason": "Message about brand positioning matches strategy skill"
            })

        result = await semantic_match(
            message="How should I position my brand in the market?",
            skill_summaries=[
                {"key": "content_pipeline", "description": "Content creation"},
                {"key": "strategy_session", "description": "Strategic analysis"},
            ],
            llm_fn=mock_llm,
        )

        assert result is not None
        assert result.skill_key == "strategy_session"
        assert result.score == 0.88
        assert result.trigger_method == TriggerMethod.SEMANTIC

    @pytest.mark.asyncio
    async def test_no_match_below_threshold(self):
        """LLM returns score below threshold."""
        async def mock_llm(**kwargs):
            return json.dumps({
                "skill_key": "content_pipeline",
                "score": 0.4,
                "reason": "Weak match"
            })

        result = await semantic_match(
            message="What's the weather today?",
            skill_summaries=[
                {"key": "content_pipeline", "description": "Content creation"},
            ],
            llm_fn=mock_llm,
            threshold=0.6,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_skills(self):
        """Empty skill list should return None instantly."""
        result = await semantic_match(
            message="Some message",
            skill_summaries=[],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_message(self):
        """Empty message should return None."""
        result = await semantic_match(
            message="",
            skill_summaries=[{"key": "test", "description": "test"}],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self):
        """If LLM call raises, should return None."""
        async def failing_llm(**kwargs):
            raise RuntimeError("API error")

        result = await semantic_match(
            message="test message",
            skill_summaries=[{"key": "test", "description": "test"}],
            llm_fn=failing_llm,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_no_llm_available(self):
        """Without llm_fn and no importable default, return None."""
        # Temporarily hide mock LLM modules so _get_default_llm returns None
        saved = {}
        for mod_name in list(sys.modules):
            if "claude_client" in mod_name or "gemini_client" in mod_name:
                saved[mod_name] = sys.modules.pop(mod_name)
        try:
            result = await semantic_match(
                message="test",
                skill_summaries=[{"key": "test", "description": "test"}],
                llm_fn=None,
            )
            assert result is None
        finally:
            sys.modules.update(saved)

    @pytest.mark.asyncio
    async def test_custom_threshold(self):
        """Custom threshold should be respected."""
        async def mock_llm(**kwargs):
            return json.dumps({
                "skill_key": "test",
                "score": 0.55,
                "reason": "Moderate match"
            })

        # With 0.6 threshold: no match
        result = await semantic_match(
            message="test",
            skill_summaries=[{"key": "test", "description": "test"}],
            llm_fn=mock_llm,
            threshold=0.6,
        )
        assert result is None

        # With 0.5 threshold: match
        result = await semantic_match(
            message="test",
            skill_summaries=[{"key": "test", "description": "test"}],
            llm_fn=mock_llm,
            threshold=0.5,
        )
        assert result is not None
        assert result.score == 0.55


# ---------------------------------------------------------------------------
# Batch matching
# ---------------------------------------------------------------------------

class TestSemanticMatchBatch:

    @pytest.mark.asyncio
    async def test_batch_returns_list(self):
        """Batch match should return a list."""
        async def mock_llm(**kwargs):
            return json.dumps({
                "skill_key": "content_pipeline",
                "score": 0.9,
                "reason": "Strong match"
            })

        results = await semantic_match_batch(
            message="write a blog post",
            skill_summaries=[
                {"key": "content_pipeline", "description": "Content creation"},
            ],
            llm_fn=mock_llm,
        )
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].skill_key == "content_pipeline"

    @pytest.mark.asyncio
    async def test_batch_empty_on_no_match(self):
        """Batch returns empty list when no match."""
        async def mock_llm(**kwargs):
            return "NO_MATCH"

        results = await semantic_match_batch(
            message="something unrelated",
            skill_summaries=[
                {"key": "test", "description": "test"},
            ],
            llm_fn=mock_llm,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_empty_inputs(self):
        """Batch with empty inputs returns empty list."""
        results = await semantic_match_batch(
            message="",
            skill_summaries=[],
        )
        assert results == []
