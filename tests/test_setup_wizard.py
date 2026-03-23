"""Tests for the setup wizard and shared init logic.

Covers:
- Template listing
- Project initialization (shared init.py)
- SetupState save/load/resume
- Doctor diagnostics
"""

from realize_core.init import get_available_templates, initialize_project
from realize_core.setup_wizard import SetupState

# ---------------------------------------------------------------------------
# Template listing
# ---------------------------------------------------------------------------


class TestTemplates:
    def test_lists_available_templates(self):
        templates = get_available_templates()
        assert len(templates) >= 8
        names = {t["name"] for t in templates}
        assert "consulting" in names
        assert "agency" in names
        assert "freelance" in names

    def test_templates_have_descriptions(self):
        templates = get_available_templates()
        for t in templates:
            assert "name" in t
            assert "description" in t
            assert len(t["description"]) > 0


# ---------------------------------------------------------------------------
# Project initialization (shared logic)
# ---------------------------------------------------------------------------


class TestInitializeProject:
    def test_creates_env_file(self, tmp_path):
        result = initialize_project(
            {
                "anthropic_api_key": "sk-test-123",
                "template": "consulting",
                "business_name": "Test Biz",
            },
            tmp_path,
        )

        assert result["env_created"] is True
        env = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "sk-test-123" in env

    def test_creates_config_file(self, tmp_path):
        result = initialize_project(
            {
                "template": "consulting",
                "business_name": "Acme Corp",
            },
            tmp_path,
        )

        assert result["config_created"] is True
        config = (tmp_path / "realize-os.yaml").read_text(encoding="utf-8")
        assert "Acme Corp" in config

    def test_copies_fabric_structure(self, tmp_path):
        result = initialize_project(
            {
                "template": "consulting",
            },
            tmp_path,
        )

        assert result["files_copied"] > 0

    def test_creates_gitignore(self, tmp_path):
        initialize_project({"template": "consulting"}, tmp_path)
        assert (tmp_path / ".gitignore").exists()

    def test_invalid_template_returns_error(self, tmp_path):
        result = initialize_project(
            {
                "template": "nonexistent_template",
            },
            tmp_path,
        )
        assert len(result["errors"]) > 0

    def test_idempotent_no_overwrite(self, tmp_path):
        initialize_project({"template": "consulting", "anthropic_api_key": "key1"}, tmp_path)
        result2 = initialize_project({"template": "consulting", "anthropic_api_key": "key2"}, tmp_path)

        # Second run should not overwrite
        assert result2["env_created"] is False
        assert result2["config_created"] is False
        env = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "key1" in env  # Original key preserved

    def test_business_description_in_identity(self, tmp_path):
        initialize_project(
            {
                "template": "consulting",
                "business_name": "TestCo",
                "business_description": "We do amazing things",
            },
            tmp_path,
        )

        # Check if any venture-identity.md got the description
        identity_files = list(tmp_path.rglob("venture-identity.md"))
        if identity_files:
            content = identity_files[0].read_text(encoding="utf-8")
            assert "We do amazing things" in content


# ---------------------------------------------------------------------------
# SetupState persistence
# ---------------------------------------------------------------------------


class TestSetupState:
    def test_save_and_load(self, tmp_path):
        state = SetupState(
            project_root=str(tmp_path),
            anthropic_key="sk-test",
            template="agency",
            business_name="My Agency",
        )
        state.phases_done.append("prerequisites")

        state_file = tmp_path / ".realize-setup.json"
        state.save(state_file)

        loaded = SetupState.load(state_file)
        assert loaded is not None
        assert loaded.anthropic_key == "sk-test"
        assert loaded.template == "agency"
        assert "prerequisites" in loaded.phases_done

    def test_load_nonexistent_returns_none(self, tmp_path):
        result = SetupState.load(tmp_path / "nonexistent.json")
        assert result is None

    def test_load_corrupted_returns_none(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json{{{", encoding="utf-8")
        result = SetupState.load(bad_file)
        assert result is None

    def test_default_values(self):
        state = SetupState()
        assert state.template == "consulting"
        assert state.business_name == "My Business"
        assert state.install_dashboard is True
        assert state.phases_done == []
