"""A venture created with packs on, after ``features.packs`` is turned off (review finding, 2026-10-13).

The venture links its team and skills instead of copying them, so with the
flag off it has none. That used to happen silently; now it is logged at
startup and on the reload that turns the flag off, and listed in the
venture's ``warnings`` (``GET /api/ventures``, ``GET /api/status``).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from realize_core.config import build_systems_dict, load_config
from realize_core.packs import clear_cache, loader
from realize_core.scaffold import scaffold_venture

LOGGER = "realize_core.packs.flag_off"


def _set_packs(root: Path, on: bool) -> dict:
    """Rewrite the ``features.packs`` flag in ``realize-os.yaml`` and return the loaded config."""
    import yaml

    path = root / "realize-os.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config["features"] = {**(config.get("features") or {}), "packs": on}
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return load_config(path)


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    monkeypatch.delenv(loader.PACKS_PATH_ENV, raising=False)
    (tmp_path / "realize-os.yaml").write_text("name: test\nfeatures:\n  packs: true\nsystems: []\n", encoding="utf-8")
    clear_cache()
    yield tmp_path
    clear_cache()


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == logging.WARNING]


def test_turning_packs_off_under_a_linked_venture_is_reported(project, caplog):
    scaffold_venture(project, "dev-co", template="real-estate-developer")
    assert build_systems_dict(_set_packs(project, True), project)["dev-co"].get("warnings") is None

    config = _set_packs(project, False)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        system = build_systems_dict(config, project)["dev-co"]  # startup
        build_systems_dict(config, project)  # a later rebuild (reload, mission step): logged once per change

    assert system["agents"] == {}
    [message] = system["warnings"]
    assert "Venture dev-co links packs (profession developer, market il)" in message
    assert "features.packs is off" in message
    assert "6 agents and 3 skills" in message
    assert _warnings(caplog) == [message]

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert build_systems_dict(_set_packs(project, True), project)["dev-co"].get("warnings") is None
        build_systems_dict(_set_packs(project, False), project)  # turned off again: reported again
    assert _warnings(caplog) == [message]


def test_ventures_with_their_own_team_are_not_reported(project, caplog):
    _set_packs(project, False)
    scaffold_venture(project, "old-co", template="real-estate-developer")  # flag off: copied, as before packs
    plain = project / "systems" / "plain"
    (plain / "A-agents").mkdir(parents=True)
    (plain / "packs.yaml").write_text("market: [il]\n", encoding="utf-8")  # the il pack brings no agents or skills
    import yaml

    config_path = project / "realize-os.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["systems"].append({"key": "plain", "name": "Plain", "directory": "systems/plain"})
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        systems = build_systems_dict(load_config(config_path), project)

    assert systems["old-co"].get("warnings") is None
    assert systems["plain"].get("warnings") is None
    assert _warnings(caplog) == []


def test_the_warning_shows_in_the_venture_list_and_status(project):
    from realize_api.routes import health, ventures

    scaffold_venture(project, "dev-co", template="real-estate-developer")
    app = FastAPI()
    app.include_router(ventures.router, prefix="/api")
    app.include_router(health.router, prefix="/api")
    app.state.systems = build_systems_dict(_set_packs(project, False), project)
    app.state.kb_path = project
    app.state.config = {"features": {"packs": False}}
    client = TestClient(app)

    listed = {v["key"]: v for v in client.get("/api/ventures").json()["ventures"]}
    detail = client.get("/api/ventures/dev-co").json()
    status = client.get("/api/status").json()

    assert "features.packs is off" in listed["dev-co"]["warnings"][0]
    assert detail["warnings"] == listed["dev-co"]["warnings"]
    assert status["systems"]["dev-co"]["warnings"] == listed["dev-co"]["warnings"]
