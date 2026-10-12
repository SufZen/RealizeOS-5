"""
Codex audit F08: the Integrations page must not claim a connection it never made.

Adding Slack with an invalid key returned "connected", and test returned
"Connection to Slack is working" without contacting Slack; the key itself
was discarded.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    from realize_api.routes import integrations

    monkeypatch.setattr(integrations, "_integrations", [])
    app = FastAPI()
    app.include_router(integrations.router, prefix="/api")
    return TestClient(app)


def test_adding_with_a_key_is_not_reported_connected(client):
    res = client.post("/api/integrations", json={"provider": "slack", "api_key": "deliberately-invalid"})

    assert res.status_code == 200
    assert res.json()["status"] == "unverified"
    assert "deliberately-invalid" not in client.get("/api/integrations").text


def test_connect_says_it_cannot(client):
    integration_id = client.post("/api/integrations", json={"provider": "slack"}).json()["id"]

    res = client.post(f"/api/integrations/{integration_id}/connect")

    assert res.status_code == 409
    assert "Setup" in res.json()["detail"]
    assert client.get("/api/integrations").json()["integrations"][0]["status"] == "unverified"


def test_test_does_not_claim_the_connection_works(client):
    integration_id = client.post("/api/integrations", json={"provider": "slack"}).json()["id"]

    body = client.post(f"/api/integrations/{integration_id}/test").json()

    assert body["status"] == "unverified"
    assert "working" not in body["message"]


def test_no_provider_asks_for_a_key_here(client):
    available = client.get("/api/integrations").json()["available"]
    assert not any(a["requires_api_key"] for a in available)
