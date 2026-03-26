"""
Tests for Vertical Template Marketplace — Intent 4.3.

Covers:
- TemplateManifest model
- load_template_manifest() from YAML
- validate_template()
- install_template()
- TemplateRegistry
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from realize_core.templates.marketplace import (
    TemplateManifest,
    TemplateRegistry,
    install_template,
    load_template_manifest,
    validate_template,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_template(base: Path, name: str = "Test Template", add_agent: bool = True) -> Path:
    """Create a minimal valid template directory."""
    template_dir = base / name.lower().replace(" ", "_")
    template_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "description": "A test template",
        "version": "1.0.0",
        "author": "Test",
        "vertical": "agency",
        "tags": ["test"],
    }
    (template_dir / "template.yaml").write_text(yaml.dump(manifest), encoding="utf-8")

    if add_agent:
        (template_dir / "agents").mkdir(exist_ok=True)
        (template_dir / "agents" / "writer.md").write_text("# Writer Agent\n", encoding="utf-8")

    return template_dir


# ---------------------------------------------------------------------------
# TemplateManifest
# ---------------------------------------------------------------------------


class TestTemplateManifest:
    def test_create(self):
        m = TemplateManifest(name="Test", description="A test", version="1.0")
        assert m.name == "Test"
        assert m.version == "1.0"

    def test_serialization(self):
        m = TemplateManifest(name="Test", author="Me", tags=["a", "b"])
        d = m.to_dict()
        assert d["name"] == "Test"
        assert d["author"] == "Me"
        assert d["tags"] == ["a", "b"]

    def test_from_dict(self):
        d = {"name": "FromDict", "version": "2.0", "vertical": "saas"}
        m = TemplateManifest.from_dict(d)
        assert m.name == "FromDict"
        assert m.version == "2.0"
        assert m.vertical == "saas"


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_load(self, tmp_path):
        tdir = _create_template(tmp_path)
        manifest = load_template_manifest(tdir)
        assert manifest is not None
        assert manifest.name == "Test Template"

    def test_missing(self, tmp_path):
        assert load_template_manifest(tmp_path / "nope") is None

    def test_invalid_yaml(self, tmp_path):
        tdir = tmp_path / "bad"
        tdir.mkdir()
        (tdir / "template.yaml").write_text("[[[", encoding="utf-8")
        assert load_template_manifest(tdir) is None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_template(self, tmp_path):
        tdir = _create_template(tmp_path)
        valid, errors = validate_template(tdir)
        assert valid is True
        assert len(errors) == 0

    def test_missing_manifest(self, tmp_path):
        tdir = tmp_path / "empty"
        tdir.mkdir()
        (tdir / "agents").mkdir()
        (tdir / "agents" / "a.md").write_text("x", encoding="utf-8")
        valid, errors = validate_template(tdir)
        assert valid is False
        assert any("template.yaml" in e for e in errors)

    def test_no_agents_or_skills(self, tmp_path):
        tdir = _create_template(tmp_path, add_agent=False)
        valid, errors = validate_template(tdir)
        assert valid is False
        assert any("agent or skill" in e for e in errors)


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


class TestInstallation:
    def test_install(self, tmp_path):
        tdir = _create_template(tmp_path / "src")
        target = tmp_path / "dest"
        ok, msg = install_template(tdir, target)
        assert ok is True
        assert target.exists()
        assert (target / "template.yaml").exists()

    def test_install_existing_no_overwrite(self, tmp_path):
        tdir = _create_template(tmp_path / "src")
        target = tmp_path / "dest"
        target.mkdir()
        ok, msg = install_template(tdir, target, overwrite=False)
        assert ok is False

    def test_install_with_overwrite(self, tmp_path):
        tdir = _create_template(tmp_path / "src")
        target = tmp_path / "dest"
        target.mkdir()
        ok, msg = install_template(tdir, target, overwrite=True)
        assert ok is True

    def test_install_missing_source(self, tmp_path):
        ok, msg = install_template(tmp_path / "nope", tmp_path / "dest")
        assert ok is False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestTemplateRegistry:
    def test_register_and_list(self, tmp_path):
        tdir = _create_template(tmp_path)
        registry = TemplateRegistry()
        ok, msg = registry.register_template(tdir)
        assert ok is True
        assert registry.count == 1
        templates = registry.list_templates()
        assert len(templates) == 1
        assert templates[0].name == "Test Template"

    def test_filter_by_vertical(self, tmp_path):
        _tdir1 = _create_template(tmp_path / "a", name="Agency Template")
        registry = TemplateRegistry()
        registry.register_template(_tdir1)
        agency = registry.list_templates(vertical="agency")
        saas = registry.list_templates(vertical="saas")
        assert len(agency) == 1
        assert len(saas) == 0

    def test_get_template(self, tmp_path):
        tdir = _create_template(tmp_path)
        registry = TemplateRegistry()
        registry.register_template(tdir)
        t = registry.get_template("Test Template")
        assert t is not None

    def test_scan_directory(self, tmp_path):
        _create_template(tmp_path, name="T1")
        _create_template(tmp_path, name="T2")
        registry = TemplateRegistry(registry_dir=tmp_path)
        assert registry.count == 2

    def test_empty_registry(self):
        registry = TemplateRegistry()
        assert registry.count == 0
        assert registry.list_templates() == []
