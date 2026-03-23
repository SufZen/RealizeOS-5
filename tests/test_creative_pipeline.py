"""Tests for realize_core.pipeline — creative pipeline and session management.

Covers:
- Task type detection from system config
- Pipeline creation from routing config
- Session lifecycle: create, advance pipeline, add drafts
- Session summary output
- Fallback behavior (no matching route → orchestrator)
"""

from unittest.mock import patch

import pytest
from realize_core.pipeline.creative import (
    _COMMON_PATTERNS,
    detect_task_type,
    get_pipeline,
    start_pipeline,
)
from realize_core.pipeline.session import CreativeSession

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def routing_config():
    """System config with routing definitions."""
    return {
        "name": "Test System",
        "routing": {
            "content": ["writer", "reviewer", "gatekeeper"],
            "strategy": ["analyst", "strategist", "reviewer"],
            "research": ["researcher", "analyst"],
            "general": ["orchestrator"],
        },
        "agents": {
            "orchestrator": "agents/orchestrator.md",
            "writer": "agents/writer.md",
        },
    }


@pytest.fixture
def empty_routing_config():
    """System config with no routing defined."""
    return {
        "name": "No Routes",
        "agents": {},
    }


@pytest.fixture
def mock_session():
    """Create a CreativeSession without database persistence."""
    return CreativeSession(
        id="test-001",
        system_key="test",
        brief="Write a blog post about AI trends",
        task_type="content",
        active_agent="writer",
        stage="briefing",
        pipeline=["writer", "reviewer", "gatekeeper"],
        pipeline_index=0,
        user_id="user1",
    )


# ---------------------------------------------------------------------------
# Task type detection
# ---------------------------------------------------------------------------


class TestDetectTaskType:
    def test_detect_content(self, routing_config):
        result = detect_task_type(routing_config, "write a blog post about AI")
        assert result == "content"

    def test_detect_strategy(self, routing_config):
        result = detect_task_type(routing_config, "analyze our competitive positioning")
        assert result == "strategy"

    def test_detect_research(self, routing_config):
        result = detect_task_type(routing_config, "research the market trends")
        assert result == "research"

    def test_unmatched_defaults_to_general(self, routing_config):
        result = detect_task_type(routing_config, "hello how are you")
        assert result == "general"

    def test_case_insensitive(self, routing_config):
        result = detect_task_type(routing_config, "WRITE A BLOG POST")
        assert result == "content"

    def test_empty_routing(self, empty_routing_config):
        result = detect_task_type(empty_routing_config, "write something")
        assert result == "general"

    def test_common_patterns_exist(self):
        """Common patterns dict has expected task types."""
        assert "content" in _COMMON_PATTERNS
        assert "strategy" in _COMMON_PATTERNS
        assert "research" in _COMMON_PATTERNS


# ---------------------------------------------------------------------------
# Pipeline retrieval
# ---------------------------------------------------------------------------


class TestGetPipeline:
    def test_content_pipeline(self, routing_config):
        pipeline = get_pipeline(routing_config, "content")
        assert pipeline == ["writer", "reviewer", "gatekeeper"]

    def test_strategy_pipeline(self, routing_config):
        pipeline = get_pipeline(routing_config, "strategy")
        assert pipeline == ["analyst", "strategist", "reviewer"]

    def test_unknown_type_fallback(self, routing_config):
        """Unknown task type falls back to orchestrator."""
        pipeline = get_pipeline(routing_config, "unknown_type")
        assert pipeline == ["orchestrator"]

    def test_no_routing_config(self, empty_routing_config):
        pipeline = get_pipeline(empty_routing_config, "content")
        assert pipeline == ["orchestrator"]

    def test_returns_copy_not_reference(self, routing_config):
        """Should return a copy so modifications don't affect config."""
        pipeline1 = get_pipeline(routing_config, "content")
        pipeline2 = get_pipeline(routing_config, "content")
        pipeline1.append("extra")
        assert len(pipeline2) == 3  # Original unchanged


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


class TestCreativeSession:
    def test_initial_state(self, mock_session):
        assert mock_session.stage == "briefing"
        assert mock_session.pipeline_index == 0
        assert mock_session.active_agent == "writer"
        assert len(mock_session.drafts) == 0

    def test_current_pipeline_agent(self, mock_session):
        assert mock_session.current_pipeline_agent() == "writer"

    def test_advance_pipeline(self, mock_session):
        """Advancing should move to the next agent."""
        # Patch save to avoid DB calls in tests
        with patch.object(mock_session, "save"):
            next_agent = mock_session.advance_pipeline()
            assert next_agent == "reviewer"
            assert mock_session.pipeline_index == 1
            assert mock_session.active_agent == "reviewer"

    def test_advance_pipeline_to_end(self, mock_session):
        """Advancing past the last agent returns None."""
        with patch.object(mock_session, "save"):
            mock_session.advance_pipeline()  # → reviewer
            mock_session.advance_pipeline()  # → gatekeeper
            result = mock_session.advance_pipeline()  # → None (past end)
            assert result is None

    def test_add_draft(self, mock_session):
        with patch.object(mock_session, "save"):
            mock_session.add_draft("Draft content here", "writer")
            assert len(mock_session.drafts) == 1
            assert mock_session.drafts[0]["content"] == "Draft content here"
            assert mock_session.drafts[0]["agent"] == "writer"
            assert mock_session.drafts[0]["version"] == 1

    def test_add_multiple_drafts(self, mock_session):
        with patch.object(mock_session, "save"):
            mock_session.add_draft("First draft", "writer")
            mock_session.add_draft("Second draft", "writer")
            assert len(mock_session.drafts) == 2
            assert mock_session.drafts[1]["version"] == 2

    def test_latest_draft(self, mock_session):
        with patch.object(mock_session, "save"):
            mock_session.add_draft("First draft", "writer")
            mock_session.add_draft("Revised draft", "writer")
            latest = mock_session.latest_draft()
            assert latest["content"] == "Revised draft"
            assert latest["version"] == 2

    def test_latest_draft_empty(self, mock_session):
        assert mock_session.latest_draft() is None

    def test_summary_output(self, mock_session):
        summary = mock_session.summary()
        assert "test" in summary.lower()
        assert "briefing" in summary
        assert "writer" in summary
        assert "Pipeline" in summary

    def test_summary_with_drafts(self, mock_session):
        with patch.object(mock_session, "save"):
            mock_session.add_draft("Some content", "writer")
            summary = mock_session.summary()
            assert "1 version(s)" in summary

    def test_summary_with_context_files(self, mock_session):
        mock_session.context_files = ["path/to/file1.md", "path/to/file2.md"]
        summary = mock_session.summary()
        assert "file1.md" in summary
        assert "file2.md" in summary

    def test_pipeline_display_in_summary(self, mock_session):
        """The summary should show pipeline progress."""
        with patch.object(mock_session, "save"):
            mock_session.advance_pipeline()  # Move past writer
            summary = mock_session.summary()
            assert "done: writer" in summary
            assert "reviewer (active)" in summary


# ---------------------------------------------------------------------------
# Start pipeline (integration-ish)
# ---------------------------------------------------------------------------


class TestStartPipeline:
    def test_start_pipeline_auto_detects_type(self, routing_config):
        with patch("realize_core.pipeline.session.CreativeSession.save"):
            session = start_pipeline(
                system_key="test",
                system_config=routing_config,
                user_id="user1",
                message="write a blog post about market trends",
            )
            assert session.task_type in ("content", "strategy", "general")
            assert session.system_key == "test"
            assert len(session.pipeline) > 0

    def test_start_pipeline_explicit_type(self, routing_config):
        with patch("realize_core.pipeline.session.CreativeSession.save"):
            session = start_pipeline(
                system_key="test",
                system_config=routing_config,
                user_id="user1",
                message="anything",
                task_type="content",
            )
            assert session.task_type == "content"
            assert session.pipeline == ["writer", "reviewer", "gatekeeper"]

    def test_start_pipeline_initial_state(self, routing_config):
        with patch("realize_core.pipeline.session.CreativeSession.save"):
            session = start_pipeline(
                system_key="test",
                system_config=routing_config,
                user_id="user1",
                message="write a blog",
                task_type="content",
            )
            assert session.stage == "briefing"
            assert session.pipeline_index == 0
            assert session.active_agent == "writer"
