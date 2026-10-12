"""Core language schemas (spec 010, STORY-41) and the validator's allOf support."""

import json
from pathlib import Path

import pytest
from realize_core.fabric.validator import SchemaRegistry, _type_matches, validate_entity

SCHEMAS = Path(__file__).parent.parent / "docs" / "fabric-schemas"
CORE_FAMILIES = ["project", "source", "requirement", "money-event", "milestone", "change", "issue"]


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry()


@pytest.mark.parametrize("family", CORE_FAMILIES)
def test_core_family_schema_is_well_formed(family):
    schema = json.loads((SCHEMAS / f"{family}.json").read_text(encoding="utf-8"))
    assert schema["$id"].endswith(f"/{family}.json")
    assert schema["properties"]["type"]["const"] == family
    assert "kind" in schema["properties"]
    assert schema["additionalProperties"] is True
    assert schema["x-core-family"] is True
    assert "x-indexing" in schema


@pytest.mark.parametrize("family", ["requirement", "money-event", "milestone", "change", "issue"])
def test_obligation_families_carry_sources(family):
    schema = json.loads((SCHEMAS / f"{family}.json").read_text(encoding="utf-8"))
    item = schema["properties"]["sources"]["items"]["properties"]
    assert set(item) == {"source", "locator"}


def test_decision_and_contact_extended(registry):
    decision = registry.get_schema("decision")["properties"]
    assert {"approval_id", "basis", "affects", "project"} <= set(decision)
    assert "project_roles" in registry.get_schema("contact")["properties"]


def test_money_event_without_currency_warns(registry):
    result = validate_entity({"type": "money-event", "kind": "payment_claim", "amount": 1200}, registry=registry)
    assert any(w.field == "currency" for w in result.warnings)


def test_valid_payment_claim_has_no_warnings(registry):
    entity = {
        "type": "money-event",
        "kind": "payment_claim",
        "amount": 1200.5,
        "currency": "ILS",
        "status": "submitted",
        "sources": [{"source": "src-2026-10-claim-3", "locator": "p.2"}],
    }
    assert validate_entity(entity, registry=registry).valid


def test_pack_extension_resolves_core_fields(registry):
    extension = {
        "$id": "pack://developer/payment-claim.json",
        "allOf": [{"$ref": "https://realizeos.ai/schemas/v0.1/money-event.json"}],
        "properties": {"kind": {"const": "payment_claim"}, "retention_percent": {"type": "number"}},
        "required": ["milestone"],
    }
    assert registry.register("payment-claim", extension) == []
    resolved = registry.get_schema("payment-claim")
    assert {"amount", "currency", "retention_percent"} <= set(resolved["properties"])
    assert {"type", "amount", "currency", "milestone"} <= set(resolved["required"])

    result = validate_entity(
        {"type": "payment-claim", "kind": "invoice", "amount": 5, "currency": "EUR"}, registry=registry
    )
    fields = {w.field for w in result.warnings}
    assert {"kind", "milestone"} <= fields


def test_extension_by_file_name_ref(registry):
    registry.register("site-visit", {"allOf": [{"$ref": "issue.json"}], "properties": {}})
    assert "severity" in registry.get_schema("site-visit")["properties"]


def test_retyping_a_core_property_is_reported(registry):
    bad = {"allOf": [{"$ref": "money-event.json"}], "properties": {"amount": {"type": "string"}}}
    problems = registry.register("bad-claim", bad)
    assert problems
    assert "amount" in problems[0]


def test_missing_ref_is_tolerated(registry):
    registry.register("orphan", {"allOf": [{"$ref": "nope.json"}], "properties": {"x": {"type": "string"}}})
    assert validate_entity({"type": "orphan", "x": "y"}, registry=registry).valid


def test_type_matching_handles_unions_and_booleans():
    assert _type_matches(None, ["string", "null"])
    assert _type_matches("a", ["string", "null"])
    assert not _type_matches(True, "number")
    assert _type_matches(3, "number")
