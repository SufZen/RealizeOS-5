"""An agent's ``definition_path`` never shows where files sit on the server.

A pack can be installed outside the KB, and its agents were listed with the
absolute path (a viewer saw ``H:\\...\\packs\\...\\procurement.md``). The venture
agent routes now show a KB-relative path for a venture's own agent and
``<layer>:<pack ref>/<path in the pack>`` for a pack agent.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

VENTURE = "acme-co"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def kb(tmp_path: Path, monkeypatch) -> Path:
    """A KB with one venture agent; the venture links a profession pack installed outside the KB."""
    from realize_core.packs import clear_cache, loader

    packs_root = tmp_path / "installed-packs"
    acme = packs_root / "profession" / "acme"
    _write(acme / "pack.yaml", yaml.safe_dump({"id": "acme", "kind": "profession", "version": "0.1.0"}))
    _write(acme / "A-agents" / "procurement.md", "# Procurement\n")
    monkeypatch.delenv("REALIZE_PACKS_PATH", raising=False)
    monkeypatch.setattr(loader, "default_packs_root", lambda: packs_root)
    clear_cache()

    root = tmp_path / "kb"
    venture = root / "systems" / VENTURE
    _write(venture / "packs.yaml", yaml.safe_dump({"profession": ["acme"]}))
    _write(venture / "A-agents" / "writer.md", "# Writer\n")
    yield root
    clear_cache()


@pytest.fixture
def client(kb: Path) -> TestClient:
    from realize_api.main import create_app
    from realize_core.config import build_systems_dict

    config = {"systems": [{"key": VENTURE, "directory": f"systems/{VENTURE}"}], "features": {"packs": True}}
    app = create_app()
    app.state.systems = build_systems_dict(config, kb)
    app.state.kb_path = kb
    app.state.config = config
    app.state.agent_registry = None

    @app.middleware("http")
    async def as_viewer(request, call_next):
        request.state.user_id = "viewer@acme.io"
        request.state.role = "viewer"
        request.state.scopes = []
        return await call_next(request)

    return TestClient(app)


def test_the_pack_really_is_outside_the_kb(client, kb):
    stored = client.app.state.systems[VENTURE]["agents"]["procurement"]
    assert Path(stored).is_absolute(), "fixture: the stored path is what used to leak"


def test_pack_agent_detail_shows_the_pack_reference(client, kb):
    resp = client.get(f"/api/ventures/{VENTURE}/agents/procurement")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["definition_path"] == "profession:acme@0.1.0/A-agents/procurement.md"
    assert str(kb.parent) not in body["definition_path"]
    assert body["definition"].startswith("# Procurement")  # still read from the pack


def test_venture_agent_detail_is_kb_relative(client):
    body = client.get(f"/api/ventures/{VENTURE}/agents/writer").json()
    assert body["definition_path"] == f"systems/{VENTURE}/A-agents/writer.md"


@pytest.mark.parametrize("path", [f"/api/ventures/{VENTURE}/agents", f"/api/ventures/{VENTURE}"])
def test_lists_never_show_an_absolute_path(client, kb, path):
    resp = client.get(path)

    assert resp.status_code == 200, resp.text
    paths = {a["key"]: a["definition_path"] for a in resp.json()["agents"]}
    assert paths == {
        "writer": f"systems/{VENTURE}/A-agents/writer.md",
        "procurement": "profession:acme@0.1.0/A-agents/procurement.md",
    }
    for value in paths.values():
        assert not Path(value).is_absolute()
        assert str(kb.parent) not in value


class TestPublicDefinitionPath:
    def test_an_absolute_venture_path_under_the_kb_becomes_relative(self, tmp_path):
        from realize_api.routes.route_helpers import public_definition_path

        file = tmp_path / "kb" / "systems" / "v" / "A-agents" / "a.md"
        conf = {"agents": {"a": str(file)}}
        assert public_definition_path(conf, "a", tmp_path / "kb") == "systems/v/A-agents/a.md"

    def test_an_absolute_venture_path_outside_the_kb_is_only_the_file_name(self, tmp_path):
        from realize_api.routes.route_helpers import public_definition_path

        conf = {"agents": {"a": str(tmp_path / "elsewhere" / "a.md")}}
        assert public_definition_path(conf, "a", tmp_path / "kb") == "a.md"
        assert public_definition_path(conf, "a") == "a.md"

    def test_a_pack_agent_without_a_version_uses_the_layer_and_pack(self, tmp_path):
        from realize_api.routes.route_helpers import public_definition_path

        conf = {
            "agents": {"a": str(tmp_path / "packs" / "a.md")},
            "agent_provenance": {"a": {"layer": "firm"}},
        }
        assert public_definition_path(conf, "a", tmp_path) == "firm/A-agents/a.md"

    def test_unknown_agent(self):
        from realize_api.routes.route_helpers import public_definition_path

        assert public_definition_path({"agents": {}}, "nope") == ""
