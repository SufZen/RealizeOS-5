"""Developer profession pack and Israel market pack (STORY-43)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from realize_core.fabric.validator import SchemaRegistry, validate_entity
from realize_core.packs import PackResolver, clear_cache, discover_packs

PACKS = Path(__file__).parent.parent / "packs"
HEBREW = re.compile(r"[֐-׿]")


@pytest.fixture(scope="module")
def packs():
    return discover_packs(PACKS)


def test_both_packs_load_cleanly(packs):
    dev = packs[("profession", "developer")]
    il = packs[("market", "il")]
    assert dev.warnings == []
    assert il.warnings == []
    assert (dev.version, il.version) == ("0.1.0", "0.1.0")


def test_israel_pack_has_terms_rules_and_defaults(packs):
    il = packs[("market", "il")]
    assert len(il.terms) >= 10
    assert len(il.rules) >= 5
    for card in il.rules.values():
        assert card.source.startswith("https://")
        assert card.as_of
        assert card.verification == 1
    assert il.defaults["currency"] == "ILS"
    assert il.defaults["work_week"] == ["sun", "mon", "tue", "wed", "thu"]
    assert il.verification_level == 1
    assert il.limits


def test_developer_pack_is_market_neutral():
    dev_root = PACKS / "profession" / "developer"
    for path in dev_root.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert not HEBREW.search(text), path
            for marker in ("ILS", "3210", "Portugal", "Israel", "EUR"):
                assert marker not in text, (path, marker)


def test_glossary_families_are_core_families(packs):
    core = {"project", "contact", "source", "requirement", "money-event", "milestone", "change", "decision", "issue"}
    for pack in packs.values():
        for entry in pack.terms.values():
            assert entry["family"] in core, entry


def test_developer_schemas_extend_core_cleanly(packs):
    registry = SchemaRegistry()
    for name, schema in packs[("profession", "developer")].schemas.items():
        assert registry.register(name, schema) == [], name
    claim = {
        "type": "payment-claim",
        "kind": "payment_claim",
        "amount": 120000,
        "currency": "EUR",
        "milestone": "mil-2026-10-frame-1",
        "counterparty": "contractor-a",
    }
    assert validate_entity(claim, registry=registry).valid


def test_scaffold_writes_packs_yaml(tmp_path):
    from realize_core.scaffold import scaffold_venture

    (tmp_path / "realize-os.yaml").write_text("name: test\nsystems: []\n", encoding="utf-8")
    scaffold_venture(tmp_path, "dev-co", template="real-estate-developer")
    data = yaml.safe_load((tmp_path / "systems" / "dev-co" / "packs.yaml").read_text(encoding="utf-8"))
    assert data == {"profession": ["developer"], "market": []}


def test_scaffold_without_packs_writes_nothing(tmp_path):
    from realize_core.scaffold import scaffold_venture

    (tmp_path / "realize-os.yaml").write_text("name: test\nsystems: []\n", encoding="utf-8")
    scaffold_venture(tmp_path, "plain")
    assert not (tmp_path / "systems" / "plain" / "packs.yaml").exists()


def test_israeli_developer_venture_resolves_through_both_packs(tmp_path):
    clear_cache()
    venture = tmp_path / "systems" / "il-dev"
    venture.mkdir(parents=True)
    (venture / "packs.yaml").write_text("profession: [developer]\nmarket: [il]\n", encoding="utf-8")
    r = PackResolver(venture, enabled=True, packs_root=PACKS)
    claim = r.resolve("term", "חשבון חלקי")
    assert (claim.value["kind"], claim.layer) == ("payment_claim", "market")
    assert r.resolve("term", "payment claim").layer == "profession"
    assert r.resolve("default", "currency").value == "ILS"
    assert r.resolve("rule", "il.sale-law.buyer-funds-secured").verification == 1
    assert r.resolve("measure", "payment_claims_checked").layer == "profession"


def test_webinar_demo_venture_gets_the_developer_pack(tmp_path):
    from realize_core.demo_seed import DEMO_KEY, seed_webinar_demo

    clear_cache()
    (tmp_path / "realize-os.yaml").write_text("name: test\nsystems: []\n", encoding="utf-8")
    seed_webinar_demo(tmp_path)
    venture = tmp_path / "systems" / DEMO_KEY
    r = PackResolver(venture, enabled=True, packs_root=PACKS)
    assert [p.id for p in r.packs] == ["developer"]
    assert r.resolve("measure", "payment_claims_checked") is not None
    off = PackResolver(venture, enabled=False, packs_root=PACKS)
    assert off.packs == []
