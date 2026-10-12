"""
Venture create/delete must be all-or-nothing (QA 5.14, P0 #3).

On 5.14 a delete removed ``systems/homeaid`` first and then failed on a
read-only ``realize-os.yaml``, losing the files while the venture stayed
configured. These tests pin the new order (config first, files last, rollback),
config-only removal, directory resolution from config, and the API mapping.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from realize_core.scaffold import VentureConfigReadOnlyError, delete_venture, scaffold_venture


def _write_config(root: Path, systems: list[dict]) -> None:
    (root / "realize-os.yaml").write_text(yaml.safe_dump({"name": "T", "systems": systems}), encoding="utf-8")


def _config_keys(root: Path) -> list[str]:
    config = yaml.safe_load((root / "realize-os.yaml").read_text(encoding="utf-8"))
    return [s["key"] for s in config.get("systems", [])]


def _make_dir(root: Path, rel: str) -> Path:
    d = root / rel
    (d / "F-foundations").mkdir(parents=True)
    (d / "F-foundations" / "venture-identity.md").write_text("x", encoding="utf-8")
    return d


@pytest.fixture
def project(tmp_path):
    """Two configured ventures with directories, DB cleanup stubbed out."""
    _make_dir(tmp_path, "systems/alpha")
    _make_dir(tmp_path, "systems/beta")
    _write_config(
        tmp_path,
        [
            {"key": "alpha", "name": "Alpha", "directory": "systems/alpha"},
            {"key": "beta", "name": "Beta", "directory": "systems/beta"},
        ],
    )
    with patch("realize_core.scaffold._cleanup_venture_db_references") as cleanup:
        yield tmp_path, cleanup


class TestDeleteVenture:
    def test_removes_config_entry_files_and_db_rows(self, project):
        root, cleanup = project
        result = delete_venture(root, "alpha", confirm_name="alpha")

        assert result["deleted"] is True
        assert result["warnings"] == []
        assert not (root / "systems" / "alpha").exists()
        assert _config_keys(root) == ["beta"]
        assert (root / "systems" / "beta").is_dir()
        cleanup.assert_called_once_with("alpha")
        assert not list((root / "systems").glob(".deleting-*"))

    def test_read_only_config_changes_nothing(self, project):
        root, cleanup = project
        with (
            patch("realize_core.scaffold.config_writable", return_value=False),
            pytest.raises(VentureConfigReadOnlyError),
        ):
            delete_venture(root, "alpha", confirm_name="alpha")

        assert (root / "systems" / "alpha" / "F-foundations" / "venture-identity.md").exists()
        assert _config_keys(root) == ["alpha", "beta"]
        cleanup.assert_not_called()

    def test_failed_config_write_restores_directory(self, project):
        root, cleanup = project
        with (
            patch("realize_core.scaffold._write_config_text", side_effect=OSError(30, "Read-only file system")),
            pytest.raises(OSError),
        ):
            delete_venture(root, "alpha", confirm_name="alpha")

        assert (root / "systems" / "alpha" / "F-foundations" / "venture-identity.md").exists()
        assert not list((root / "systems").glob(".deleting-*"))
        assert _config_keys(root) == ["alpha", "beta"]
        cleanup.assert_not_called()

    def test_config_only_venture_is_removed_with_warning(self, project):
        root, _ = project
        _write_config(
            root,
            [
                {"key": "alpha", "directory": "systems/alpha"},
                {"key": "ghost", "directory": "systems/ghost"},
            ],
        )
        result = delete_venture(root, "ghost", confirm_name="ghost")

        assert result["directory"] is None
        assert result["warnings"]
        assert _config_keys(root) == ["alpha"]

    def test_uses_configured_directory_not_key(self, project):
        root, _ = project
        real = _make_dir(root, "systems/realization.co.il")
        stale = _make_dir(root, "systems/realization-il")
        _write_config(root, [{"key": "realization-il", "directory": "systems/realization.co.il"}])

        delete_venture(root, "realization-il", confirm_name="realization-il")

        assert not real.exists()
        assert stale.exists()

    @pytest.mark.parametrize("directory", [".", "systems", "../outside", "systems/a/b"])
    def test_refuses_directory_outside_systems(self, project, directory):
        root, _ = project
        _write_config(root, [{"key": "bad", "directory": directory}])

        with pytest.raises(ValueError):
            delete_venture(root, "bad", confirm_name="bad")

        assert (root / "systems" / "alpha").is_dir()
        assert _config_keys(root) == ["bad"]

    def test_refuses_directory_shared_with_another_venture(self, project):
        root, _ = project
        _write_config(
            root,
            [
                {"key": "alpha", "directory": "systems/alpha"},
                {"key": "alias", "directory": "systems/alpha"},
            ],
        )
        with pytest.raises(ValueError, match="also used"):
            delete_venture(root, "alias", confirm_name="alias")
        assert (root / "systems" / "alpha").is_dir()

    def test_unknown_venture_raises_not_found(self, project):
        root, _ = project
        with pytest.raises(FileNotFoundError):
            delete_venture(root, "nope", confirm_name="nope")

    def test_confirmation_mismatch(self, project):
        root, _ = project
        with pytest.raises(ValueError, match="does not match"):
            delete_venture(root, "alpha", confirm_name="beta")
        assert (root / "systems" / "alpha").is_dir()


class TestCreateVenture:
    @pytest.fixture
    def template(self, tmp_path):
        tpl = tmp_path / "tpl"
        (tpl / "F-foundations").mkdir(parents=True)
        (tpl / "F-foundations" / "venture-identity.md").write_text("[Your Business Name]", encoding="utf-8")
        return tpl

    def test_read_only_config_leaves_no_orphan_directory(self, project, template):
        root, _ = project
        with (
            patch("realize_core.scaffold._find_venture_template", return_value=template),
            patch("realize_core.scaffold.config_writable", return_value=False),
            pytest.raises(VentureConfigReadOnlyError),
        ):
            scaffold_venture(root, "gamma")
        assert not (root / "systems" / "gamma").exists()

    def test_failed_config_write_removes_copied_directory(self, project, template):
        root, _ = project
        with (
            patch("realize_core.scaffold._find_venture_template", return_value=template),
            patch("realize_core.scaffold._write_config_text", side_effect=OSError(30, "Read-only file system")),
            pytest.raises(OSError),
        ):
            scaffold_venture(root, "gamma")
        assert not (root / "systems" / "gamma").exists()
        assert _config_keys(root) == ["alpha", "beta"]

    def test_create_registers_venture(self, project, template):
        root, _ = project
        with patch("realize_core.scaffold._find_venture_template", return_value=template):
            scaffold_venture(root, "gamma", name="Gamma")
        assert "gamma" in _config_keys(root)
        assert (root / "systems" / "gamma" / "F-foundations" / "venture-identity.md").read_text(
            encoding="utf-8"
        ) == "Gamma"


class TestVentureRoutes:
    @pytest.fixture
    def client(self, project, monkeypatch):
        root, _ = project
        monkeypatch.setenv("REALIZE_CONFIG", str(root / "realize-os.yaml"))
        from realize_api.routes import ventures

        app = FastAPI()
        app.include_router(ventures.router, prefix="/api")
        app.state.kb_path = root
        app.state.config = {}
        app.state.systems = {
            "alpha": {"key": "alpha", "name": "Alpha", "directory": "systems/alpha"},
            "beta": {"key": "beta", "name": "Beta", "directory": "systems/beta"},
        }
        return TestClient(app), app, root

    def test_delete_success_reloads_systems(self, client):
        c, app, root = client
        res = c.delete("/api/ventures/alpha")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"
        assert "alpha" not in app.state.systems
        assert "beta" in app.state.systems

    def test_delete_read_only_returns_503_with_detail(self, client):
        c, app, root = client
        with patch("realize_core.scaffold.config_writable", return_value=False):
            res = c.delete("/api/ventures/alpha")
        assert res.status_code == 503
        assert "read-only" in res.json()["detail"]
        assert (root / "systems" / "alpha").is_dir()

    def test_list_reports_config_writable(self, client):
        c, _, _ = client
        assert c.get("/api/ventures").json()["config_writable"] is True
        with patch("realize_core.scaffold.config_writable", return_value=False):
            assert c.get("/api/ventures").json()["config_writable"] is False

    def test_create_invalid_key_returns_400(self, client):
        c, _, _ = client
        res = c.post("/api/ventures", json={"key": "Bad_Key"})
        assert res.status_code == 400

    def test_create_existing_returns_409(self, client):
        c, _, _ = client
        res = c.post("/api/ventures", json={"key": "alpha"})
        assert res.status_code == 409
