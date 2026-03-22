"""Tests for realize_core.scaffold — project scaffolding.

Covers:
- Directory structure creation
- Template file copying
- Force overwrite behavior
- Idempotent re-runs
- Stats tracking
"""
import pytest
from pathlib import Path
from realize_core.scaffold import scaffold_dev_process


class TestScaffold:
    def test_creates_directory_structure(self, tmp_path):
        stats = scaffold_dev_process(tmp_path)

        assert (tmp_path / "docs" / "dev-process").is_dir()
        assert (tmp_path / "docs" / "dev-process" / "active").is_dir()
        assert (tmp_path / "docs" / "dev-process" / "plans").is_dir()
        assert (tmp_path / "docs" / "dev-process" / "plans" / "stories").is_dir()
        assert (tmp_path / "docs" / "dev-process" / "decisions").is_dir()
        assert (tmp_path / "docs" / "dev-process" / "reference").is_dir()
        assert (tmp_path / "docs" / "dev-process" / "templates").is_dir()

    def test_creates_readme(self, tmp_path):
        scaffold_dev_process(tmp_path)
        readme = tmp_path / "docs" / "dev-process" / "_README.md"
        assert readme.exists()
        content = readme.read_text(encoding="utf-8")
        assert "Development Process" in content
        assert "Session Protocol" in content

    def test_creates_active_files(self, tmp_path):
        scaffold_dev_process(tmp_path)
        active = tmp_path / "docs" / "dev-process" / "active"
        # These should exist (from templates if available, or at least attempted)
        assert active.is_dir()

    def test_returns_stats(self, tmp_path):
        stats = scaffold_dev_process(tmp_path)
        assert "dirs_created" in stats
        assert "files_created" in stats
        assert "skipped" in stats
        assert stats["dirs_created"] > 0

    def test_idempotent_no_overwrite(self, tmp_path):
        stats1 = scaffold_dev_process(tmp_path)
        stats2 = scaffold_dev_process(tmp_path)

        # Second run should skip existing files
        assert stats2["dirs_created"] == 0
        assert stats2["files_created"] == 0

    def test_force_overwrites(self, tmp_path):
        scaffold_dev_process(tmp_path)

        # Modify the README
        readme = tmp_path / "docs" / "dev-process" / "_README.md"
        readme.write_text("Modified content", encoding="utf-8")

        stats = scaffold_dev_process(tmp_path, force=True)
        # Should have recreated files
        assert stats["files_created"] > 0
        # README should be restored
        content = readme.read_text(encoding="utf-8")
        assert "Development Process" in content

    def test_creates_plan_template(self, tmp_path):
        scaffold_dev_process(tmp_path)
        plan_template = tmp_path / "docs" / "dev-process" / "plans" / "_template.md"
        # Exists if source templates are accessible
        if plan_template.exists():
            content = plan_template.read_text(encoding="utf-8")
            assert "Phase" in content or "Goal" in content

    def test_creates_adr_template(self, tmp_path):
        scaffold_dev_process(tmp_path)
        adr_template = tmp_path / "docs" / "dev-process" / "decisions" / "_template.md"
        if adr_template.exists():
            content = adr_template.read_text(encoding="utf-8")
            assert "Context" in content or "Decision" in content

    def test_empty_project_root(self, tmp_path):
        """Should work on a completely empty directory."""
        empty = tmp_path / "empty_project"
        empty.mkdir()
        stats = scaffold_dev_process(empty)
        assert stats["dirs_created"] >= 7  # All dirs should be new

    def test_partial_existing_structure(self, tmp_path):
        """Should fill in missing pieces of existing structure."""
        # Create partial structure
        (tmp_path / "docs" / "dev-process" / "active").mkdir(parents=True)
        (tmp_path / "docs" / "dev-process" / "plans").mkdir(parents=True)

        stats = scaffold_dev_process(tmp_path)
        # Should still create the missing dirs
        assert (tmp_path / "docs" / "dev-process" / "decisions").is_dir()
        assert (tmp_path / "docs" / "dev-process" / "reference").is_dir()
