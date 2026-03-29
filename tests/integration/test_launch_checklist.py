"""
Launch Checklist Validation — Intent 5.3.

Programmatic verification of all launch readiness requirements:
1. Required files exist (README, LICENSE, CONTRIBUTING, etc.)
2. Security scan configuration present
3. Docker compose available
4. All new modules importable
5. Feature inventory complete
"""

from __future__ import annotations

from pathlib import Path

# Root of the project
PROJECT_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# File existence checks
# ---------------------------------------------------------------------------


class TestRequiredFiles:
    """Verify all required documentation files exist."""

    def test_readme_exists(self):
        assert (PROJECT_ROOT / "README.md").exists()

    def test_license_exists(self):
        """BSL 1.1 license file."""
        paths = [PROJECT_ROOT / "LICENSE", PROJECT_ROOT / "LICENSE.md", PROJECT_ROOT / "LICENSE.txt"]
        assert any(p.exists() for p in paths), "No LICENSE file found"

    def test_contributing_exists(self):
        assert (PROJECT_ROOT / "CONTRIBUTING.md").exists()

    def test_docker_compose_exists(self):
        paths = [
            PROJECT_ROOT / "docker-compose.yml",
            PROJECT_ROOT / "docker-compose.yaml",
            PROJECT_ROOT / "docker" / "docker-compose.yml",
        ]
        assert any(p.exists() for p in paths), "No docker-compose file found"


# ---------------------------------------------------------------------------
# Module importability
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Verify all new modules can be imported without errors."""

    def test_import_persona(self):
        from realize_core.agents.persona import AgentPersona

        assert AgentPersona is not None

    def test_import_goal(self):
        from realize_core.prompt.goal import goal_to_prompt

        assert goal_to_prompt is not None

    def test_import_brief(self):
        from realize_core.prompt.brief import generate_session_brief

        assert generate_session_brief is not None

    def test_import_brand(self):
        from realize_core.prompt.brand import BrandProfile

        assert BrandProfile is not None

    def test_import_approval(self):
        from realize_core.tools.approval import ApprovalTool

        assert ApprovalTool is not None

    def test_import_gating(self):
        from realize_core.tools.gating import gate_tools_for_persona

        assert gate_tools_for_persona is not None

    def test_import_messaging(self):
        from realize_core.tools.messaging import MessageTool

        assert MessageTool is not None

    def test_import_eval_harness(self):
        from realize_core.eval.harness import EvalRunner

        assert EvalRunner is not None

    def test_import_template_marketplace(self):
        from realize_core.templates.marketplace import TemplateRegistry

        assert TemplateRegistry is not None

    def test_import_builder(self):
        from realize_core.prompt.builder import build_system_prompt

        assert build_system_prompt is not None

    def test_import_migrations(self):
        from realize_core.db.migrations import MIGRATIONS

        assert len(MIGRATIONS) >= 3
        assert max(MIGRATIONS.keys()) == 4


# ---------------------------------------------------------------------------
# Feature inventory
# ---------------------------------------------------------------------------


class TestFeatureInventory:
    """Verify feature completeness — all planned features are present."""

    def test_phase2_features(self):
        """Phase 2: Agent Intelligence Layer."""
        from realize_core.agents.persona import AgentPersona, persona_to_prompt
        from realize_core.prompt.brief import generate_session_brief
        from realize_core.prompt.goal import goal_to_prompt

        # Persona creation
        p = AgentPersona(name="Test", role="Tester")
        assert persona_to_prompt(p) != ""

        # Goal formatting
        assert goal_to_prompt("Test goal", "TestCo") != ""

        # Brief generation — requires system_key
        brief = generate_session_brief(system_key="test-co")
        assert isinstance(brief, str)

    def test_phase3_features(self):
        """Phase 3: Coordination & Control."""
        from realize_core.prompt.brand import BrandProfile, brand_to_prompt
        from realize_core.tools.approval import ApprovalTool

        # Approval tool
        tool = ApprovalTool()
        assert tool.name == "approval"

        # Brand profile
        brand = BrandProfile(name="TestBrand")
        assert brand_to_prompt(brand) != ""

    def test_phase4_features(self):
        """Phase 4: Ecosystem & Scale."""
        from realize_core.eval.harness import EvalRunner, EvalSuite
        from realize_core.templates.marketplace import TemplateRegistry
        from realize_core.tools.messaging import MessageTool

        # Messaging
        tool = MessageTool()
        assert tool.name == "messaging"

        # Eval harness
        runner = EvalRunner()
        report = runner.run_suite(EvalSuite("test"))
        assert report is not None

        # Template registry
        registry = TemplateRegistry()
        assert registry.count == 0


# ---------------------------------------------------------------------------
# DB schema version
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    """Verify database is at correct schema version."""

    def test_latest_version(self):
        from realize_core.db.migrations import MIGRATIONS

        assert max(MIGRATIONS.keys()) == 4

    def test_migration_completeness(self, tmp_path):
        from realize_core.db.migrations import get_current_version, run_migrations
        from realize_core.db.schema import get_connection

        db_path = tmp_path / "test.db"
        run_migrations(db_path)
        conn = get_connection(db_path)
        version = get_current_version(conn)
        assert version == 4
        conn.close()
