"""Every market pack loads cleanly and runs the developer workflows (STORY-47)."""

from __future__ import annotations

from pathlib import Path

import pytest
from realize_core.packs import PackResolver, clear_cache, discover_packs

PACKS = Path(__file__).parent.parent / "packs"
DRAFTED = {"pt": "EUR", "gr": "EUR", "cy": "EUR", "es": "EUR", "uk": "GBP", "us": "USD"}
CORE_FAMILIES = {
    "project",
    "contact",
    "source",
    "requirement",
    "money-event",
    "milestone",
    "change",
    "decision",
    "issue",
}


@pytest.fixture(scope="module")
def packs():
    return discover_packs(PACKS)


@pytest.mark.parametrize("code", sorted(DRAFTED))
def test_market_pack_meets_the_level_1_bar(packs, code):
    pack = packs[("market", code)]
    assert pack.warnings == []
    assert pack.verification_level == 1
    assert pack.defaults["currency"] == DRAFTED[code]
    assert pack.defaults["country"]
    assert pack.limits
    assert len(pack.terms) >= 15
    assert len(pack.rules) >= 10
    for card in pack.rules.values():
        assert card.source.startswith("https://"), card.id
        assert card.as_of
        assert card.review_by
        assert card.id.startswith(f"{code}.")
        assert card.applies_to.get("family") in CORE_FAMILIES, card.id
    for entry in pack.terms.values():
        assert entry["family"] in CORE_FAMILIES, entry
    readme = (pack.root / "README.md").read_text(encoding="utf-8")
    assert "Missing" in readme
    assert "review" in readme.lower()


@pytest.mark.parametrize("code", sorted(DRAFTED))
def test_developer_workflows_resolve_in_every_market(tmp_path, code):
    clear_cache()
    venture = tmp_path / "systems" / f"dev-{code}"
    venture.mkdir(parents=True)
    (venture / "packs.yaml").write_text(f"profession: [developer]\nmarket: [{code}]\n", encoding="utf-8")
    r = PackResolver(venture, enabled=True, packs_root=PACKS)
    assert [p.id for p in r.packs] == [code, "developer"]
    assert r.resolve("default", "currency").layer == "market"
    assert r.resolve("measure", "payment_claims_checked").layer == "profession"
    claim_terms = [e for e in r.list("term").values() if e.value.get("kind") == "payment_claim"]
    assert claim_terms, f"{code} has no local term for a payment claim"


def test_rule_ids_are_unique_across_packs(packs):
    seen: dict[str, str] = {}
    for (kind, pid), pack in packs.items():
        for rid in pack.rules:
            assert rid not in seen, f"{rid} in {pid} and {seen.get(rid)}"
            seen[rid] = pid
