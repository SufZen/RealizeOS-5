"""
Codex audit F06: the workflow API must refuse what it can't store.

The Workflow Editor posted ``content/format/venture_key``; the API ignored
those fields and created a workflow with no venture, triggers or steps
(201), so a save looked successful and produced an empty workflow.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from realize_api.routes import workflows

    app = FastAPI()
    app.include_router(workflows.router, prefix="/api")
    app.state.systems = {}
    return TestClient(app)


def test_editor_shaped_body_is_refused():
    res = _client().post(
        "/api/workflows",
        json={"name": "draft", "format": "yaml", "content": "name: draft\n", "venture_key": "acme"},
    )
    assert res.status_code == 422


def test_workflow_without_steps_is_refused():
    assert _client().post("/api/workflows", json={"name": "empty", "system_key": "acme"}).status_code == 422


def test_update_refuses_unknown_fields_and_empty_steps():
    client = _client()
    assert client.put("/api/workflows/x", json={"content": "..."}).status_code == 422
    assert client.put("/api/workflows/x", json={"steps": []}).status_code == 422


def test_api_workflows_survive_a_settings_reload(tmp_path, monkeypatch):
    """A settings reload re-reads the skill files; what was done through the API stays (review G-5)."""
    from types import SimpleNamespace

    from realize_core.config_runtime import reload_app_config
    from realize_core.skills import detector

    folder = tmp_path / "systems" / "acme" / "R-routines" / "skills"
    folder.mkdir(parents=True)
    for name in ("site_diary", "old_report"):
        (folder / f"{name}.yaml").write_text(f"name: {name}\ntriggers: [{name}]\n", encoding="utf-8")
    monkeypatch.setattr(detector, "_loaded_skills", {})
    state = SimpleNamespace(kb_path=tmp_path)
    config = {"systems": [{"key": "acme", "directory": "systems/acme"}]}
    monkeypatch.setattr("realize_core.config_runtime.sync_tool_gate", lambda app_state, config: None)
    reload_app_config(state, tmp_path, config)

    client = _client()
    body = {"name": "tender_check", "system_key": "acme", "steps": [{"id": "s1", "type": "agent"}]}
    assert client.post("/api/workflows", json=body).status_code == 201
    assert client.put("/api/workflows/site_diary?system_key=acme", json={"enabled": False}).status_code == 200
    assert client.delete("/api/workflows/old_report?system_key=acme").status_code == 200

    reload_app_config(state, tmp_path, config)  # e.g. a change saved in Settings

    assert detector.find_skill("tender_check", "acme")[1]["steps"] == body["steps"]
    assert detector.find_skill("site_diary", "acme")[1]["enabled"] is False
    assert detector.find_skill("old_report", "acme") is None
    names = [s["name"] for s in detector.get_skills_for_system("acme")]
    assert sorted(names) == ["site_diary", "tender_check"]

    # A skill file that appears later with the same name doesn't replace the API's until restart.
    (folder / "tender_check.yaml").write_text("name: tender_check\ntriggers: [from file]\n", encoding="utf-8")
    reload_app_config(state, tmp_path, config)
    assert detector.find_skill("tender_check", "acme")[1]["steps"] == body["steps"]
    assert [s["name"] for s in detector.get_skills_for_system("acme")].count("tender_check") == 1
