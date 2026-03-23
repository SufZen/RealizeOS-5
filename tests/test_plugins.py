"""Tests for Sprint 11 — plugin system and venture export/import.

Covers:
- Plugin discovery from directory
- Plugin loading with on_load hook
- Plugin unloading with on_unload hook
- Tool plugin keyword mapping
- Venture export (zip creation, excludes secrets)
- Venture import (restore from zip)
"""

import zipfile

import pytest
from realize_core.plugins.loader import (
    _plugins,
    discover_plugins,
    get_loaded_plugins,
    get_plugin_keywords,
    load_all_plugins,
    load_plugin,
    unload_plugin,
)
from realize_core.plugins.venture_io import export_venture, import_venture


@pytest.fixture(autouse=True)
def clear_plugins():
    _plugins.clear()
    yield
    _plugins.clear()


# ---------------------------------------------------------------------------
# Plugin Discovery
# ---------------------------------------------------------------------------


class TestPluginDiscovery:
    def test_discover_from_directory(self, tmp_path):
        plugin_dir = tmp_path / "plugins" / "test-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.yaml").write_text(
            "name: test-plugin\nversion: '1.0'\ntype: tool\nentry_point: __init__\n",
            encoding="utf-8",
        )
        (plugin_dir / "__init__.py").write_text("", encoding="utf-8")

        manifests = discover_plugins(tmp_path / "plugins")
        assert len(manifests) == 1
        assert manifests[0]["name"] == "test-plugin"
        assert manifests[0]["type"] == "tool"

    def test_discover_skips_no_manifest(self, tmp_path):
        plugin_dir = tmp_path / "plugins" / "no-manifest"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "__init__.py").write_text("", encoding="utf-8")

        manifests = discover_plugins(tmp_path / "plugins")
        assert len(manifests) == 0

    def test_discover_empty_dir(self, tmp_path):
        (tmp_path / "plugins").mkdir()
        manifests = discover_plugins(tmp_path / "plugins")
        assert manifests == []

    def test_discover_nonexistent_dir(self, tmp_path):
        manifests = discover_plugins(tmp_path / "nonexistent")
        assert manifests == []


# ---------------------------------------------------------------------------
# Plugin Loading
# ---------------------------------------------------------------------------


class TestPluginLoading:
    def _create_plugin(self, tmp_path, name="my-tool", plugin_type="tool", keywords=None, code=""):
        plugin_dir = tmp_path / "plugins" / name
        plugin_dir.mkdir(parents=True)
        kw_str = str(keywords or [])
        (plugin_dir / "plugin.yaml").write_text(
            f"name: {name}\nversion: '1.0'\ntype: {plugin_type}\nentry_point: __init__\nkeywords: {kw_str}\n",
            encoding="utf-8",
        )
        (plugin_dir / "__init__.py").write_text(code, encoding="utf-8")
        return discover_plugins(tmp_path / "plugins")[0]

    def test_load_plugin(self, tmp_path):
        manifest = self._create_plugin(tmp_path, code="LOADED = True")
        assert load_plugin(manifest) is True
        assert "my-tool" in get_loaded_plugins()

    def test_load_calls_on_load(self, tmp_path):
        code = "STATE = []\ndef on_load():\n    STATE.append('loaded')\n"
        manifest = self._create_plugin(tmp_path, code=code)
        load_plugin(manifest)

        import sys

        mod = sys.modules["plugins.my-tool"]
        assert "loaded" in mod.STATE

    def test_unload_calls_on_unload(self, tmp_path):
        code = (
            "STATE = []\ndef on_load():\n    STATE.append('loaded')\ndef on_unload():\n    STATE.append('unloaded')\n"
        )
        manifest = self._create_plugin(tmp_path, code=code)
        load_plugin(manifest)

        import sys

        mod = sys.modules["plugins.my-tool"]
        unload_plugin("my-tool")
        assert "unloaded" in mod.STATE
        assert "my-tool" not in get_loaded_plugins()

    def test_load_all(self, tmp_path):
        self._create_plugin(tmp_path, name="p1")
        self._create_plugin(tmp_path, name="p2")
        count = load_all_plugins(tmp_path / "plugins")
        assert count == 2

    def test_tool_plugin_keywords(self, tmp_path):
        manifest = self._create_plugin(tmp_path, keywords=["search", "lookup"], code="")
        load_plugin(manifest)
        keywords = get_plugin_keywords()
        assert "search" in keywords
        assert "my-tool" in keywords["search"]


# ---------------------------------------------------------------------------
# Venture Export
# ---------------------------------------------------------------------------


class TestVentureExport:
    def _create_venture(self, kb_path, key="testbiz"):
        sys_dir = kb_path / "systems" / key
        (sys_dir / "F-foundations").mkdir(parents=True)
        (sys_dir / "A-agents").mkdir()
        (sys_dir / "R-routines" / "skills").mkdir(parents=True)
        (sys_dir / "F-foundations" / "identity.md").write_text("# Identity", encoding="utf-8")
        (sys_dir / "A-agents" / "writer.md").write_text("# Writer", encoding="utf-8")
        (sys_dir / "R-routines" / "skills" / "seo.yaml").write_text("name: seo", encoding="utf-8")
        return sys_dir

    def test_export_creates_zip(self, tmp_path):
        self._create_venture(tmp_path)
        output = tmp_path / "export.zip"
        result = export_venture("testbiz", tmp_path, output)
        assert result.exists()
        assert zipfile.is_zipfile(result)

    def test_export_includes_files(self, tmp_path):
        self._create_venture(tmp_path)
        output = export_venture("testbiz", tmp_path, tmp_path / "out.zip")
        with zipfile.ZipFile(output) as zf:
            names = zf.namelist()
            assert any("identity.md" in n for n in names)
            assert any("writer.md" in n for n in names)
            assert any("manifest.json" in n for n in names)

    def test_export_excludes_secrets(self, tmp_path):
        self._create_venture(tmp_path)
        secret = tmp_path / "systems" / "testbiz" / ".env"
        secret.write_text("SECRET=value", encoding="utf-8")

        output = export_venture("testbiz", tmp_path, tmp_path / "out.zip")
        with zipfile.ZipFile(output) as zf:
            assert not any(".env" in n for n in zf.namelist())

    def test_export_nonexistent_venture(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            export_venture("nonexistent", tmp_path)


# ---------------------------------------------------------------------------
# Venture Import
# ---------------------------------------------------------------------------


class TestVentureImport:
    def _create_export(self, tmp_path):
        """Create a venture, export it, return the zip path."""
        sys_dir = tmp_path / "src" / "systems" / "original"
        (sys_dir / "F-foundations").mkdir(parents=True)
        (sys_dir / "A-agents").mkdir()
        (sys_dir / "F-foundations" / "identity.md").write_text("# Imported Identity", encoding="utf-8")
        (sys_dir / "A-agents" / "writer.md").write_text("# Imported Writer", encoding="utf-8")

        zip_path = tmp_path / "export.zip"
        export_venture("original", tmp_path / "src", zip_path)
        return zip_path

    def test_import_restores_files(self, tmp_path):
        zip_path = self._create_export(tmp_path)
        dest = tmp_path / "dest"
        dest.mkdir()

        result = import_venture(zip_path, dest, venture_key="imported")
        assert result["venture_key"] == "imported"
        assert result["files_imported"] >= 2

        assert (dest / "systems" / "imported" / "F-foundations" / "identity.md").exists()
        assert (dest / "systems" / "imported" / "A-agents" / "writer.md").exists()

    def test_import_with_key_override(self, tmp_path):
        zip_path = self._create_export(tmp_path)
        dest = tmp_path / "dest"
        dest.mkdir()

        result = import_venture(zip_path, dest, venture_key="my-new-biz")
        assert result["venture_key"] == "my-new-biz"
        assert (dest / "systems" / "my-new-biz" / "F-foundations" / "identity.md").exists()

    def test_import_nonexistent_zip(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            import_venture(tmp_path / "missing.zip", tmp_path)
