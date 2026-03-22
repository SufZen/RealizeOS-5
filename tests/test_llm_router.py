"""Tests for realize_core.llm.router — task classification and model selection.

Covers:
- All task type classifications (simple, content, reasoning, financial, etc.)
- Edge cases: empty message, short message, mixed keywords, case insensitivity
- Model selection mapping and default fallback
- Self-tuning quality override mechanism
"""
from unittest.mock import patch

from realize_core.llm.router import (
    COMPLEX_KEYWORDS,
    CONTENT_KEYWORDS,
    FINANCIAL_KEYWORDS,
    GOOGLE_KEYWORDS,
    REASONING_KEYWORDS,
    SIMPLE_KEYWORDS,
    WEB_ACTION_KEYWORDS,
    WEB_RESEARCH_KEYWORDS,
    _get_quality_override,
    classify_task,
    select_model,
)

# ---------------------------------------------------------------------------
# Task classification
# ---------------------------------------------------------------------------

class TestClassifyTask:
    """Test task classification for all supported types."""

    # Simple tasks
    def test_simple_greeting(self):
        assert classify_task("hello") == "simple"

    def test_simple_thanks(self):
        assert classify_task("thanks") == "simple"

    def test_simple_explain(self):
        assert classify_task("explain how this works") == "simple"

    def test_simple_status(self):
        assert classify_task("show me the status") == "simple"

    def test_simple_help(self):
        assert classify_task("help me understand this") == "simple"

    # Content tasks
    def test_content_write(self):
        assert classify_task("write a blog post about AI") == "content"

    def test_content_newsletter(self):
        assert classify_task("write a newsletter for our clients") == "content"

    def test_content_linkedin(self):
        assert classify_task("create a linkedin post") == "content"

    def test_content_headline(self):
        assert classify_task("write a headline for our campaign") == "content"

    # Financial tasks
    def test_financial_roi(self):
        assert classify_task("what's the roi on this deal") == "financial"

    def test_financial_revenue(self):
        assert classify_task("what's our revenue projection for Q2") == "financial"

    def test_financial_budget(self):
        assert classify_task("review the budget breakdown") == "financial"

    def test_financial_cash_flow(self):
        assert classify_task("analyze the cash flow statement") == "financial"

    # Reasoning tasks
    def test_reasoning_analyze(self):
        assert classify_task("analyze our market positioning") == "reasoning"

    def test_reasoning_strategy(self):
        assert classify_task("analyze our market positioning strategy") in ("reasoning", "strategy")

    def test_reasoning_contract(self):
        assert classify_task("review this contract for issues") == "reasoning"

    def test_reasoning_architecture(self):
        assert classify_task("design the system architecture") == "reasoning"

    # Complex tasks
    def test_complex_cross_system(self):
        assert classify_task("cross-system analysis of all ventures") == "complex"

    def test_complex_portfolio(self):
        assert classify_task("portfolio review across all systems") == "complex"

    def test_complex_ecosystem(self):
        assert classify_task("review our ecosystem strategy") == "complex"

    # Google Workspace tasks
    def test_google_email(self):
        assert classify_task("check my emails from today") == "google"

    def test_google_calendar(self):
        assert classify_task("what's on my calendar this week") == "google"

    def test_google_drive(self):
        assert classify_task("save this to google drive") == "google"

    # Web research tasks
    def test_web_research_search(self):
        assert classify_task("search the web for latest AI news") == "web_research"

    def test_web_research_lookup(self):
        assert classify_task("look up competitor pricing") == "web_research"

    def test_web_research_browse(self):
        assert classify_task("browse the latest market data") == "web_research"

    # Web action tasks
    def test_web_action_post(self):
        assert classify_task("post on linkedin") == "web_action"

    def test_web_action_navigate(self):
        assert classify_task("navigate to the registration page") == "web_action"

    # Edge cases
    def test_empty_message_defaults_to_simple(self):
        """Empty string should default to 'simple'."""
        result = classify_task("")
        assert result == "simple"

    def test_short_message_defaults_to_simple(self):
        """Very short unclassifiable message defaults to simple."""
        result = classify_task("ok")
        assert result == "simple"

    def test_case_insensitive(self):
        """Classification is case-insensitive."""
        assert classify_task("WRITE A BLOG POST") == "content"
        assert classify_task("What's Our REVENUE?") == "financial"

    def test_google_takes_priority_over_content(self):
        """Google keywords take priority because they're checked first."""
        result = classify_task("draft email about the newsletter")
        assert result == "google"  # "email" keyword matches Google first

    def test_unclassifiable_defaults_to_simple(self):
        """Messages with no matching keywords default to simple."""
        result = classify_task("abcdef xyz 12345")
        assert result == "simple"

    def test_general_question_reasonable(self):
        """General questions get a reasonable classification."""
        result = classify_task("what should we focus on next quarter")
        assert result in ("general", "strategy", "simple", "reasoning")


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------

class TestSelectModel:
    """Test model selection from task type."""

    def test_simple_routes_to_flash(self):
        model = select_model("simple")
        assert "flash" in model.lower() or "gemini" in model.lower()

    def test_content_routes_to_sonnet(self):
        model = select_model("content")
        assert "sonnet" in model.lower() or "claude" in model.lower()

    def test_reasoning_routes_to_sonnet(self):
        model = select_model("reasoning")
        assert "sonnet" in model.lower() or "claude" in model.lower()

    def test_financial_routes_to_sonnet(self):
        model = select_model("financial")
        assert "sonnet" in model.lower() or "claude" in model.lower()

    def test_complex_routes_to_opus(self):
        model = select_model("complex")
        assert "opus" in model.lower() or "claude" in model.lower()

    def test_google_routes_to_claude(self):
        """Google tasks require Claude for tool_use."""
        model = select_model("google")
        assert "sonnet" in model.lower() or "claude" in model.lower()

    def test_web_research_routes_to_claude(self):
        model = select_model("web_research")
        assert "sonnet" in model.lower() or "claude" in model.lower()

    def test_web_action_routes_to_claude(self):
        model = select_model("web_action")
        assert "sonnet" in model.lower() or "claude" in model.lower()

    def test_unknown_task_type_defaults_to_flash(self):
        """Unknown task types fall back to cheapest model."""
        model = select_model("unknown_type_xyz")
        assert "flash" in model.lower() or "gemini" in model.lower()

    def test_all_valid_types_return_string(self):
        """Every valid task type returns a non-empty string."""
        valid_types = [
            "simple", "content", "reasoning", "financial",
            "complex", "google", "web_research", "web_action",
        ]
        for task_type in valid_types:
            model = select_model(task_type)
            assert isinstance(model, str)
            assert len(model) > 0


# ---------------------------------------------------------------------------
# Quality override (self-tuning)
# ---------------------------------------------------------------------------

class TestQualityOverride:
    def test_no_signals_returns_none(self):
        """When no feedback signals exist, no override."""
        import sys
        with patch.dict(sys.modules, {"realize_core.memory.store": None}):
            result = _get_quality_override("simple")
            assert result is None

    def test_import_error_handled(self):
        """If memory module isn't available, override returns None gracefully."""
        # This should not raise — the function catches the ImportError
        result = _get_quality_override("simple")
        # Result depends on whether memory module exists; just verify no crash
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# Keyword sets are non-empty
# ---------------------------------------------------------------------------

class TestKeywordSetsIntegrity:
    """Ensure keyword sets haven't been accidentally emptied."""

    def test_complex_keywords_exist(self):
        assert len(COMPLEX_KEYWORDS) > 0

    def test_financial_keywords_exist(self):
        assert len(FINANCIAL_KEYWORDS) > 0

    def test_reasoning_keywords_exist(self):
        assert len(REASONING_KEYWORDS) > 0

    def test_content_keywords_exist(self):
        assert len(CONTENT_KEYWORDS) > 0

    def test_simple_keywords_exist(self):
        assert len(SIMPLE_KEYWORDS) > 0

    def test_google_keywords_exist(self):
        assert len(GOOGLE_KEYWORDS) > 0

    def test_web_research_keywords_exist(self):
        assert len(WEB_RESEARCH_KEYWORDS) > 0

    def test_web_action_keywords_exist(self):
        assert len(WEB_ACTION_KEYWORDS) > 0
