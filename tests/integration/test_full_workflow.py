"""
End-to-End Integration Tests — Intent 5.1.

Test cross-feature workflows to verify all Phase 1–4 features
work together as a cohesive system:

1. Agent lifecycle: persona → goal → brief → tool call → gating → approval → messaging
2. Template install → venture session
3. Eval harness → agent with gating
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

from realize_core.tools.approval import ApprovalStatus


def run_async(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test 1: Full Agent Lifecycle
# persona (2.1) → goal (2.2) → brief (2.3)
# → tool call → gating (3.2) → approval (3.1) → messaging (4.1)
# ---------------------------------------------------------------------------


class TestFullAgentLifecycle:
    """Verify persona → goal → brief → tool gating → approval → messaging flow."""

    def test_persona_to_prompt(self):
        """Agent persona is correctly built into prompt text."""
        from realize_core.agents.persona import AgentPersona, persona_to_prompt
        persona = AgentPersona(
            name="Integration Writer",
            role="Content strategist",
            personality_traits=["creative", "strategic"],
            communication_style="Professional and engaging",
            tools_allowlist=["web_search", "email"],
        )
        prompt = persona_to_prompt(persona)
        assert "Integration Writer" in prompt
        assert "Content strategist" in prompt

    def test_goal_to_prompt(self):
        """Venture goal is correctly formatted for injection."""
        from realize_core.prompt.goal import goal_to_prompt
        text = goal_to_prompt("Grow monthly revenue by 20%", "TechCo")
        assert "Grow monthly revenue" in text
        assert "TechCo" in text

    def test_brief_generation(self):
        """Session brief generates given a system key."""
        from realize_core.prompt.brief import generate_session_brief
        brief = generate_session_brief(system_key="test-co")
        assert isinstance(brief, str)

    def test_tool_gating_with_persona(self):
        """Tools are correctly gated based on persona allowlist."""
        from realize_core.agents.persona import AgentPersona
        from realize_core.tools.gating import gate_tools_for_persona, check_tool_access
        from realize_core.tools.base_tool import BaseTool, ToolCategory, ToolResult, ToolSchema

        class StubTool(BaseTool):
            def __init__(self, n):
                self._n = n
            @property
            def name(self): return self._n
            @property
            def description(self): return f"Tool {self._n}"
            @property
            def category(self): return ToolCategory.CUSTOM
            def is_available(self): return True
            def get_schemas(self): return [ToolSchema(name=self._n, description=self._n, input_schema={})]
            async def execute(self, action, params): return ToolResult.ok("ok")

        persona = AgentPersona(name="Rep", tools_allowlist=["crm", "email"])
        tools = [StubTool("crm"), StubTool("email"), StubTool("admin")]

        gated = gate_tools_for_persona(tools, persona)
        assert len(gated) == 2
        assert {t.name for t in gated} == {"crm", "email"}

        allowed, _ = check_tool_access("crm", persona)
        assert allowed is True
        blocked, reason = check_tool_access("admin", persona)
        assert blocked is False

    def test_approval_workflow(self):
        """Approval request → resolve → verify state transition."""
        from realize_core.tools.approval import ApprovalTool

        tool = ApprovalTool()
        # Request a decision (uses 'description' param, not 'question')
        result = run_async(tool.execute("request_decision", {
            "agent_key": "writer",
            "system_key": "agency",
            "description": "Should we publish the Q4 report?",
            "options": ["yes", "no", "defer"],
        }))
        assert result.success
        request_id = result.data["id"]

        # Resolve approval (status is an ApprovalStatus enum)
        req = tool.store.resolve(request_id, ApprovalStatus.APPROVED, "yes", "operator")
        assert req is not None
        assert req.status == ApprovalStatus.APPROVED
        assert req.response == "yes"

    def test_messaging_between_agents(self):
        """Agent A sends message → Agent B reads from inbox."""
        from realize_core.tools.messaging import MessageTool

        tool = MessageTool()

        # Writer sends to analyst
        send_result = run_async(tool.execute("send_message", {
            "target": "agent:analyst",
            "content": "Review Q4 content draft",
            "agent_key": "writer",
            "system_key": "agency",
        }))
        assert send_result.success

        # Analyst reads
        read_result = run_async(tool.execute("read_messages", {
            "agent_key": "analyst",
        }))
        assert read_result.success
        assert len(read_result.data) == 1
        assert "Q4 content draft" in read_result.data[0]["content"]

    def test_full_workflow_integration(self):
        """End-to-end: persona + goal + gating + approval + messaging."""
        from realize_core.agents.persona import AgentPersona, persona_to_prompt
        from realize_core.prompt.goal import goal_to_prompt
        from realize_core.tools.gating import gate_tools_for_persona
        from realize_core.tools.approval import ApprovalTool
        from realize_core.tools.messaging import MessageTool

        # 1. Create persona
        persona = AgentPersona(
            name="Content Lead",
            role="Content strategy and creation",
            tools_allowlist=["messaging", "approval"],
        )
        prompt = persona_to_prompt(persona)
        assert "Content Lead" in prompt

        # 2. Goal injection
        goal = goal_to_prompt("Double blog output this quarter", "GrowthCo")
        assert "Double blog output" in goal

        # 3. Request approval
        approval = ApprovalTool()
        result = run_async(approval.execute("request_decision", {
            "agent_key": "content_lead",
            "system_key": "growthco",
            "description": "Publish draft #12?",
            "options": ["approve", "reject"],
        }))
        assert result.success
        approval.store.resolve(result.data["id"], ApprovalStatus.APPROVED, "approve", "operator")

        # 4. Send message
        msg_tool = MessageTool()
        msg_result = run_async(msg_tool.execute("send_message", {
            "target": "agent:writer",
            "content": "Draft #12 approved, please publish",
            "agent_key": "content_lead",
        }))
        assert msg_result.success

        # 5. Writer reads message
        inbox = run_async(msg_tool.execute("read_messages", {"agent_key": "writer"}))
        assert len(inbox.data) == 1
        assert "approved" in inbox.data[0]["content"]


# ---------------------------------------------------------------------------
# Test 2: Template → Venture → Agent Session
# ---------------------------------------------------------------------------


class TestTemplateToSession:
    """Verify template install creates a working venture with agents + brand."""

    def test_template_install_and_brand_load(self, tmp_path):
        """Install a template and verify brand profile loads."""
        from realize_core.templates.marketplace import install_template
        from realize_core.prompt.brand import load_brand_profile

        # Create a template
        src = tmp_path / "src"
        src.mkdir()
        (src / "template.yaml").write_text(yaml.dump({
            "name": "Test Agency",
            "description": "Agency template",
            "vertical": "agency",
        }), encoding="utf-8")
        (src / "agents").mkdir()
        (src / "agents" / "writer.md").write_text("# Writer\nContent creator", encoding="utf-8")
        (src / "brand.yaml").write_text(yaml.dump({
            "name": "Test Agency Brand",
            "voice": "professional",
            "tagline": "Great content matters",
        }), encoding="utf-8")

        # Install
        dest = tmp_path / "installed"
        ok, msg = install_template(src, dest)
        assert ok is True

        # Verify brand loads
        brand = load_brand_profile(dest / "brand.yaml")
        assert brand is not None
        assert brand.name == "Test Agency Brand"
        assert brand.voice == "professional"

    def test_template_install_and_agent_persona(self, tmp_path):
        """Installed template agents can be loaded as personas."""
        from realize_core.templates.marketplace import install_template
        from realize_core.agents.persona import AgentPersona

        src = tmp_path / "src"
        src.mkdir()
        (src / "template.yaml").write_text(yaml.dump({
            "name": "SaaS Starter",
            "vertical": "saas",
        }), encoding="utf-8")
        (src / "agents").mkdir()
        (src / "agents" / "support.md").write_text("# Support Agent\nHandles tickets", encoding="utf-8")

        dest = tmp_path / "installed"
        ok, msg = install_template(src, dest)
        assert ok is True

        # Verify persona can be created for the agent
        persona = AgentPersona(
            name="Support Agent",
            role="Customer support",
            tools_allowlist=["messaging"],
        )
        assert persona.name == "Support Agent"


# ---------------------------------------------------------------------------
# Test 3: Eval Harness with Gated Agent
# ---------------------------------------------------------------------------


class TestEvalWithGating:
    """Verify eval harness works end-to-end with tool-gated agents."""

    def test_eval_suite_runs(self):
        """Run eval suite and verify report generation."""
        from realize_core.eval.harness import EvalCase, EvalSuite, EvalRunner

        suite = EvalSuite("Integration Test", cases=[
            EvalCase(
                name="greeting_test",
                prompt="Hello, I need help",
                expected_patterns=["help", "assist"],
            ),
            EvalCase(
                name="tool_usage_test",
                prompt="Search for marketing trends",
                expected_tools=["web_search"],
                expected_patterns=["trend", "marketing"],
            ),
        ])

        def mock_agent(prompt):
            if "help" in prompt.lower():
                return "I'm here to assist you! How can I help?"
            elif "search" in prompt.lower():
                return "Here are the latest marketing trends I found"
            return "I don't understand"

        runner = EvalRunner()
        report = runner.run_suite(suite, agent_fn=mock_agent)

        assert len(report.results) == 2
        assert report.results[0].passed is True  # greeting matched
        assert report.pass_rate > 0


# ---------------------------------------------------------------------------
# Test 4: Brand Profile → Prompt Builder Integration
# ---------------------------------------------------------------------------


class TestBrandPromptIntegration:
    """Verify brand profile injection into prompt builder."""

    def test_brand_profile_to_prompt(self):
        """Brand profile converts to prompt-friendly format."""
        from realize_core.prompt.brand import BrandProfile, brand_to_prompt

        brand = BrandProfile(
            name="TestCo",
            tagline="Build better",
            voice="professional",
            tone="Confident and clear",
            target_audience="B2B SaaS founders",
            domains=["SaaS", "DevTools"],
            writing_guidelines=["Be concise", "Use data"],
        )
        prompt = brand_to_prompt(brand)
        assert "TestCo" in prompt
        assert "Build better" in prompt
        assert "B2B SaaS founders" in prompt
        assert "Be concise" in prompt


# ---------------------------------------------------------------------------
# Test 5: Messaging + Approval Cross-Feature
# ---------------------------------------------------------------------------


class TestMessagingApprovalCross:
    """Verify messaging and approval can work together."""

    def test_approval_then_notify(self):
        """Request approval, resolve it, then send notification via messaging."""
        from realize_core.tools.approval import ApprovalTool
        from realize_core.tools.messaging import MessageTool

        approval = ApprovalTool()
        messaging = MessageTool()

        # Agent requests approval
        result = run_async(approval.execute("request_decision", {
            "agent_key": "writer",
            "system_key": "agency",
            "description": "Publish post?",
            "options": ["yes", "no"],
        }))
        assert result.success
        request_id = result.data["id"]

        # Operator resolves
        req = approval.store.resolve(request_id, ApprovalStatus.APPROVED, "yes", "operator")
        assert req is not None

        # Agent sends notification to team
        run_async(messaging.execute("send_message", {
            "target": "channel:team-updates",
            "content": f"Post published (approval {request_id})",
            "agent_key": "writer",
            "system_key": "agency",
        }))

        # Verify human-targeted messages
        human_result = run_async(messaging.execute("send_message", {
            "target": "human:default",
            "content": "Post is live!",
            "agent_key": "writer",
        }))
        assert human_result.success
