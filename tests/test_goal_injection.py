"""
Tests for Workspace Goal Injection — Intent 2.2.

Covers:
- Goal loading from GOAL.md file
- Goal loading from config field
- Resolution order (file > config)
- Goal-to-prompt formatting
- Prompt builder goal layer integration
- Graceful handling of missing goals
- Truncation for long goals
"""

import pytest
from realize_core.prompt.goal import _read_goal, goal_to_prompt, load_goal

# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

SAMPLE_GOAL = """# Our Mission

Build the best product in the market.

## This Quarter
- Ship v2.0
- Reach 500 users
- Maintain NPS > 50
"""


@pytest.fixture
def venture_with_goal_file(tmp_path):
    """Create a venture directory with GOAL.md."""
    venture_dir = tmp_path / "systems" / "my-venture"
    venture_dir.mkdir(parents=True)
    goal_file = venture_dir / "GOAL.md"
    goal_file.write_text(SAMPLE_GOAL, encoding="utf-8")
    return tmp_path, {"key": "my-venture", "name": "My Venture"}


@pytest.fixture
def venture_with_config_goal():
    """Config with goal field but no GOAL.md file."""
    return {"goal": "Become the market leader in AI tools.", "name": "AI Venture"}


# ---------------------------------------------------------------------------
#  Goal Loading Tests
# ---------------------------------------------------------------------------


class TestLoadGoal:
    """Test the load_goal function."""

    def test_load_from_goal_file(self, venture_with_goal_file):
        kb_path, system_config = venture_with_goal_file
        goal = load_goal(kb_path, system_config, "my-venture")
        assert "Build the best product" in goal
        assert "Ship v2.0" in goal

    def test_load_from_config_field(self, tmp_path, venture_with_config_goal):
        goal = load_goal(tmp_path, venture_with_config_goal, "ai-venture")
        assert goal == "Become the market leader in AI tools."

    def test_file_takes_priority_over_config(self, venture_with_goal_file):
        kb_path, system_config = venture_with_goal_file
        system_config["goal"] = "This should be ignored"
        goal = load_goal(kb_path, system_config, "my-venture")
        assert "Build the best product" in goal
        assert "ignored" not in goal

    def test_no_goal_returns_empty(self, tmp_path):
        goal = load_goal(tmp_path, {"name": "Empty"}, "empty")
        assert goal == ""

    def test_truncation(self, tmp_path):
        long_goal = "A" * 5000
        goal = load_goal(tmp_path, {"goal": long_goal}, "test", max_chars=100)
        assert len(goal) < 200
        assert "[...truncated]" in goal

    def test_fabric_dir_config(self, tmp_path):
        """Test loading from fabric_dir config key."""
        fabric_dir = tmp_path / "my-fabric"
        fabric_dir.mkdir()
        (fabric_dir / "GOAL.md").write_text("Fabric goal!", encoding="utf-8")
        config = {"fabric_dir": "my-fabric"}
        goal = load_goal(tmp_path, config, "test")
        assert goal == "Fabric goal!"


# ---------------------------------------------------------------------------
#  Goal Formatting Tests
# ---------------------------------------------------------------------------


class TestGoalToPrompt:
    """Test goal_to_prompt formatting."""

    def test_with_system_name(self):
        prompt = goal_to_prompt("Be the best.", "MyVenture")
        assert "## Venture Goal — MyVenture" in prompt
        assert "Be the best." in prompt

    def test_without_system_name(self):
        prompt = goal_to_prompt("Be the best.")
        assert "## Venture Goal\n" in prompt
        assert "Be the best." in prompt

    def test_empty_goal(self):
        result = goal_to_prompt("")
        assert result == ""

    def test_empty_none_goal(self):
        result = goal_to_prompt(None)
        assert result == ""


# ---------------------------------------------------------------------------
#  Read Goal File Tests
# ---------------------------------------------------------------------------


class TestReadGoal:
    """Test the _read_goal helper."""

    def test_read_normal_file(self, tmp_path):
        goal_file = tmp_path / "GOAL.md"
        goal_file.write_text("Test goal", encoding="utf-8")
        result = _read_goal(goal_file, max_chars=1000)
        assert result == "Test goal"

    def test_read_truncates_long_file(self, tmp_path):
        goal_file = tmp_path / "GOAL.md"
        goal_file.write_text("A" * 5000, encoding="utf-8")
        result = _read_goal(goal_file, max_chars=100)
        assert len(result) < 200
        assert "[...truncated]" in result


# ---------------------------------------------------------------------------
#  Prompt Builder Integration Tests
# ---------------------------------------------------------------------------


class TestPromptBuilderGoalIntegration:
    """Test goal layer injection into the prompt builder."""

    def test_goal_layer_in_prompt(self, tmp_path):
        from realize_core.prompt.builder import build_system_prompt

        config = {"goal": "Dominate the market.", "name": "TestVenture"}
        prompt = build_system_prompt(
            kb_path=tmp_path,
            system_config=config,
            system_key="test",
        )
        assert "Venture Goal" in prompt
        assert "Dominate the market." in prompt

    def test_no_goal_no_layer(self, tmp_path):
        from realize_core.prompt.builder import build_system_prompt

        prompt = build_system_prompt(
            kb_path=tmp_path,
            system_config={},
            system_key="test",
        )
        assert "Venture Goal" not in prompt

    def test_goal_priority_is_7(self):
        from realize_core.prompt.builder import _get_layer_priority

        priority = _get_layer_priority("## Venture Goal — Test\nBe the best")
        assert priority == 7
