"""Tests for Sprint 9 — agent hierarchy, delegation, org tree API.

Covers:
- Frontmatter parsing (reports_to)
- Org tree building (parent-child relationships)
- Org tree API endpoint
- Delegate skill step type
"""

import pytest
from realize_core.scheduler.hierarchy import build_org_tree, parse_agent_frontmatter

# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_parse_reports_to(self):
        content = "---\nreports_to: orchestrator\nrole: content creator\n---\n# Writer\nContent here."
        fm = parse_agent_frontmatter(content)
        assert fm["reports_to"] == "orchestrator"
        assert fm["role"] == "content creator"

    def test_no_frontmatter(self):
        content = "# Writer\nJust a heading, no frontmatter."
        fm = parse_agent_frontmatter(content)
        assert fm == {}

    def test_empty_frontmatter(self):
        content = "---\n---\n# Writer"
        fm = parse_agent_frontmatter(content)
        assert fm == {}


# ---------------------------------------------------------------------------
# Org tree building
# ---------------------------------------------------------------------------

class TestOrgTree:
    @pytest.fixture
    def kb_with_hierarchy(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        (agents_dir / "orchestrator.md").write_text(
            "---\nrole: coordinator\n---\n# Orchestrator", encoding="utf-8"
        )
        (agents_dir / "writer.md").write_text(
            "---\nreports_to: orchestrator\nrole: content\n---\n# Writer", encoding="utf-8"
        )
        (agents_dir / "analyst.md").write_text(
            "---\nreports_to: orchestrator\nrole: research\n---\n# Analyst", encoding="utf-8"
        )
        (agents_dir / "reviewer.md").write_text(
            "---\nreports_to: writer\nrole: quality\n---\n# Reviewer", encoding="utf-8"
        )

        sys_conf = {
            "agents": {
                "orchestrator": "agents/orchestrator.md",
                "writer": "agents/writer.md",
                "analyst": "agents/analyst.md",
                "reviewer": "agents/reviewer.md",
            }
        }
        return tmp_path, sys_conf

    def test_builds_tree(self, kb_with_hierarchy):
        kb_path, sys_conf = kb_with_hierarchy
        result = build_org_tree(kb_path, sys_conf)

        assert "tree" in result
        assert "agents" in result
        assert len(result["agents"]) == 4

        # Orchestrator is root
        assert len(result["tree"]) == 1
        root = result["tree"][0]
        assert root["key"] == "orchestrator"

        # Writer and analyst report to orchestrator
        child_keys = {c["key"] for c in root["children"]}
        assert "writer" in child_keys
        assert "analyst" in child_keys

        # Reviewer reports to writer
        writer_node = [c for c in root["children"] if c["key"] == "writer"][0]
        assert len(writer_node["children"]) == 1
        assert writer_node["children"][0]["key"] == "reviewer"

    def test_flat_agents_no_hierarchy(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "a.md").write_text("# Agent A", encoding="utf-8")
        (agents_dir / "b.md").write_text("# Agent B", encoding="utf-8")

        sys_conf = {"agents": {"a": "agents/a.md", "b": "agents/b.md"}}
        result = build_org_tree(tmp_path, sys_conf)

        # All agents are roots (no reports_to)
        assert len(result["tree"]) == 2

    def test_empty_agents(self, tmp_path):
        result = build_org_tree(tmp_path, {"agents": {}})
        assert result["tree"] == []


# ---------------------------------------------------------------------------
# Org Tree API
# ---------------------------------------------------------------------------

class TestOrgTreeAPI:
    @pytest.fixture
    def client(self, tmp_path):
        try:
            from fastapi import FastAPI
        except ImportError:
            pytest.skip("FastAPI not installed")

        from realize_core.db.schema import init_schema, set_db_path
        db_path = tmp_path / "test.db"
        set_db_path(db_path)
        init_schema(db_path)

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "orchestrator.md").write_text("---\nrole: lead\n---\n# Orch", encoding="utf-8")
        (agents_dir / "writer.md").write_text("---\nreports_to: orchestrator\n---\n# Writer", encoding="utf-8")

        from fastapi.testclient import TestClient
        from realize_api.routes import ventures

        app = FastAPI()
        app.include_router(ventures.router, prefix="/api")
        app.state.systems = {
            "v1": {
                "name": "Test", "agents": {
                    "orchestrator": "agents/orchestrator.md",
                    "writer": "agents/writer.md",
                },
                "agents_dir": "agents", "foundations": "", "brain_dir": "",
                "routines_dir": "", "insights_dir": "", "creations_dir": "",
            },
        }
        app.state.kb_path = tmp_path
        yield TestClient(app)
        set_db_path(None)

    def test_org_tree_endpoint(self, client):
        res = client.get("/api/ventures/v1/org-tree")
        assert res.status_code == 200
        data = res.json()
        assert len(data["tree"]) == 1
        assert data["tree"][0]["key"] == "orchestrator"
        assert len(data["tree"][0]["children"]) == 1

    def test_org_tree_not_found(self, client):
        res = client.get("/api/ventures/fake/org-tree")
        assert res.status_code == 404
