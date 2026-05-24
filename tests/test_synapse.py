"""
Tests for Synapse — Knowledge Indexer.
"""

from pathlib import Path

import pytest

from realize_core.fabric.crud import create_entity
from realize_core.fabric.synapse import Synapse


def _setup_venture(tmp_path):
    """Create a minimal FABRIC venture with test entities."""
    venture_dir = tmp_path / "systems" / "test-biz"
    for layer in ["F-foundations", "A-agents", "B-brain", "R-routines", "I-insights", "C-creations"]:
        (venture_dir / layer).mkdir(parents=True, exist_ok=True)

    # Create test entities
    create_entity(
        venture_dir=venture_dir,
        entity_type="decision",
        title="Pricing Model",
        body="## Rationale\n\nSetup-plus-maintenance avoids SaaS lock-in.\n\nSee [[contact-meirav]] for review.",
        frontmatter={"status": "committed", "date": "2026-05-20", "tags": ["pricing", "strategy"]},
        venture="test-biz",
    )

    create_entity(
        venture_dir=venture_dir,
        entity_type="contact",
        title="Meirav Levi",
        frontmatter={"name": "Meirav Levi", "relationship": "partner", "tags": ["partner"]},
        venture="test-biz",
    )

    create_entity(
        venture_dir=venture_dir,
        entity_type="insight",
        title="International Leads Pattern",
        body="International leads convert at 3x the rate but require 2x the touchpoints.",
        frontmatter={
            "kind": "pattern",
            "summary": "International leads convert higher but slower than domestic.",
            "tags": ["sales", "funnel"],
        },
        venture="test-biz",
    )

    return venture_dir


class TestSynapseIndexing:
    def test_index_venture(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")

        count = synapse.index_venture(venture_dir, venture="test-biz")
        assert count == 3

        synapse.close()

    def test_toc(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        toc = synapse.toc(venture="test-biz")
        assert len(toc) == 3

        types = {entry["type"] for entry in toc}
        assert "decision" in types
        assert "contact" in types
        assert "insight" in types

        synapse.close()

    def test_toc_all_ventures(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        toc = synapse.toc()  # No venture filter
        assert len(toc) == 3

        synapse.close()


class TestSynapseSearch:
    def test_fts_search(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        results = synapse.search("pricing")
        assert len(results) >= 1

        synapse.close()

    def test_scoped_search(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        results = synapse.search("pricing", scope="test-biz")
        assert len(results) >= 1

        results = synapse.search("pricing", scope="nonexistent")
        assert len(results) == 0

        synapse.close()


class TestSynapseGraphQueries:
    def test_by_type(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        decisions = synapse.by_type("decision")
        assert len(decisions) == 1
        assert decisions[0]["type"] == "decision"

        synapse.close()

    def test_by_tag(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        tagged = synapse.by_tag("pricing")
        assert len(tagged) >= 1

        synapse.close()

    def test_recent(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        recent = synapse.recent(n=5)
        assert len(recent) == 3

        synapse.close()

    def test_orphans(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        orphans = synapse.orphans()
        # All entities should be orphans initially (no inbound refs in our test data)
        assert len(orphans) >= 1

        synapse.close()

    def test_get_entity(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        # Get by type to find an ID
        decisions = synapse.by_type("decision")
        assert len(decisions) == 1

        entity = synapse.get(decisions[0]["id"])
        assert entity is not None
        assert entity["type"] == "decision"

        synapse.close()

    def test_get_nonexistent(self, tmp_path):
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        entity = synapse.get("nonexistent-id")
        assert entity is None
        synapse.close()


class TestSynapseMissionMemory:
    def test_mission_memory_crud(self, tmp_path):
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")

        # Initially empty
        assert synapse.mission_memory("m-2026-05-20-test-001") is None

        # Create
        synapse.update_mission_memory(
            mission_id="m-2026-05-20-test-001",
            summary="Finding properties in Setúbal",
            decisions=["dec-2026-05-pricing-001"],
            blockers=["Waiting for heir contact verification"],
        )

        # Read
        memory = synapse.mission_memory("m-2026-05-20-test-001")
        assert memory is not None
        assert "Setúbal" in memory["summary"]
        assert len(memory["decisions"]) == 1
        assert len(memory["blockers"]) == 1

        # Update
        synapse.update_mission_memory(
            mission_id="m-2026-05-20-test-001",
            summary="Properties found, contacting heirs",
            decisions=["dec-2026-05-pricing-001"],
            blockers=[],
        )

        memory = synapse.mission_memory("m-2026-05-20-test-001")
        assert "contacting heirs" in memory["summary"]
        assert len(memory["blockers"]) == 0

        synapse.close()


class TestSynapseStats:
    def test_stats(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        stats = synapse.stats(venture="test-biz")
        assert stats["entity_count"] == 3
        assert stats["tag_count"] >= 1
        assert "decision" in stats["type_counts"]

        synapse.close()

    def test_stats_global(self, tmp_path):
        venture_dir = _setup_venture(tmp_path)
        synapse = Synapse(db_path=tmp_path / "test-synapse.db")
        synapse.index_venture(venture_dir, venture="test-biz")

        stats = synapse.stats()
        assert stats["entity_count"] == 3

        synapse.close()
