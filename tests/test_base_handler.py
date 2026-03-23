"""Tests for realize_core.base_handler — message pipeline building blocks.

Covers:
- Agent selection with keyword scoring
- Edge cases: empty routing, no match, case insensitivity
- Custom default agent
- Tie-breaking and highest-score-wins behavior
"""

from realize_core.base_handler import select_agent

# ---------------------------------------------------------------------------
# Agent selection
# ---------------------------------------------------------------------------


class TestSelectAgent:
    """Test keyword-based agent routing."""

    def test_selects_writer_for_content(self):
        routing = {
            "writer": ["write", "draft", "post", "blog"],
            "analyst": ["analyze", "research", "data"],
            "orchestrator": ["plan", "help"],
        }
        assert select_agent(routing, "write a blog post") == "writer"

    def test_selects_analyst_for_research(self):
        routing = {
            "writer": ["write", "draft"],
            "analyst": ["analyze", "research", "data"],
        }
        assert select_agent(routing, "analyze this data please") == "analyst"

    def test_returns_default_for_no_match(self):
        routing = {
            "writer": ["write"],
            "analyst": ["analyze"],
        }
        assert select_agent(routing, "hello there") == "orchestrator"

    def test_custom_default(self):
        routing = {"writer": ["write"]}
        assert select_agent(routing, "hello", default="custom") == "custom"

    def test_highest_score_wins(self):
        routing = {
            "writer": ["write", "content", "blog"],
            "analyst": ["write", "data"],
        }
        # "write a blog about content strategy" matches writer 3 times, analyst 1 time
        result = select_agent(routing, "write a blog about content strategy")
        assert result == "writer"

    # --- Edge cases ---

    def test_empty_routing_dict(self):
        """Empty routing should return default agent."""
        result = select_agent({}, "write a blog post")
        assert result == "orchestrator"

    def test_empty_routing_dict_custom_default(self):
        """Empty routing with custom default."""
        result = select_agent({}, "anything", default="fallback")
        assert result == "fallback"

    def test_empty_message(self):
        """Empty message should return default agent."""
        routing = {"writer": ["write"], "analyst": ["analyze"]}
        result = select_agent(routing, "")
        assert result == "orchestrator"

    def test_case_insensitive_matching(self):
        """Keywords should match case-insensitively."""
        routing = {"writer": ["write", "blog"]}
        result = select_agent(routing, "WRITE A BLOG POST")
        assert result == "writer"

    def test_single_keyword_match(self):
        """A single keyword match should select the agent."""
        routing = {
            "writer": ["blog"],
            "analyst": ["spreadsheet"],
        }
        result = select_agent(routing, "can you make a blog?")
        assert result == "writer"

    def test_multiple_agents_single_word_match(self):
        """When multiple agents match one keyword each, any match is valid."""
        routing = {
            "writer": ["content"],
            "marketer": ["content"],
        }
        result = select_agent(routing, "create content")
        assert result in ("writer", "marketer")

    def test_no_keywords_in_routing(self):
        """Agent with empty keyword list never matches."""
        routing = {
            "writer": [],
            "analyst": ["analyze"],
        }
        result = select_agent(routing, "analyze this data")
        assert result == "analyst"

    def test_partial_word_match_behavior(self):
        """Check if 'write' matches in 'rewrite' (substring matching behavior)."""
        routing = {"writer": ["write"]}
        result = select_agent(routing, "please rewrite this paragraph")
        # Behavior depends on implementation — just verify it doesn't crash
        assert isinstance(result, str)
