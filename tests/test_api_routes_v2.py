"""
Tests for Sprint 3 API routes — Agents V2, Workflows, Extensions, Routing.

Uses FastAPI's TestClient for endpoint testing.
"""

import pytest
from fastapi.testclient import TestClient
from realize_api.main import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Create a FastAPI test client with mocked app state."""
    # Reset module-level state to avoid cross-test pollution
    import realize_api.routes.agents_v2 as _agents_mod
    import realize_api.routes.routing as _routing_mod

    _agents_mod._registry = None
    _agents_mod._pipeline_states.clear()
    _routing_mod._routing_analytics.clear()

    app = create_app()

    with TestClient(app, raise_server_exceptions=False) as c:
        # Override app state AFTER lifespan startup (which loads real config)
        app.state.config = {"systems": [], "features": {}}
        app.state.systems = {
            "test": {
                "name": "Test System",
                "agents": {"orchestrator": "systems/test/A-agents/orchestrator.md"},
                "agents_dir": "systems/test/A-agents",
                "agent_routing": {"orchestrator": ["help", "general", "question"]},
                "routing": {},
            }
        }
        app.state.kb_path = None
        app.state.shared_config = {"identity": "shared/identity.md"}
        yield c


# ---------------------------------------------------------------------------
# Agents V2 routes
# ---------------------------------------------------------------------------


class TestAgentsV2Routes:
    """Test the /api/agents endpoints."""

    def test_list_agents_empty(self, client):
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "total" in data

    def test_list_personas(self, client):
        resp = client.get("/api/agents/personas")
        assert resp.status_code == 200
        data = resp.json()
        assert "personas" in data
        # Should have the 5 built-in personas
        assert len(data["personas"]) >= 5
        keys = [p["key"] for p in data["personas"]]
        assert "writer" in keys
        assert "pm" in keys
        assert "exec-assistant" in keys

    def test_create_agent(self, client):
        resp = client.post(
            "/api/agents",
            json={
                "name": "Test Agent",
                "key": "test_agent",
                "description": "A test agent",
                "persona": "writer",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"] == "test_agent"
        assert data["version"] == "2"
        assert data["persona"] == "writer"

    def test_create_duplicate_agent_409(self, client):
        client.post("/api/agents", json={"name": "A", "key": "dup"})
        resp = client.post("/api/agents", json={"name": "B", "key": "dup"})
        assert resp.status_code == 409

    def test_get_agent(self, client):
        client.post("/api/agents", json={"name": "Getter", "key": "getter"})
        resp = client.get("/api/agents/getter")
        assert resp.status_code == 200
        assert resp.json()["key"] == "getter"

    def test_get_agent_not_found(self, client):
        resp = client.get("/api/agents/nonexistent")
        assert resp.status_code == 404

    def test_update_agent(self, client):
        client.post("/api/agents", json={"name": "Updatable", "key": "updatable"})
        resp = client.put(
            "/api/agents/updatable",
            json={
                "description": "Updated description",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    def test_update_nonexistent_404(self, client):
        resp = client.put("/api/agents/nope", json={"description": "x"})
        assert resp.status_code == 404

    def test_delete_agent(self, client):
        client.post("/api/agents", json={"name": "Deleteable", "key": "del_me"})
        resp = client.delete("/api/agents/del_me")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Verify it's gone
        resp = client.get("/api/agents/del_me")
        assert resp.status_code == 404

    def test_delete_nonexistent_404(self, client):
        resp = client.delete("/api/agents/nope")
        assert resp.status_code == 404

    def test_reload_agents(self, client):
        resp = client.post("/api/agents/reload")
        assert resp.status_code == 200
        assert resp.json()["status"] == "reloaded"

    def test_create_agent_invalid_persona_400(self, client):
        resp = client.post(
            "/api/agents",
            json={
                "name": "Bad",
                "key": "bad",
                "persona": "nonexistent_persona",
            },
        )
        assert resp.status_code == 400

    def test_filter_by_version(self, client):
        client.post("/api/agents", json={"name": "V2 Agent", "key": "v2_agent"})
        resp = client.get("/api/agents", params={"version": "2"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(a["version"] == "2" for a in data["agents"])


# ---------------------------------------------------------------------------
# Pipeline routes
# ---------------------------------------------------------------------------


class TestPipelineRoutes:
    def test_execute_pipeline(self, client):
        resp = client.post(
            "/api/pipelines/execute",
            json={
                "stages": [
                    {"name": "draft", "agent_key": "writer"},
                    {"name": "review", "agent_key": "reviewer"},
                ],
                "input_text": "Write a blog post about AI",
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "pipeline_id" in data
        assert data["status"] in ("completed", "running")

    def test_get_pipeline_state(self, client):
        # Execute first
        create_resp = client.post(
            "/api/pipelines/execute",
            json={
                "stages": [{"name": "step", "agent_key": "agent"}],
                "input_text": "test",
            },
        )
        pid = create_resp.json()["pipeline_id"]

        # Then retrieve
        resp = client.get(f"/api/pipelines/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pipeline_id"] == pid
        assert "results" in data

    def test_get_nonexistent_pipeline_404(self, client):
        resp = client.get("/api/pipelines/nonexistent-id")
        assert resp.status_code == 404

    def test_pipeline_empty_stages_400(self, client):
        resp = client.post(
            "/api/pipelines/execute",
            json={
                "stages": [],
                "input_text": "test",
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Routing routes
# ---------------------------------------------------------------------------


class TestRoutingRoutes:
    def test_get_routing_config_all(self, client):
        resp = client.get("/api/routing")
        assert resp.status_code == 200
        data = resp.json()
        assert "routing_configs" in data
        assert data["total_systems"] >= 1

    def test_get_routing_config_by_system(self, client):
        resp = client.get("/api/routing", params={"system_key": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["system_key"] == "test"
        assert "agent_routing" in data

    def test_get_routing_system_not_found(self, client):
        resp = client.get("/api/routing", params={"system_key": "nope"})
        assert resp.status_code == 404

    def test_update_routing(self, client):
        resp = client.put(
            "/api/routing",
            json={
                "system_key": "test",
                "agent_routing": {
                    "orchestrator": ["help", "general"],
                    "writer": ["write", "blog", "content"],
                },
            },
        )
        assert resp.status_code == 200
        assert "writer" in resp.json()["agents_configured"]

    def test_update_routing_missing_system_404(self, client):
        resp = client.put(
            "/api/routing",
            json={
                "system_key": "nope",
                "agent_routing": {"a": ["b"]},
            },
        )
        assert resp.status_code == 404

    def test_test_routing(self, client):
        resp = client.post(
            "/api/routing/test",
            json={
                "message": "help me with a question",
                "system_key": "test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "selected_agent" in data
        assert "scores" in data

    def test_routing_analytics(self, client):
        # Generate some routing events first
        client.post(
            "/api/routing/test",
            json={
                "message": "help",
                "system_key": "test",
            },
        )
        resp = client.get("/api/routing/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "agent_distribution" in data

    def test_agent_stats(self, client):
        # Route something to orchestrator
        client.post(
            "/api/routing/test",
            json={
                "message": "help with general question",
                "system_key": "test",
            },
        )
        resp = client.get("/api/routing/agents/orchestrator/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_key"] == "orchestrator"
        assert "total_routes" in data


# ---------------------------------------------------------------------------
# Extensions routes (graceful degradation)
# ---------------------------------------------------------------------------


class TestExtensionRoutes:
    def test_list_extensions_empty(self, client):
        resp = client.get("/api/extensions")
        assert resp.status_code == 200
        data = resp.json()
        assert "extensions" in data
        # Should return empty list gracefully when module not available
        assert isinstance(data["extensions"], list)


# ---------------------------------------------------------------------------
# Workflows routes (graceful degradation)
# ---------------------------------------------------------------------------


class TestWorkflowRoutes:
    def test_list_workflows_(self, client):
        resp = client.get("/api/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert "workflows" in data
        assert isinstance(data["workflows"], list)
