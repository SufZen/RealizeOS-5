"""Tests for Sprint 10 — Evolution API endpoints.

Covers:
- List suggestions (empty, with proposals)
- Approve suggestion
- Dismiss suggestion
- Not found / already decided errors
"""
import pytest
from realize_core.activity.bus import _recent_events, _subscribers
from realize_core.db.schema import init_schema, set_db_path


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    db_path = tmp_path / "test_evo.db"
    set_db_path(db_path)
    init_schema(db_path)
    _subscribers.clear()
    _recent_events.clear()
    yield db_path
    _subscribers.clear()
    _recent_events.clear()
    set_db_path(None)


@pytest.fixture
def client(setup_db):
    try:
        from fastapi import FastAPI
    except ImportError:
        pytest.skip("FastAPI not installed")

    from fastapi.testclient import TestClient
    from realize_api.routes import evolution

    # Reset the module-level engine for each test
    evolution._engine = None

    app = FastAPI()
    app.include_router(evolution.router, prefix="/api")
    return TestClient(app)


def _seed_proposal(client):
    """Seed a test proposal via the engine directly."""
    from realize_api.routes.evolution import _get_engine
    from realize_core.evolution.engine import EvolutionProposal, EvolutionType, RiskLevel

    engine = _get_engine()
    proposal = EvolutionProposal(
        id="test-001",
        evolution_type=EvolutionType.NEW_SKILL,
        title="Add SEO optimization skill",
        description="Detected frequent SEO-related queries with no matching skill.",
        risk_level=RiskLevel.LOW,
        priority=0.8,
        source="gap_detector",
        changes={"skill_name": "seo_optimizer", "triggers": ["optimize seo", "improve ranking"]},
    )
    engine.propose(proposal)
    return "test-001"


class TestEvolutionAPI:
    def test_list_empty(self, client):
        res = client.get("/api/evolution/suggestions")
        assert res.status_code == 200
        assert res.json()["total"] == 0

    def test_list_with_proposals(self, client):
        _seed_proposal(client)
        res = client.get("/api/evolution/suggestions")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["suggestions"][0]["title"] == "Add SEO optimization skill"
        assert data["pending"] == 1

    def test_approve_suggestion(self, client):
        pid = _seed_proposal(client)
        res = client.post(f"/api/evolution/suggestions/{pid}/approve")
        assert res.status_code == 200
        assert res.json()["status"] == "applied"

        # Should no longer be pending
        listing = client.get("/api/evolution/suggestions")
        assert listing.json()["pending"] == 0

    def test_dismiss_suggestion(self, client):
        pid = _seed_proposal(client)
        res = client.post(f"/api/evolution/suggestions/{pid}/dismiss", json={"reason": "Not needed"})
        assert res.status_code == 200
        assert res.json()["status"] == "rejected"

    def test_approve_not_found(self, client):
        res = client.post("/api/evolution/suggestions/nonexistent/approve")
        assert res.status_code == 404

    def test_dismiss_not_found(self, client):
        res = client.post("/api/evolution/suggestions/nonexistent/dismiss")
        assert res.status_code == 404

    def test_double_approve_fails(self, client):
        pid = _seed_proposal(client)
        client.post(f"/api/evolution/suggestions/{pid}/approve")
        res = client.post(f"/api/evolution/suggestions/{pid}/approve")
        assert res.status_code == 400

    def test_filter_by_status(self, client):
        _seed_proposal(client)
        res = client.get("/api/evolution/suggestions?status=pending")
        assert len(res.json()["suggestions"]) == 1

        res = client.get("/api/evolution/suggestions?status=applied")
        assert len(res.json()["suggestions"]) == 0
