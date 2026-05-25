"""
Tests for the FABRIC Entity System: parser, writer, refs, tags, CRUD, and validation.
"""

from datetime import datetime

from realize_core.fabric.crud import create_entity, delete_entity, read_entity, scan_venture, update_entity
from realize_core.fabric.entity import FabricEntity
from realize_core.fabric.id_gen import generate_id, parse_id_type
from realize_core.fabric.parser import parse_entity, parse_frontmatter
from realize_core.fabric.refs import extract_refs
from realize_core.fabric.tags import extract_tags
from realize_core.fabric.validator import SchemaRegistry, validate_entity
from realize_core.fabric.writer import write_entity

# ─── Frontmatter Parsing ─────────────────────────────────────────────────────

class TestFrontmatterParsing:
    def test_basic_frontmatter(self):
        content = "---\ntitle: Test\ntype: decision\n---\nBody text here."
        fm, body = parse_frontmatter(content)
        assert fm["title"] == "Test"
        assert fm["type"] == "decision"
        assert body.strip() == "Body text here."

    def test_no_frontmatter(self):
        content = "Just body text."
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == "Just body text."

    def test_empty_frontmatter(self):
        content = "---\n---\nBody."
        fm, body = parse_frontmatter(content)
        assert fm == {} or fm is None
        # Body should still be extracted
        assert "Body" in body

    def test_complex_frontmatter(self):
        content = """---
id: dec-2026-05-pricing-001
type: decision
title: RealizeOS pricing model
status: committed
date: "2026-05-20"
tags:
  - pricing
  - strategy
reviewers:
  - contact-meirav
ventures:
  - realizeos
confidence: 0.95
verified: true
---

## Rationale

This is the body with [[contact-meirav]] reference.
"""
        fm, body = parse_frontmatter(content)
        assert fm["id"] == "dec-2026-05-pricing-001"
        assert fm["status"] == "committed"
        assert fm["tags"] == ["pricing", "strategy"]
        assert fm["confidence"] == 0.95
        assert "Rationale" in body


# ─── Reference Extraction ─────────────────────────────────────────────────────

class TestRefs:
    def test_wikilinks(self):
        refs = extract_refs({}, "See [[dec-2026-05-pricing-001]] and [[contact-meirav]].")
        assert "dec-2026-05-pricing-001" in refs
        assert "contact-meirav" in refs

    def test_wikilink_with_display(self):
        refs = extract_refs({}, "See [[dec-2026-05-pricing-001|pricing decision]].")
        assert "dec-2026-05-pricing-001" in refs

    def test_xml_refs(self):
        refs = extract_refs({}, 'Based on <decision ref="dec-2026-05-pricing-001"/>.')
        assert "dec-2026-05-pricing-001" in refs

    def test_frontmatter_refs(self):
        fm = {
            "reviewers": ["contact-meirav"],
            "supersedes": "dec-2026-04-old-pricing-001",
            "related_risks": ["risk-2026-05-cash-001"],
        }
        refs = extract_refs(fm, "")
        assert "contact-meirav" in refs
        assert "dec-2026-04-old-pricing-001" in refs
        assert "risk-2026-05-cash-001" in refs

    def test_combined_refs(self):
        fm = {"reviewers": ["contact-meirav"]}
        body = "See [[dec-2026-05-pricing-001]] and <insight ref=\"insight-2026-05-funnel-001\"/>."
        refs = extract_refs(fm, body)
        assert len(refs) >= 3

    def test_no_refs(self):
        refs = extract_refs({}, "No references here.")
        assert refs == []


# ─── Tag Extraction ───────────────────────────────────────────────────────────

class TestTags:
    def test_frontmatter_tags(self):
        tags = extract_tags({"tags": ["pricing", "Strategy"]}, "")
        assert "pricing" in tags
        assert "strategy" in tags  # lowercased

    def test_inline_tags(self):
        tags = extract_tags({}, "This is about <tag>real-estate</tag> investments.")
        assert "real-estate" in tags

    def test_combined_tags(self):
        tags = extract_tags(
            {"tags": ["pricing"]},
            "Also about <tag>strategy</tag> considerations.",
        )
        assert "pricing" in tags
        assert "strategy" in tags

    def test_comma_separated_string(self):
        tags = extract_tags({"tags": "pricing, strategy, ops"}, "")
        assert "pricing" in tags
        assert "strategy" in tags
        assert "ops" in tags


# ─── ID Generation ────────────────────────────────────────────────────────────

class TestIdGen:
    def test_decision_id(self):
        dt = datetime(2026, 5, 20)
        id_ = generate_id("decision", "pricing-model", seq=1, date=dt)
        assert id_ == "dec-2026-05-pricing-model-001"

    def test_mission_id(self):
        dt = datetime(2026, 5, 20)
        id_ = generate_id("mission", "find-properties", seq=1, date=dt)
        assert id_ == "m-2026-05-20-find-properties-001"

    def test_contact_id(self):
        id_ = generate_id("contact", "meirav")
        assert id_ == "contact-meirav"

    def test_insight_id(self):
        dt = datetime(2026, 5, 15)
        id_ = generate_id("insight", "funnel-pattern", seq=1, date=dt)
        assert id_ == "insight-2026-05-funnel-pattern-001"

    def test_slug_cleaning(self):
        dt = datetime(2026, 5, 20)
        id_ = generate_id("decision", "Pricing Model!!! v2", seq=1, date=dt)
        assert "pricing-model-v2" in id_
        assert "!" not in id_

    def test_parse_id_type(self):
        assert parse_id_type("dec-2026-05-pricing-001") == "decision"
        assert parse_id_type("m-2026-05-20-find-001") == "mission"
        assert parse_id_type("contact-meirav") == "contact"
        assert parse_id_type("insight-2026-05-pattern-001") == "insight"
        assert parse_id_type("unknown-id") == ""


# ─── Entity Round-Trip ────────────────────────────────────────────────────────

class TestRoundTrip:
    def test_parse_write_parse(self, tmp_path):
        """Verify parse → write → parse produces identical core fields."""
        content = """---
id: dec-2026-05-pricing-001
type: decision
title: RealizeOS pricing model
status: committed
date: "2026-05-20"
tags:
  - pricing
  - strategy
venture: realizeos
confidence: 0.95
verified: true
---

## Rationale

Setup-plus-maintenance model avoids SaaS lock-in.

See [[contact-meirav]] for board review.
"""
        source_file = tmp_path / "pricing-model.md"
        source_file.write_text(content, encoding="utf-8")

        # Parse
        entity = parse_entity(source_file, venture="realizeos")
        assert entity.id == "dec-2026-05-pricing-001"
        assert entity.type == "decision"
        assert entity.title == "RealizeOS pricing model"
        assert "pricing" in entity.tags
        assert "contact-meirav" in entity.refs

        # Write to new file
        dest_file = tmp_path / "roundtrip.md"
        write_entity(entity, path=dest_file)

        # Re-parse
        entity2 = parse_entity(dest_file, venture="realizeos")
        assert entity2.id == entity.id
        assert entity2.type == entity.type
        assert entity2.title == entity.title
        assert entity2.venture == entity.venture
        assert set(entity2.tags) == set(entity.tags)
        assert set(entity2.refs) == set(entity.refs)

    def test_entity_summary_for_toc(self):
        entity = FabricEntity(
            id="dec-2026-05-test-001",
            type="decision",
            title="Test Decision",
            slug="test-decision",
            venture="test-venture",
            tags=["test", "pricing"],
            refs=["contact-meirav"],
        )
        toc = entity.summary_for_toc()
        assert toc["id"] == "dec-2026-05-test-001"
        assert toc["type"] == "decision"
        assert toc["tags"] == ["test", "pricing"]


# ─── CRUD ─────────────────────────────────────────────────────────────────────

class TestCRUD:
    def _setup_venture(self, tmp_path):
        """Create a minimal FABRIC venture structure."""
        venture_dir = tmp_path / "systems" / "test-venture"
        for layer in ["F-foundations", "A-agents", "B-brain", "R-routines", "I-insights", "C-creations"]:
            (venture_dir / layer).mkdir(parents=True, exist_ok=True)
        return venture_dir

    def test_create_entity(self, tmp_path):
        venture_dir = self._setup_venture(tmp_path)
        entity = create_entity(
            venture_dir=venture_dir,
            entity_type="decision",
            title="Test Decision",
            body="## Context\n\nThis is a test decision.",
            created_by="user-test",
        )
        assert entity.id.startswith("dec-")
        assert entity.type == "decision"
        assert entity.path.exists()

    def test_read_entity(self, tmp_path):
        venture_dir = self._setup_venture(tmp_path)
        created = create_entity(
            venture_dir=venture_dir,
            entity_type="insight",
            title="Test Insight",
            frontmatter={"kind": "observation", "summary": "This is a test insight"},
        )
        read = read_entity(created.path)
        assert read.id == created.id
        assert read.type == "insight"

    def test_update_entity(self, tmp_path):
        venture_dir = self._setup_venture(tmp_path)
        created = create_entity(
            venture_dir=venture_dir,
            entity_type="decision",
            title="Original Title",
        )
        updated = update_entity(
            created,
            updates={"title": "Updated Title", "status": "committed"},
            modified_by="user-test",
        )
        assert updated.title == "Updated Title"
        assert updated.frontmatter["status"] == "committed"
        assert updated.last_modified_by == "user-test"

        # Verify persisted
        re_read = read_entity(updated.path)
        assert re_read.frontmatter["title"] == "Updated Title"

    def test_delete_entity(self, tmp_path):
        venture_dir = self._setup_venture(tmp_path)
        created = create_entity(
            venture_dir=venture_dir,
            entity_type="decision",
            title="To Delete",
        )
        assert created.path.exists()
        result = delete_entity(created)
        assert result is True
        assert not created.path.exists()

    def test_scan_venture(self, tmp_path):
        venture_dir = self._setup_venture(tmp_path)
        create_entity(venture_dir=venture_dir, entity_type="decision", title="Dec 1")
        create_entity(venture_dir=venture_dir, entity_type="insight", title="Insight 1",
                       frontmatter={"kind": "observation", "summary": "Test insight summary text."})
        create_entity(venture_dir=venture_dir, entity_type="contact", title="Contact 1",
                       frontmatter={"name": "Test Contact"})

        entities = scan_venture(venture_dir, venture="test-venture")
        assert len(entities) == 3
        types = {e.type for e in entities}
        assert "decision" in types
        assert "insight" in types
        assert "contact" in types


# ─── Schema Validation ────────────────────────────────────────────────────────

class TestValidation:
    def test_valid_decision(self):
        fm = {
            "type": "decision",
            "title": "Test Decision",
            "status": "committed",
            "date": "2026-05-20",
        }
        result = validate_entity(fm)
        assert result.valid
        assert result.warning_count == 0

    def test_missing_required_field(self):
        fm = {
            "type": "decision",
            "title": "Test Decision",
            # Missing: status, date
        }
        result = validate_entity(fm)
        assert not result.valid
        assert result.warning_count >= 1
        field_names = [w.field for w in result.warnings]
        assert "status" in field_names or "date" in field_names

    def test_invalid_enum_value(self):
        fm = {
            "type": "decision",
            "title": "Test Decision",
            "status": "invalid-status",
            "date": "2026-05-20",
        }
        result = validate_entity(fm)
        assert result.warning_count >= 1

    def test_unknown_type_no_validation(self):
        fm = {"type": "custom-type", "title": "Custom Entity"}
        result = validate_entity(fm)
        assert result.valid  # Unknown types pass without validation

    def test_schema_registry_loads(self):
        registry = SchemaRegistry()
        # Should load schemas from docs/fabric-schemas/
        assert isinstance(registry.known_types, list)
