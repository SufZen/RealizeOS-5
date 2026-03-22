"""Tests for realize_core.skills.executor — multi-step skill execution engine.

Covers:
- SkillContext: variable injection, step result tracking
- Resume context storage and retrieval
- v1 pipeline skill execution (mocked LLM)
- v2 step-based skill execution (mocked LLM, tools)
- Condition step branching
- Human-in-the-loop pausing
"""
import sys
import types
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import date

# Pre-register mock modules so patch() can target them even when
# anthropic SDK is not installed.
if "realize_core.llm.claude_client" not in sys.modules:
    _mock_claude = types.ModuleType("realize_core.llm.claude_client")
    _mock_claude.call_claude = AsyncMock()
    sys.modules["realize_core.llm.claude_client"] = _mock_claude

from realize_core.skills.executor import (
    SkillContext,
    store_skill_resume_context,
    pop_skill_resume_context,
    execute_skill,
    _pending_skill_contexts,
)


# ---------------------------------------------------------------------------
# SkillContext
# ---------------------------------------------------------------------------

class TestSkillContext:
    def test_init(self):
        ctx = SkillContext("write a blog post", "venture1", "user1")
        assert ctx.user_message == "write a blog post"
        assert ctx.system_key == "venture1"
        assert ctx.user_id == "user1"
        assert ctx.step_results == {}
        assert ctx.variables["doc_title"] == "write a blog post"

    def test_inject_user_message(self):
        ctx = SkillContext("AI trends 2026", "venture1", "user1")
        result = ctx.inject("Write about: {user_message}")
        assert result == "Write about: AI trends 2026"

    def test_inject_step_result(self):
        ctx = SkillContext("test", "s1", "u1")
        ctx.step_results["search"] = "Found 3 competitors"
        result = ctx.inject("Based on research: {search}")
        assert result == "Based on research: Found 3 competitors"

    def test_inject_variable(self):
        ctx = SkillContext("test doc", "s1", "u1")
        ctx.variables["output_format"] = "markdown"
        result = ctx.inject("Format: {output_format}")
        assert result == "Format: markdown"

    def test_inject_today_date(self):
        ctx = SkillContext("test", "s1", "u1")
        result = ctx.inject("Report for {today}")
        expected = date.today().isoformat()
        assert expected in result

    def test_inject_multiple_placeholders(self):
        ctx = SkillContext("AI article", "s1", "u1")
        ctx.step_results["draft"] = "First draft content"
        ctx.variables["tone"] = "professional"
        result = ctx.inject("Topic: {user_message}, Tone: {tone}, Draft: {draft}")
        assert "AI article" in result
        assert "professional" in result
        assert "First draft content" in result

    def test_inject_missing_placeholder_unchanged(self):
        ctx = SkillContext("test", "s1", "u1")
        result = ctx.inject("Value: {nonexistent}")
        # Unresolved placeholders remain as-is
        assert "{nonexistent}" in result

    def test_progress_tracking(self):
        ctx = SkillContext("test", "s1", "u1")
        ctx.progress_messages.append("Step 1: done")
        ctx.progress_messages.append("Step 2: done")
        assert len(ctx.progress_messages) == 2


# ---------------------------------------------------------------------------
# Resume context storage
# ---------------------------------------------------------------------------

class TestResumeContext:
    def setup_method(self):
        _pending_skill_contexts.clear()

    def test_store_and_pop(self):
        ctx = SkillContext("msg", "sys", "user1")
        store_skill_resume_context("user1", "email_skill", ctx, [{"id": "step2"}])

        result = pop_skill_resume_context("user1")
        assert result is not None
        assert result["skill_name"] == "email_skill"
        assert len(result["remaining_steps"]) == 1

    def test_pop_removes_context(self):
        ctx = SkillContext("msg", "sys", "user1")
        store_skill_resume_context("user1", "skill", ctx, [])

        pop_skill_resume_context("user1")
        # Second pop should return None
        assert pop_skill_resume_context("user1") is None

    def test_pop_nonexistent_user(self):
        assert pop_skill_resume_context("nonexistent_user") is None

    def test_overwrite_previous_context(self):
        ctx1 = SkillContext("first", "sys", "user1")
        ctx2 = SkillContext("second", "sys", "user1")

        store_skill_resume_context("user1", "skill_a", ctx1, [])
        store_skill_resume_context("user1", "skill_b", ctx2, [])

        result = pop_skill_resume_context("user1")
        assert result["skill_name"] == "skill_b"


# ---------------------------------------------------------------------------
# v1 pipeline execution (mocked)
# ---------------------------------------------------------------------------

class TestV1Pipeline:
    @pytest.mark.asyncio
    async def test_v1_single_agent(self):
        """v1 skill with single agent pipeline."""
        skill = {
            "name": "simple_skill",
            "_version": 1,
            "pipeline": ["writer"],
        }
        with patch("realize_core.llm.claude_client.call_claude", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Generated blog post content"

            # Need to also patch build_system_prompt
            with patch("realize_core.prompt.builder.build_system_prompt", return_value="system prompt"):
                # Import the private function for direct testing
                from realize_core.skills.executor import _execute_v1_pipeline
                result = await _execute_v1_pipeline(
                    skill, "write a blog post", "test", "user1",
                    None, None, None, "api",
                )
                assert "Generated blog post" in result

    @pytest.mark.asyncio
    async def test_v1_multi_agent_pipeline(self):
        """v1 skill with multi-agent pipeline passes previous outputs."""
        skill = {
            "name": "content_pipeline",
            "_version": 1,
            "pipeline": ["writer", "reviewer"],
        }
        call_count = 0

        async def mock_claude(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "Draft: AI is transforming business"
            return "APPROVED: Polished content ready"

        with patch("realize_core.llm.claude_client.call_claude", side_effect=mock_claude):
            with patch("realize_core.prompt.builder.build_system_prompt", return_value="prompt"):
                from realize_core.skills.executor import _execute_v1_pipeline
                result = await _execute_v1_pipeline(
                    skill, "write about AI", "test", "user1",
                    None, None, None, "api",
                )
                assert call_count == 2
                assert "APPROVED" in result

    @pytest.mark.asyncio
    async def test_v1_empty_pipeline(self):
        """v1 skill with no pipeline defaults to orchestrator."""
        skill = {
            "name": "default_skill",
            "_version": 1,
            "pipeline": [],
        }
        with patch("realize_core.llm.claude_client.call_claude", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Response"
            with patch("realize_core.prompt.builder.build_system_prompt", return_value="prompt"):
                from realize_core.skills.executor import _execute_v1_pipeline
                result = await _execute_v1_pipeline(
                    skill, "hello", "test", "user1",
                    None, None, None, "api",
                )
                # Empty pipeline should return the fallback message
                assert result == "No output from pipeline."


# ---------------------------------------------------------------------------
# v2 step execution (mocked)
# ---------------------------------------------------------------------------

class TestV2Steps:
    @pytest.mark.asyncio
    async def test_v2_no_steps(self):
        """v2 skill with empty steps returns a message."""
        skill = {
            "name": "empty_skill",
            "_version": 2,
            "steps": [],
        }
        from realize_core.skills.executor import _execute_v2_steps
        result = await _execute_v2_steps(
            skill, "hello", "test", "user1",
            None, None, None, "api",
        )
        assert "no steps" in result.lower() or "no output" in result.lower()

    @pytest.mark.asyncio
    async def test_v2_agent_step(self):
        """v2 skill executing a single agent step."""
        skill = {
            "name": "agent_skill",
            "_version": 2,
            "steps": [
                {"id": "draft", "type": "agent", "agent": "writer"},
            ],
        }
        with patch("realize_core.llm.claude_client.call_claude", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Drafted content"
            with patch("realize_core.prompt.builder.build_system_prompt", return_value="prompt"):
                from realize_core.skills.executor import _execute_v2_steps
                result = await _execute_v2_steps(
                    skill, "write article", "test", "user1",
                    None, None, None, "api",
                )
                assert result == "Drafted content"


# ---------------------------------------------------------------------------
# Condition steps
# ---------------------------------------------------------------------------

class TestConditionStep:
    @pytest.mark.asyncio
    async def test_condition_skip(self):
        from realize_core.skills.executor import _execute_condition_step, SkillContext
        step = {
            "type": "condition",
            "check": "{previous_result}",
            "branches": {
                "no": "skip",
                "yes": "continue",
            },
        }
        ctx = SkillContext("test", "s1", "u1")
        ctx.step_results["previous_result"] = "No, skip this"
        result = await _execute_condition_step(step, ctx)
        assert result == "__SKIP__"

    @pytest.mark.asyncio
    async def test_condition_stop(self):
        from realize_core.skills.executor import _execute_condition_step, SkillContext
        step = {
            "type": "condition",
            "check": "{check_val}",
            "branches": {
                "abort": "stop",
            },
        }
        ctx = SkillContext("test", "s1", "u1")
        ctx.step_results["check_val"] = "Must abort now"
        result = await _execute_condition_step(step, ctx)
        assert result == "__STOP__"

    @pytest.mark.asyncio
    async def test_condition_default_continue(self):
        from realize_core.skills.executor import _execute_condition_step, SkillContext
        step = {
            "type": "condition",
            "check": "{val}",
            "branches": {
                "nothing_matches": "skip",
                "default": "continue",
            },
        }
        ctx = SkillContext("test", "s1", "u1")
        ctx.step_results["val"] = "something else entirely"
        result = await _execute_condition_step(step, ctx)
        assert "continue" in result.lower()


# ---------------------------------------------------------------------------
# Human-in-the-loop steps
# ---------------------------------------------------------------------------

class TestHumanStep:
    @pytest.mark.asyncio
    async def test_human_step_returns_question(self):
        from realize_core.skills.executor import _execute_human_step, SkillContext
        step = {
            "type": "human",
            "question": "Should I send this email?",
        }
        ctx = SkillContext("test", "s1", "u1")
        result = await _execute_human_step(step, ctx)
        assert "__HUMAN_INPUT_NEEDED__" in result
        assert "send this email" in result

    @pytest.mark.asyncio
    async def test_human_step_injects_variables(self):
        from realize_core.skills.executor import _execute_human_step, SkillContext
        step = {
            "type": "human",
            "question": "Send email about {user_message}?",
        }
        ctx = SkillContext("meeting tomorrow", "s1", "u1")
        result = await _execute_human_step(step, ctx)
        assert "meeting tomorrow" in result


# ---------------------------------------------------------------------------
# execute_skill dispatcher
# ---------------------------------------------------------------------------

class TestExecuteSkill:
    @pytest.mark.asyncio
    async def test_dispatches_to_v1(self):
        skill = {"name": "test", "_version": 1, "pipeline": ["writer"]}
        with patch("realize_core.skills.executor._execute_v1_pipeline", new_callable=AsyncMock) as mock:
            mock.return_value = "v1 result"
            result = await execute_skill(skill, "msg", "sys", "u1")
            mock.assert_called_once()
            assert result == "v1 result"

    @pytest.mark.asyncio
    async def test_dispatches_to_v2(self):
        skill = {"name": "test", "_version": 2, "steps": []}
        with patch("realize_core.skills.executor._execute_v2_steps", new_callable=AsyncMock) as mock:
            mock.return_value = "v2 result"
            result = await execute_skill(skill, "msg", "sys", "u1")
            mock.assert_called_once()
            assert result == "v2 result"

    @pytest.mark.asyncio
    async def test_default_version_is_v1(self):
        """Skills without _version should default to v1."""
        skill = {"name": "test", "pipeline": ["writer"]}
        with patch("realize_core.skills.executor._execute_v1_pipeline", new_callable=AsyncMock) as mock:
            mock.return_value = "v1 default"
            result = await execute_skill(skill, "msg", "sys", "u1")
            mock.assert_called_once()
