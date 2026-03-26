"""
Tests for Session Startup Brief — Intent 2.3.

Covers:
- Brief generation with various pending items
- Empty sections omitted
- Token budget enforcement
- Session-level caching
- Activity section formatting
- Tasks section formatting
- Approvals section formatting
- KB changes section formatting
"""

import pytest

from realize_core.prompt.brief import (
    generate_session_brief,
    get_or_generate_brief,
    clear_brief_cache,
    _build_activity_section,
    _build_tasks_section,
    _build_approvals_section,
    _build_kb_changes_section,
)


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear brief cache before each test."""
    clear_brief_cache()
    yield
    clear_brief_cache()


@pytest.fixture
def sample_audit_entries():
    return [
        {"action": "message_sent", "details": "Reply to customer inquiry about pricing", "timestamp": "2026-03-26T14:00:00"},
        {"action": "kb_update", "details": "Updated pricing FAQ", "timestamp": "2026-03-26T13:30:00"},
        {"action": "tool_call", "details": "CRM lookup for client Acme Corp", "timestamp": "2026-03-26T12:00:00"},
    ]


@pytest.fixture
def sample_tasks():
    return [
        {"title": "Draft Q2 report", "priority": "high", "due_date": "2026-03-28"},
        {"title": "Review campaign metrics", "priority": "medium"},
        {"title": "Update pricing page", "priority": "low", "due_date": "2026-04-01"},
    ]


@pytest.fixture
def sample_approvals():
    return [
        {"type": "decision", "requested_by": "writer", "description": "Approve blog post for publication"},
        {"type": "credential", "requested_by": "analyst", "description": "Need API key for analytics"},
    ]


@pytest.fixture
def sample_kb_changes():
    return [
        {"file": "pricing-faq.md", "action": "updated"},
        {"file": "team-roster.md", "action": "created"},
    ]


# ---------------------------------------------------------------------------
#  Full Brief Generation
# ---------------------------------------------------------------------------


class TestGenerateSessionBrief:
    """Test the generate_session_brief function."""

    def test_full_brief(self, sample_audit_entries, sample_tasks, sample_approvals, sample_kb_changes):
        brief = generate_session_brief(
            system_key="test",
            recent_audit_entries=sample_audit_entries,
            pending_tasks=sample_tasks,
            pending_approvals=sample_approvals,
            recent_kb_changes=sample_kb_changes,
        )
        assert "## Session Brief" in brief
        assert "Recent Activity" in brief
        assert "Pending Tasks (3)" in brief
        assert "Pending Approvals (2)" in brief
        assert "Recent KB Updates" in brief

    def test_empty_brief(self):
        brief = generate_session_brief(system_key="test")
        assert brief == ""

    def test_only_tasks(self, sample_tasks):
        brief = generate_session_brief(
            system_key="test",
            pending_tasks=sample_tasks,
        )
        assert "## Session Brief" in brief
        assert "Pending Tasks" in brief
        assert "Recent Activity" not in brief

    def test_only_approvals(self, sample_approvals):
        brief = generate_session_brief(
            system_key="test",
            pending_approvals=sample_approvals,
        )
        assert "Pending Approvals" in brief
        assert "Pending Tasks" not in brief

    def test_empty_sections_omitted(self):
        brief = generate_session_brief(
            system_key="test",
            pending_tasks=[],
            pending_approvals=[],
            recent_kb_changes=[],
        )
        assert brief == ""


# ---------------------------------------------------------------------------
#  Individual Section Builders
# ---------------------------------------------------------------------------


class TestActivitySection:
    """Test the activity section builder."""

    def test_with_entries(self, sample_audit_entries):
        section = _build_activity_section(sample_audit_entries, None, "test", 24)
        assert "Recent Activity (24h)" in section
        assert "message_sent" in section
        assert "14:00" in section

    def test_empty(self):
        section = _build_activity_section([], None, "test", 24)
        assert section == ""

    def test_none(self):
        section = _build_activity_section(None, None, "test", 24)
        assert section == ""

    def test_limits_to_5(self):
        entries = [
            {"action": f"action_{i}", "details": f"details_{i}", "timestamp": "2026-03-26T10:00:00"}
            for i in range(8)
        ]
        section = _build_activity_section(entries, None, "test", 24)
        assert "...and 3 more" in section


class TestTasksSection:
    """Test the tasks section builder."""

    def test_with_tasks(self, sample_tasks):
        section = _build_tasks_section(sample_tasks)
        assert "Pending Tasks (3)" in section
        assert "Draft Q2 report" in section
        assert "[high]" in section
        assert "due: 2026-03-28" in section

    def test_empty(self):
        assert _build_tasks_section([]) == ""

    def test_none(self):
        assert _build_tasks_section(None) == ""

    def test_limits_to_5(self):
        tasks = [{"title": f"Task {i}"} for i in range(8)]
        section = _build_tasks_section(tasks)
        assert "...and 3 more" in section


class TestApprovalsSection:
    """Test the approvals section builder."""

    def test_with_approvals(self, sample_approvals):
        section = _build_approvals_section(sample_approvals)
        assert "Pending Approvals (2)" in section
        assert "from writer" in section
        assert "Approve blog post" in section

    def test_empty(self):
        assert _build_approvals_section([]) == ""


class TestKBChangesSection:
    """Test the KB changes section builder."""

    def test_with_changes(self, sample_kb_changes):
        section = _build_kb_changes_section(sample_kb_changes)
        assert "Recent KB Updates" in section
        assert "updated: pricing-faq.md" in section

    def test_empty(self):
        assert _build_kb_changes_section([]) == ""


# ---------------------------------------------------------------------------
#  Session-Level Caching
# ---------------------------------------------------------------------------


class TestBriefCaching:
    """Test session-level brief caching."""

    def test_caches_brief(self, sample_tasks):
        brief1 = get_or_generate_brief("session-1", "test", pending_tasks=sample_tasks)
        brief2 = get_or_generate_brief("session-1", "test")
        assert brief1 == brief2
        assert "Pending Tasks" in brief1

    def test_different_sessions(self, sample_tasks):
        brief1 = get_or_generate_brief("session-1", "test", pending_tasks=sample_tasks)
        brief2 = get_or_generate_brief("session-2", "test")
        assert brief1 != brief2

    def test_clear_cache(self, sample_tasks):
        brief1 = get_or_generate_brief("session-1", "test", pending_tasks=sample_tasks)
        clear_brief_cache()
        brief2 = get_or_generate_brief("session-1", "test")
        assert brief2 == ""  # No tasks provided after cache clear


# ---------------------------------------------------------------------------
#  Token Budget
# ---------------------------------------------------------------------------


class TestTokenBudget:
    """Test that briefs respect the token budget."""

    def test_long_brief_truncated(self):
        """A very long list of items should be truncated."""
        tasks = [{"title": f"Very important task number {i} with extra details and context"} for i in range(100)]
        brief = generate_session_brief(system_key="test", pending_tasks=tasks)
        # Should be truncated to ~500 tokens * 3.5 chars = ~1750 chars
        assert len(brief) < 2000
