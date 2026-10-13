"""Pack agents in the agents_v2 registry API (``/api/agents``), behind ``features.packs``.

A fixture KB: ``acme-co`` links the profession pack ``acme`` (agents
``estimator`` and ``reviewer``) and the market pack ``zz`` (agent
``surveyor``), has its own ``reviewer`` (which wins over the pack's) and a
firm override agent ``controller``; ``plain`` links no pack and has a
``writer``. With the flag on, a venture's effective team is listed with
where each agent came from, and pack agents are read-only. With it off the
API answers exactly as before.
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


def _yaml(path: Path, data) -> None:
    _write(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


@pytest.fixture
def kb(tmp_path: Path, monkeypatch) -> Path:
    from realize_core.packs import clear_cache, loader

    packs_root = tmp_path / "packs"
    acme = packs_root / "profession" / "acme"
    _yaml(acme / "pack.yaml", {"id": "acme", "kind": "profession", "version": "0.1.0", "title": "Acme"})
    _write(acme / "A-agents" / "estimator.md", "# Estimator\n\n## Role\nChecks quotes line by line.\n")
    _write(acme / "A-agents" / "reviewer.md", "# Pack reviewer\n")
    zz = packs_root / "market" / "zz"
    _yaml(zz / "pack.yaml", {"id": "zz", "kind": "market", "version": "0.2.0", "verification": {"level": 1}})
    _write(zz / "A-agents" / "surveyor.md", "# Surveyor\n")

    monkeypatch.delenv("REALIZE_PACKS_PATH", raising=False)
    monkeypatch.setattr(loader, "default_packs_root", lambda: packs_root)
    clear_cache()
    root = tmp_path / "kb"
    venture = root / "systems" / VENTURE
    _yaml(venture / "packs.yaml", {"profession": ["acme"], "market": ["zz"]})
    _write(venture / "A-agents" / "reviewer.md", "# Venture reviewer\n")
    _write(venture / "F-foundations" / "overrides" / "A-agents" / "controller.md", "# Controller\n")
    _write(root / "systems" / "plain" / "A-agents" / "writer.md", "# Writer\n")
    yield root
    clear_cache()


def _config(packs: bool) -> dict:
    config = {
        "systems": [
            {"key": VENTURE, "directory": f"systems/{VENTURE}"},
            {"key": "plain", "directory": "systems/plain"},
        ]
    }
    if packs:
        config["features"] = {"packs": True}
    return config


def _client(kb: Path, *, packs: bool, scopes: tuple[str, ...] = (), role: str = "owner") -> TestClient:
    from realize_api.main import create_app
    from realize_core.config import build_systems_dict

    config = _config(packs)
    app = create_app()
    app.state.systems = build_systems_dict(config, kb)
    app.state.kb_path = kb
    app.state.config = config
    app.state.agent_registry = None

    @app.middleware("http")
    async def as_principal(request, call_next):
        request.state.user_id = "dana@acme.io"
        request.state.role = role
        request.state.scopes = list(scopes)
        return await call_next(request)

    return TestClient(app)


def _by(agents: list[dict]) -> dict[tuple[str | None, str], dict]:
    return {(a.get("venture_key"), a["key"]): a for a in agents}


def test_flag_off_lists_exactly_the_ventures_own_agents_as_before(kb):
    body = _client(kb, packs=False).get("/api/agents").json()

    assert sorted(a["key"] for a in body["agents"]) == ["reviewer", "writer"]
    assert body["total"] == 2
    # No new fields: the response is what it was before packs.
    assert all(not {"layer", "venture_key", "read_only", "pack"} & set(a) for a in body["agents"])
    client = _client(kb, packs=False)
    assert client.get("/api/agents/estimator").status_code == 404
    assert client.put("/api/agents/estimator", json={"description": "x"}).status_code in (403, 404)


def test_flag_on_lists_each_ventures_effective_team_with_provenance(kb):
    body = _client(kb, packs=True).get("/api/agents").json()
    agents = _by(body["agents"])

    assert set(agents) == {
        (VENTURE, "reviewer"),
        (VENTURE, "estimator"),
        (VENTURE, "surveyor"),
        (VENTURE, "controller"),
        ("plain", "writer"),
    }
    assert body["total"] == 5
    own = agents[(VENTURE, "reviewer")]
    assert (own["layer"], own["read_only"], own["name"]) == ("venture", False, "Venture reviewer")
    estimator = agents[(VENTURE, "estimator")]
    assert estimator["layer"] == "profession"
    assert estimator["pack"] == "acme@0.1.0"
    assert estimator["read_only"] is True
    assert estimator["override_path"] == f"systems/{VENTURE}/A-agents/estimator.md"
    assert estimator["role"] == "Checks quotes line by line."
    assert "verification" not in estimator  # only market packs carry a level
    surveyor = agents[(VENTURE, "surveyor")]
    assert (surveyor["layer"], surveyor["pack"], surveyor["verification"]) == ("market", "zz@0.2.0", 1)
    assert agents[(VENTURE, "controller")]["layer"] == "firm"
    assert agents[("plain", "writer")]["layer"] == "venture"


def test_the_ventures_own_agent_wins_over_the_packs(kb):
    agents = _client(kb, packs=True).get("/api/agents", params={"venture": VENTURE}).json()["agents"]
    reviewers = [a for a in agents if a["key"] == "reviewer"]
    assert len(reviewers) == 1
    assert reviewers[0]["name"] == "Venture reviewer"
    assert reviewers[0]["layer"] == "venture"


def test_venture_filter_shows_one_ventures_team(kb):
    client = _client(kb, packs=True)
    team = client.get("/api/agents", params={"venture": VENTURE}).json()["agents"]
    assert {(a["key"], a["layer"]) for a in team} == {
        ("reviewer", "venture"),
        ("estimator", "profession"),
        ("surveyor", "market"),
        ("controller", "firm"),
    }
    plain = client.get("/api/agents", params={"venture": "plain"}).json()["agents"]
    assert [(a["key"], a["layer"]) for a in plain] == [("writer", "venture")]
    assert client.get("/api/agents", params={"venture": "nope"}).status_code == 404
    # Without packs the filter still narrows to the venture's own agents.
    off = _client(kb, packs=False).get("/api/agents", params={"venture": VENTURE}).json()["agents"]
    assert [a["key"] for a in off] == ["reviewer"]


def test_version_filter_applies_to_pack_agents(kb):
    client = _client(kb, packs=True)
    assert client.get("/api/agents", params={"version": "2"}).json()["agents"] == []
    assert len(client.get("/api/agents", params={"version": "1"}).json()["agents"]) == 5


def test_get_a_pack_agent_with_its_provenance(kb):
    client = _client(kb, packs=True)
    agent = client.get("/api/agents/estimator", params={"venture": VENTURE}).json()
    assert (agent["key"], agent["venture_key"], agent["layer"], agent["read_only"]) == (
        "estimator",
        VENTURE,
        "profession",
        True,
    )
    assert client.get("/api/agents/estimator").json()["pack"] == "acme@0.1.0"
    assert client.get("/api/agents/reviewer", params={"venture": VENTURE}).json()["layer"] == "venture"
    assert client.get("/api/agents/estimator", params={"venture": "plain"}).status_code == 404


@pytest.mark.parametrize("method", ["put", "delete"])
def test_editing_a_pack_agent_says_override_it_in_your_venture(kb, method):
    pack_file = kb.parent / "packs" / "profession" / "acme" / "A-agents" / "estimator.md"
    before = pack_file.read_text(encoding="utf-8")
    client = _client(kb, packs=True)

    if method == "put":
        r = client.put("/api/agents/estimator", params={"venture": VENTURE}, json={"description": "cheaper"})
    else:
        r = client.delete("/api/agents/estimator", params={"venture": VENTURE})

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "pack_agent_read_only"
    assert detail["layer"] == "profession"
    assert detail["pack"] == "acme@0.1.0"
    assert detail["override_path"] == f"systems/{VENTURE}/A-agents/estimator.md"
    assert "override it in your venture" in detail["message"]
    # Nothing was written into the pack, and the agent is still listed.
    assert pack_file.read_text(encoding="utf-8") == before
    assert not (kb / "systems" / VENTURE / "A-agents" / "estimator.md").exists()
    assert client.get("/api/agents/estimator", params={"venture": VENTURE}).status_code == 200


def test_a_firm_override_agent_is_read_only_too(kb):
    r = _client(kb, packs=True).put("/api/agents/controller", json={"description": "x"})
    assert r.status_code == 409
    assert "the firm's overrides" in r.json()["detail"]["message"]


def test_the_ventures_own_agents_keep_their_behaviour(kb):
    client = _client(kb, packs=True)
    # A V1 agent from the venture's folder: the registry's own rule, not the pack's.
    r = client.put("/api/agents/reviewer", params={"venture": VENTURE}, json={"description": "x"})
    assert r.status_code == 400
    assert "V1" in r.json()["detail"]
    # Naming a venture the agent doesn't belong to finds nothing.
    assert client.put("/api/agents/writer", params={"venture": VENTURE}, json={"description": "x"}).status_code == 404
    assert client.delete("/api/agents/writer", params={"venture": VENTURE}).status_code == 404
    assert client.get("/api/agents/writer").status_code == 200  # still registered


def test_a_venture_limited_caller_sees_only_their_ventures_pack_agents(kb):
    client = _client(kb, packs=True, scopes=("venture:plain",), role="operator")
    agents = client.get("/api/agents").json()["agents"]
    assert [(a["venture_key"], a["key"]) for a in agents] == [("plain", "writer")]
    assert client.get("/api/agents/estimator").status_code == 404
    # Naming another venture is refused by the venture guard before the route runs.
    assert client.get("/api/agents", params={"venture": VENTURE}).status_code == 403
    assert client.put("/api/agents/estimator", json={"description": "x"}).status_code in (403, 404)
