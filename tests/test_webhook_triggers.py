"""Codex audit: a webhook trigger match must not be reported as a skill run."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_matched_trigger_is_reported_as_not_executed(monkeypatch):
    from realize_api.routes import webhooks

    logged: list[dict] = []
    monkeypatch.setattr("realize_core.activity.logger.log_event", lambda **kw: logged.append(kw))
    app = FastAPI()
    app.include_router(webhooks.router, prefix="/api")
    app.state.config = {"webhook_triggers": [{"source": "custom", "skill": "invoice_processor"}]}

    body = TestClient(app).post("/api/webhooks/custom", json={"event": "x"}).json()

    assert body["triggers_matched"] == 1
    assert body["triggers_executed"] == 0
    actions = [e["action"] for e in logged]
    assert "webhook_trigger_matched" in actions
    assert "webhook_trigger_fired" not in actions
