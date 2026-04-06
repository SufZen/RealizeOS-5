"""
Product invariants that must NEVER break across sprints.

If any of these tests fail, the product is in a broken state and users
cannot complete basic workflows (init, create venture, serve).

These tests are the guard rail against sprint regression.
"""

from pathlib import Path

import pytest
import yaml

ENGINE_ROOT = Path(__file__).parent.parent
REALIZE_LITE = ENGINE_ROOT / "realize_lite"
TEMPLATES_DIR = ENGINE_ROOT / "templates"

FABRIC_DIRS = ["F-foundations", "A-agents", "B-brain", "R-routines", "I-insights", "C-creations"]


# --- FABRIC Template Invariants ---


class TestFabricTemplate:
    """The default FABRIC venture template must exist and be complete."""

    def test_template_directory_exists(self):
        """FABRIC venture template must exist for scaffold_venture() to work."""
        template = REALIZE_LITE / "systems" / "my-business-1"
        assert template.exists(), (
            f"Missing: {template}\n"
            "scaffold_venture() cannot create new ventures without this template."
        )

    def test_template_has_all_fabric_dirs(self):
        """Template must have all 6 FABRIC directories."""
        template = REALIZE_LITE / "systems" / "my-business-1"
        for d in FABRIC_DIRS:
            assert (template / d).exists(), f"Missing FABRIC directory: {d}/"

    def test_template_has_agents(self):
        """Template must have at least the 4 base agents."""
        agents_dir = REALIZE_LITE / "systems" / "my-business-1" / "A-agents"
        required_agents = ["orchestrator.md", "writer.md", "analyst.md", "reviewer.md"]
        for agent in required_agents:
            assert (agents_dir / agent).exists(), f"Missing agent: {agent}"

    def test_template_agents_match_config_routing(self):
        """Every agent in the default config routing must have a .md file."""
        config_path = REALIZE_LITE / "realize-os.yaml"
        if not config_path.exists():
            pytest.skip("realize-os.yaml not found in realize_lite")

        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        agents_dir = REALIZE_LITE / "systems" / "my-business-1" / "A-agents"

        available = {f.stem.replace("-", "_") for f in agents_dir.glob("*.md") if not f.name.startswith("_")}

        for system in config.get("systems", []):
            for route_type, agent_list in system.get("routing", {}).items():
                if isinstance(agent_list, list):
                    for agent_name in agent_list:
                        agent_key = agent_name.replace("-", "_")
                        assert agent_key in available, (
                            f"Routing '{route_type}' references agent '{agent_name}' "
                            f"but no {agent_name}.md found in A-agents/. "
                            f"Available: {sorted(available)}"
                        )

    def test_template_has_skills(self):
        """Template must have at least one skill YAML file."""
        skills_dir = REALIZE_LITE / "systems" / "my-business-1" / "R-routines" / "skills"
        assert skills_dir.exists(), "Missing skills directory"
        skills = list(skills_dir.glob("*.yaml"))
        assert len(skills) > 0, "No skill YAML files found in R-routines/skills/"


# --- Template YAML Invariants ---


class TestTemplateYamls:
    """Every template YAML must be parseable and have required fields."""

    def test_all_template_yamls_parse(self):
        """Every templates/*.yaml must be valid YAML."""
        for f in TEMPLATES_DIR.glob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                assert isinstance(data, dict), f"{f.name}: parsed as {type(data).__name__}, expected dict"
            except yaml.YAMLError as e:
                pytest.fail(f"{f.name}: YAML parse error: {e}")

    def test_all_template_yamls_have_systems(self):
        """Every template must define at least one system."""
        for f in TEMPLATES_DIR.glob("*.yaml"):
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            systems = data.get("systems", [])
            assert len(systems) > 0, f"{f.name}: missing 'systems' section"

    def test_all_template_yamls_have_routing(self):
        """Every template system must have routing config."""
        for f in TEMPLATES_DIR.glob("*.yaml"):
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            for system in data.get("systems", []):
                routing = system.get("routing", {})
                assert len(routing) > 0, (
                    f"{f.name}: system '{system.get('key', '?')}' has no routing config"
                )

    def test_real_estate_template_exists(self):
        """Primary market template must exist."""
        assert (TEMPLATES_DIR / "real-estate.yaml").exists(), "Missing real-estate.yaml template"


# --- Real Estate Template Invariants ---


class TestRealEstateTemplate:
    """Real estate template must have specialized agents and knowledge."""

    def test_real_estate_fabric_exists(self):
        """Real estate FABRIC directory must exist."""
        fabric_dir = TEMPLATES_DIR / "real-estate"
        assert fabric_dir.exists(), "Missing templates/real-estate/ FABRIC directory"

    def test_real_estate_has_specialized_agents(self):
        """Real estate template must have domain-specific agents."""
        agents_dir = TEMPLATES_DIR / "real-estate" / "A-agents"
        required = ["listing-specialist.md", "market-analyst.md", "deal-analyst.md"]
        for agent in required:
            assert (agents_dir / agent).exists(), f"Missing real estate agent: {agent}"

    def test_real_estate_has_country_knowledge(self):
        """Real estate template must have PT, IT, ES knowledge bases."""
        brain_dir = TEMPLATES_DIR / "real-estate" / "B-brain"
        for country in ["portugal", "italy", "spain"]:
            country_dir = brain_dir / country
            assert country_dir.exists(), f"Missing knowledge base: B-brain/{country}/"
            files = list(country_dir.glob("*.md"))
            assert len(files) >= 2, (
                f"B-brain/{country}/ has only {len(files)} files, expected at least 2"
            )

    def test_real_estate_has_skills(self):
        """Real estate template must have domain-specific skills."""
        skills_dir = TEMPLATES_DIR / "real-estate" / "R-routines" / "skills"
        assert skills_dir.exists(), "Missing real estate skills directory"
        skills = list(skills_dir.glob("*.yaml"))
        assert len(skills) >= 4, f"Only {len(skills)} skills, expected at least 4"

    def test_real_estate_yaml_agents_match_fabric(self):
        """Agents in real-estate.yaml routing must exist in the FABRIC template."""
        yaml_path = TEMPLATES_DIR / "real-estate.yaml"
        agents_dir = TEMPLATES_DIR / "real-estate" / "A-agents"

        config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        available = {f.stem.replace("-", "_") for f in agents_dir.glob("*.md") if not f.name.startswith("_")}

        for system in config.get("systems", []):
            for route_type, agent_list in system.get("routing", {}).items():
                if isinstance(agent_list, list):
                    for agent_name in agent_list:
                        agent_key = agent_name.replace("-", "_")
                        assert agent_key in available, (
                            f"real-estate.yaml routing '{route_type}' references "
                            f"'{agent_name}' but no matching file in A-agents/"
                        )


# --- Init Flow Invariants ---


class TestInitFlow:
    """The init command must produce a working project."""

    def test_realize_lite_exists(self):
        """realize_lite/ directory must exist."""
        assert REALIZE_LITE.exists(), "Missing realize_lite/ directory"

    def test_realize_lite_has_config(self):
        """realize_lite/ must contain realize-os.yaml."""
        assert (REALIZE_LITE / "realize-os.yaml").exists(), "Missing realize_lite/realize-os.yaml"

    def test_realize_lite_has_shared(self):
        """realize_lite/ must have shared identity and preferences."""
        assert (REALIZE_LITE / "shared" / "identity.md").exists(), "Missing shared/identity.md"
        assert (REALIZE_LITE / "shared" / "user-preferences.md").exists(), "Missing shared/user-preferences.md"


# --- Scaffold Function Invariants ---


class TestScaffoldFunction:
    """scaffold_venture() must work end-to-end."""

    def test_scaffold_finds_template(self):
        """_find_venture_template() must return a valid path."""
        from realize_core.scaffold import _find_venture_template

        result = _find_venture_template()
        assert result is not None, "Default venture template not found"
        assert result.exists(), f"Template path {result} does not exist"
        assert (result / "A-agents").exists(), f"Template {result} missing A-agents/"

    def test_scaffold_finds_real_estate_template(self):
        """_find_venture_template('real-estate') must return the specialized template."""
        from realize_core.scaffold import _find_venture_template

        result = _find_venture_template("real-estate")
        assert result is not None, "Real estate venture template not found"
        assert (result / "A-agents" / "listing-specialist.md").exists(), (
            "Real estate template missing listing-specialist agent"
        )

    def test_scaffold_creates_venture(self, tmp_path):
        """scaffold_venture() must create a complete FABRIC structure."""
        # Create minimal project structure
        (tmp_path / "realize-os.yaml").write_text(
            "name: Test\nsystems: []\n", encoding="utf-8"
        )

        from realize_core.scaffold import scaffold_venture

        result = scaffold_venture(str(tmp_path), "test-venture", "Test Venture")
        assert result["created"], f"Scaffold failed: {result.get('error')}"
        assert result["dirs_created"] > 0
        assert result["files_created"] > 0

        # Verify FABRIC structure
        venture_dir = tmp_path / "systems" / "test-venture"
        for d in FABRIC_DIRS:
            assert (venture_dir / d).exists(), f"Created venture missing {d}/"

        # Verify agents exist
        assert (venture_dir / "A-agents" / "orchestrator.md").exists()
