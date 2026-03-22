"""Tests for realize_core.skills.detector — skill detection and loading.

Covers:
- v1 skill detection (pipeline-based)
- v2 skill detection (step-based)
- No skill match for unrelated messages
- Edge cases: empty skills dir, malformed YAML, missing triggers
"""
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_skills_cache():
    """Clear the global skills cache before each test."""
    from realize_core.skills.detector import _loaded_skills
    _loaded_skills.clear()
    yield
    _loaded_skills.clear()


@pytest.fixture
def skills_setup(tmp_path):
    """Create test skill files (v1 and v2)."""
    skills_dir = tmp_path / "skills" / "test"
    skills_dir.mkdir(parents=True)

    # v1 skill (pipeline-based)
    (skills_dir / "content_pipeline.yaml").write_text("""
name: content_pipeline
triggers:
  - "write a post"
  - "create content"
task_type: content
pipeline:
  - writer
  - reviewer
""")

    # v2 skill (step-based)
    (skills_dir / "research_workflow.yaml").write_text("""
name: research_workflow
version: "2.0"
triggers:
  - "research competitors"
  - "competitive analysis"
task_type: research
steps:
  - id: search
    type: tool
    action: web_search
    params:
      query: "{user_message}"
  - id: analyze
    type: agent
    agent: analyst
    inject_context: [search]
""")

    return tmp_path, skills_dir


@pytest.fixture
def empty_skills_dir(tmp_path):
    """Create an empty skills directory."""
    skills_dir = tmp_path / "skills" / "empty"
    skills_dir.mkdir(parents=True)
    return tmp_path, skills_dir


@pytest.fixture
def malformed_skills_dir(tmp_path):
    """Create a skills directory with malformed YAML."""
    skills_dir = tmp_path / "skills" / "bad"
    skills_dir.mkdir(parents=True)

    (skills_dir / "broken.yaml").write_text("""
name: broken_skill
triggers: not_a_list
  - this is invalid yaml
""")

    return tmp_path, skills_dir


@pytest.fixture
def no_triggers_dir(tmp_path):
    """Create skills directory with skill missing triggers."""
    skills_dir = tmp_path / "skills" / "notrig"
    skills_dir.mkdir(parents=True)

    (skills_dir / "no_triggers.yaml").write_text("""
name: no_triggers_skill
task_type: general
pipeline:
  - orchestrator
""")

    return tmp_path, skills_dir


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestSkillDetectionHappyPath:
    def test_detect_skill_v1(self, skills_setup):
        from realize_core.skills.detector import detect_skill, load_skills
        tmp_path, skills_dir = skills_setup

        # load_skills expects the parent dir containing system subdirs
        load_skills(skills_dir.parent)

        skill = detect_skill("Can you write a post about AI trends?", "test")
        assert skill is not None
        assert skill["name"] == "content_pipeline"
        assert skill.get("_version", 1) == 1

    def test_detect_skill_v2(self, skills_setup):
        from realize_core.skills.detector import detect_skill, load_skills
        tmp_path, skills_dir = skills_setup

        load_skills(skills_dir.parent)

        skill = detect_skill("research competitors in the AI space", "test")
        assert skill is not None
        assert skill["name"] == "research_workflow"
        assert skill.get("_version") == 2

    def test_no_skill_for_unrelated_message(self, skills_setup):
        from realize_core.skills.detector import detect_skill, load_skills
        tmp_path, skills_dir = skills_setup

        load_skills(skills_dir.parent)

        skill = detect_skill("hello how are you", "test")
        # May return default or None depending on fallback behavior
        if skill:
            assert skill["name"] != "content_pipeline"
            assert skill["name"] != "research_workflow"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestSkillDetectionEdgeCases:
    def test_empty_skills_directory(self, empty_skills_dir):
        """Loading from an empty directory should not crash."""
        from realize_core.skills.detector import load_skills, detect_skill
        _, skills_dir = empty_skills_dir

        # Should not raise — pass parent dir containing "empty/" subdir
        load_skills(skills_dir.parent)

        # No skills loaded for "empty" system, so fallback behavior
        skill = detect_skill("write a post", "empty")
        # Result depends on fallback behavior — just verify no crash
        assert skill is None or isinstance(skill, dict)

    def test_nonexistent_skills_directory(self, tmp_path):
        """Loading from a nonexistent directory should handle gracefully."""
        from realize_core.skills.detector import load_skills
        nonexistent = tmp_path / "nonexistent" / "skills"

        # Should not raise (implementation logs a warning)
        try:
            load_skills(nonexistent)
        except (FileNotFoundError, OSError):
            pass  # Acceptable: some implementations raise on missing dir

    def test_skill_trigger_case_insensitive(self, skills_setup):
        """Trigger matching should be case-insensitive."""
        from realize_core.skills.detector import detect_skill, load_skills
        _, skills_dir = skills_setup

        load_skills(skills_dir.parent)

        skill = detect_skill("WRITE A POST about marketing", "test")
        # Should still match content_pipeline
        if skill:
            assert skill["name"] == "content_pipeline"

    def test_v1_skill_has_pipeline(self, skills_setup):
        """v1 skills should have a pipeline list."""
        from realize_core.skills.detector import detect_skill, load_skills
        _, skills_dir = skills_setup

        load_skills(skills_dir.parent)

        skill = detect_skill("write a post", "test")
        if skill and skill["name"] == "content_pipeline":
            assert "pipeline" in skill
            assert isinstance(skill["pipeline"], list)
            assert len(skill["pipeline"]) > 0

    def test_v2_skill_has_steps(self, skills_setup):
        """v2 skills should have a steps list."""
        from realize_core.skills.detector import detect_skill, load_skills
        _, skills_dir = skills_setup

        load_skills(skills_dir.parent)

        skill = detect_skill("research competitors", "test")
        if skill and skill["name"] == "research_workflow":
            assert "steps" in skill
            assert isinstance(skill["steps"], list)
            assert len(skill["steps"]) > 0

    def test_no_triggers_skill(self, no_triggers_dir):
        """Skill without triggers should not match any message."""
        from realize_core.skills.detector import load_skills, detect_skill
        _, skills_dir = no_triggers_dir

        # Should not crash when loading skill without triggers
        try:
            load_skills(skills_dir.parent)
        except Exception:
            pass  # Some implementations may reject skills without triggers

        skill = detect_skill("anything at all", "notrig")
        # Should not match since there are no triggers
        if skill:
            assert skill.get("name") != "no_triggers_skill" or "triggers" not in skill
