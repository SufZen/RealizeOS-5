"""QA 5.14 K-1: the venture skills endpoint and MCP list_skills import get_skills_for_system."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_skills_for_a_venture_are_listed(monkeypatch):
    from realize_core.skills import detector

    monkeypatch.setattr(
        detector,
        "_loaded_skills",
        {"acme": [{"name": "tender_register", "triggers": ["tender"]}], "shared": [{"name": "weekly_review"}]},
    )
    from realize_api.routes import systems

    app = FastAPI()
    app.include_router(systems.router, prefix="/api")
    app.state.systems = {"acme": {"name": "Acme"}}

    body = TestClient(app).get("/api/systems/acme/skills").json()

    assert "error" not in body
    assert {s["name"] for s in body["skills"]} == {"tender_register", "weekly_review"}


async def test_mcp_list_skills_works(monkeypatch):
    from types import SimpleNamespace

    from realize_core.mcp_server.tools.chat_tools import list_skills
    from realize_core.skills import detector

    monkeypatch.setattr(detector, "_loaded_skills", {"acme": [{"name": "tender_register"}]})
    out = await list_skills({"system_key": "acme"}, SimpleNamespace(), None)

    assert "error" not in out
    assert [s["name"] for s in out["skills"]] == ["tender_register"]
