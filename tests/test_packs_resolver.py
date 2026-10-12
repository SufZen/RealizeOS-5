"""Pack loader, cascade and MCP tools (spec 010, STORY-42)."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from realize_core.config import get_features
from realize_core.packs import (
    PackResolver,
    build_pack_context,
    clear_cache,
    discover_packs,
    get_resolver,
    load_pack,
    read_venture_packs,
)
from realize_core.packs.models import RuleCard


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yaml(path: Path, data) -> None:
    _write(path, yaml.safe_dump(data, allow_unicode=True))


def _rule(rid: str, statement: str, *, kinds=("payment_claim",), level=1, review_by="2099-01-01", source=True) -> str:
    meta = {
        "id": rid,
        "statement": statement,
        "as_of": "2026-10-13",
        "review_by": review_by,
        "verification": level,
        "applies_to": {"family": "money-event", "kinds": list(kinds)},
    }
    if source:
        meta["source"] = "https://example.org/" + rid
    return "---\n" + yaml.safe_dump(meta, allow_unicode=True) + "---\nWhy it matters.\n"


@pytest.fixture
def packs_root(tmp_path: Path) -> Path:
    root = tmp_path / "packs"
    dev = root / "profession" / "developer"
    _yaml(dev / "pack.yaml", {"id": "developer", "kind": "profession", "version": "0.1.0", "title": "Developer"})
    _yaml(dev / "glossary" / "en.yaml", [{"term": "payment claim", "family": "money-event", "kind": "payment_claim"}])
    _write(dev / "documents" / "investor-report.md", "# Investor report\n")
    _yaml(dev / "R-routines" / "skills" / "payment.yaml", {"id": "payment_milestone_check"})
    _yaml(dev / "trust.yaml", {"drive_upload": "approve"})
    _yaml(dev / "measures.yaml", [{"id": "claims_checked", "label": "Payment claims checked"}])
    _write(dev / "rules" / "retention.md", _rule("dev.retention", "Hold retention until handover.", level=4))
    il = root / "market" / "il"
    _yaml(
        il / "pack.yaml",
        {
            "id": "il",
            "kind": "market",
            "version": "0.1.0",
            "title": "Israel",
            "languages": ["he", "en"],
            "defaults": {"currency": "ILS", "locale": "he-IL"},
            "verification": {"level": 1},
            "limits": ["Does not replace a lawyer."],
        },
    )
    _yaml(il / "glossary" / "he.yaml", [{"term": "חשבון חלקי", "family": "money-event", "kind": "payment_claim"}])
    _write(il / "rules" / "index.md", _rule("il.index", "Claims are linked to the construction input index."))
    _write(il / "rules" / "bad.md", _rule("il.bad", "No source here.", source=False))
    _write(il / "documents" / "investor-report.md", "# דוח משקיעים\n")
    pt = root / "market" / "pt"
    _yaml(
        pt / "pack.yaml",
        {"id": "pt", "kind": "market", "version": "0.1.0", "title": "Portugal", "defaults": {"currency": "EUR"}},
    )
    _yaml(pt / "glossary" / "pt.yaml", [{"term": "auto de medição", "family": "money-event", "kind": "payment_claim"}])
    return root


@pytest.fixture
def venture(tmp_path: Path) -> Path:
    v = tmp_path / "systems" / "dev-co"
    _yaml(v / "packs.yaml", {"profession": [{"id": "developer", "version": "0.1.0"}], "market": [{"id": "il"}]})
    return v


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


def test_packs_flag_defaults_off():
    assert get_features({})["packs"] is False


def test_load_pack_skips_rule_cards_without_source(packs_root):
    pack = load_pack(packs_root / "market" / "il")
    assert set(pack.rules) == {"il.index"}
    assert any("il.bad" in w or "bad.md" in w for w in pack.warnings)


def test_pack_without_manifest_is_ignored(tmp_path):
    (tmp_path / "profession" / "empty").mkdir(parents=True)
    assert discover_packs(tmp_path) == {}


def test_read_venture_packs_accepts_strings_and_dicts(tmp_path):
    _yaml(tmp_path / "packs.yaml", {"profession": ["developer"], "market": [{"id": "pt", "version": "0.2.0"}]})
    out = read_venture_packs(tmp_path)
    assert out["profession"] == [{"id": "developer", "version": ""}]
    assert out["market"] == [{"id": "pt", "version": "0.2.0"}]


def test_flag_off_uses_firm_and_core_only(venture, packs_root):
    resolver = PackResolver(venture, enabled=False, packs_root=packs_root)
    assert resolver.packs == []
    assert resolver.resolve("term", "payment claim") is None
    core = resolver.resolve("default", "units")
    assert core.layer == "core"


def test_each_item_type_resolves_from_the_expected_layer(venture, packs_root):
    r = PackResolver(venture, enabled=True, packs_root=packs_root)
    term = r.resolve("term", "חשבון חלקי")
    assert (term.layer, term.pack_id, term.verification) == ("market", "il@0.1.0", 1)
    assert r.resolve("term", "Payment Claim").layer == "profession"
    assert r.resolve("default", "currency").value == "ILS"
    doc = r.resolve("document", "investor-report")
    assert doc.layer == "market"  # market overrides the profession template
    assert r.resolve("skill", "payment_milestone_check").layer == "profession"
    assert r.resolve("trust", "drive_upload").value == "approve"
    assert r.resolve("measure", "claims_checked").layer == "profession"
    rule = r.resolve("rule", "il.index")
    assert rule.source == "https://example.org/il.index"
    assert rule.verification == 1


def test_profession_rule_level_is_its_own(venture, packs_root):
    r = PackResolver(venture, enabled=True, packs_root=packs_root)
    assert r.resolve("rule", "dev.retention").verification == 4


def test_firm_override_wins_and_can_disable(venture, packs_root):
    overrides = venture / "F-foundations" / "overrides"
    _yaml(overrides / "defaults.yaml", {"currency": "USD"})
    _yaml(overrides / "trust.yaml", {"drive_upload": "auto"})
    _yaml(overrides / "disable.yaml", ["il.index"])
    r = PackResolver(venture, enabled=True, packs_root=packs_root)
    assert r.resolve("default", "currency").value == "USD"
    assert r.resolve("default", "currency").layer == "firm"
    assert r.resolve("trust", "drive_upload").value == "auto"
    assert r.resolve("rule", "il.index") is None
    assert "il.index" not in r.list("rule")


def test_swapping_market_pack_changes_terms_without_code(venture, packs_root):
    _yaml(venture / "packs.yaml", {"profession": ["developer"], "market": ["pt"]})
    r = PackResolver(venture, enabled=True, packs_root=packs_root)
    assert r.resolve("term", "auto de medição").pack_id == "pt@0.1.0"
    assert r.resolve("term", "חשבון חלקי") is None
    assert r.resolve("default", "currency").value == "EUR"


def test_missing_or_wrong_version_pack_is_reported(venture, packs_root):
    _yaml(venture / "packs.yaml", {"profession": [{"id": "developer", "version": "9.9.9"}], "market": ["xx"]})
    r = PackResolver(venture, enabled=True, packs_root=packs_root)
    assert r.packs == []
    assert set(r.missing) == {"profession/developer@9.9.9", "market/xx@*"}


def test_unknown_item_type_raises(venture, packs_root):
    with pytest.raises(ValueError, match="Unknown item type"):
        PackResolver(venture, enabled=True, packs_root=packs_root).resolve("colour", "x")


def test_expired_review_drops_level_to_one():
    card = RuleCard(id="x", statement="s", source="u", as_of="2026-01-01", review_by="2020-01-01", verification=3)
    assert card.effective_level(4) == 1
    fresh = RuleCard(id="y", statement="s", source="u", as_of="2026-01-01", review_by="2099-01-01", verification=3)
    assert fresh.effective_level(2) == 2
    assert fresh.effective_level(None) == 3


def test_cache_rebuilds_when_packs_yaml_changes(venture, packs_root):
    first = get_resolver(venture, enabled=True, packs_root=packs_root)
    assert get_resolver(venture, enabled=True, packs_root=packs_root) is first
    time.sleep(0.01)
    _yaml(venture / "packs.yaml", {"market": ["pt"]})
    later = time.time() + 5
    os.utime(venture / "packs.yaml", (later, later))
    second = get_resolver(venture, enabled=True, packs_root=packs_root)
    assert second is not first
    assert [p.id for p in second.packs] == ["pt"]


def test_pack_context_lists_terms_rules_and_sources(venture, packs_root):
    r = PackResolver(venture, enabled=True, packs_root=packs_root)
    sources: list[dict] = []
    text = build_pack_context(r, "Please check this חשבון חלקי from the contractor", sources)
    assert "currency=ILS" in text
    assert "Does not replace a lawyer." in text
    assert "חשבון חלקי → money-event/payment_claim" in text
    assert "[R1]" in text
    assert sources[0]["id"] == "R1"
    assert {s["layer"] for s in sources} <= {"market", "profession"}
    assert all("verification" in s for s in sources)


def test_pack_context_empty_without_packs(venture, packs_root):
    r = PackResolver(venture, enabled=False, packs_root=packs_root)
    assert build_pack_context(r, "hello") == ""


def test_build_system_prompt_adds_pack_layer(tmp_path, venture, packs_root, monkeypatch):
    from realize_core.packs import loader
    from realize_core.prompt import builder

    monkeypatch.setattr(loader, "default_packs_root", lambda: packs_root)
    system_config = {"system_dir": "systems/dev-co", "name": "Dev Co"}
    sources: list[dict] = []
    prompt = builder.build_system_prompt(
        tmp_path, system_config, "dev-co", user_message="חשבון חלקי", features={"packs": True}, sources_out=sources
    )
    assert "Local context (profession and market packs)" in prompt
    assert any(s.get("id") == "R1" for s in sources)
    off = builder.build_system_prompt(tmp_path, system_config, "dev-co", user_message="x", features={})
    assert "Local context" not in off


def _state(tmp_path: Path, packs_on: bool):
    return SimpleNamespace(
        systems={"dev-co": {"system_dir": "systems/dev-co"}},
        kb_path=tmp_path,
        config={"features": {"packs": packs_on}},
    )


def test_mcp_tools(tmp_path, venture, packs_root, monkeypatch):
    from realize_core.mcp_server.tools import pack_tools
    from realize_core.packs import loader

    monkeypatch.setattr(loader, "default_packs_root", lambda: packs_root)
    state = _state(tmp_path, True)
    listed = asyncio.run(pack_tools.list_packs({"venture_key": "dev-co"}, state, None))
    assert [p["id"] for p in listed["packs"]] == ["il", "developer"]
    found = asyncio.run(
        pack_tools.resolve_pack_item({"venture_key": "dev-co", "item_type": "rule", "key": "il.index"}, state, None)
    )
    assert found["found"]
    assert found["verification"] == 1
    assert found["value"]["source"].startswith("https://")
    term = asyncio.run(pack_tools.glossary_lookup({"venture_key": "dev-co", "term": "חשבון חלקי"}, state, None))
    assert (term["family"], term["kind"], term["layer"]) == ("money-event", "payment_claim", "market")
    missing = asyncio.run(pack_tools.list_packs({"venture_key": "nope"}, state, None))
    assert missing["code"] == "MCP_NOT_FOUND"


def test_mcp_tools_are_registered_and_venture_guarded():
    from realize_core.mcp_server import registry, venture_guard

    registry.reset_for_tests()
    reg = registry.get_registry()
    for name in ("list_packs", "resolve_pack_item", "glossary_lookup"):
        assert reg.get(name).family == "kb"
        assert name in venture_guard.NEEDS_VENTURE
        assert venture_guard.TOOL_PERMISSIONS[name] == "system:read"
