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
