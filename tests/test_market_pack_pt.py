"""Agent-drafted Portugal market pack and pack verification (STORY-45)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest
import yaml
from realize_core.governance.gates import Decider
from realize_core.packs import PackResolver, clear_cache, discover_packs, load_pack
from realize_core.packs.verify import PackVerificationError, request_verification, validate_request

PACKS = Path(__file__).parent.parent / "packs"


def test_portugal_pack_meets_the_drafting_bar():
    pt = discover_packs(PACKS)[("market", "pt")]
    assert pt.warnings == []
    assert len(pt.terms) >= 15
    assert 10 <= len(pt.rules) <= 20
    for card in pt.rules.values():
        assert card.source.startswith("https://")
        assert card.as_of
        assert card.review_by
        assert card.verification == 1
    assert pt.defaults["currency"] == "EUR"
    assert pt.verification_level == 1
    assert pt.limits


def test_same_developer_workflow_runs_in_portugal_without_code_changes(tmp_path):
    clear_cache()
    venture = tmp_path / "systems" / "pt-dev"
    venture.mkdir(parents=True)
    (venture / "packs.yaml").write_text("profession: [developer]\nmarket: [pt]\n", encoding="utf-8")
    r = PackResolver(venture, enabled=True, packs_root=PACKS)
    claim = r.resolve("term", "auto de medição")
    assert (claim.value["family"], claim.value["kind"], claim.layer) == ("money-event", "payment_claim", "market")
    assert r.resolve("term", "payment claim").layer == "profession"
    assert r.resolve("default", "currency").value == "EUR"
    assert r.resolve("measure", "payment_claims_checked") is not None
    assert r.resolve("rule", "pt.vat.rates").verification == 1


@pytest.mark.parametrize(
    ("level", "reviewer", "agreement", "message"),
    [
        (4, "x", None, "level 4"),
        (1, "x", None, "Only levels"),
        (2, " ", None, "named reviewer"),
        (3, "x", "", "partner maintenance agreement"),
    ],
)
def test_verification_rules(level, reviewer, agreement, message):
    with pytest.raises(PackVerificationError, match=message):
        validate_request(level, reviewer, agreement)


@pytest.fixture
def db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


@pytest.fixture
def pack_copy(tmp_path, monkeypatch) -> Path:
    from realize_core.packs import loader

    root = tmp_path / "packs"
    shutil.copytree(PACKS / "market" / "pt", root / "market" / "pt")
    monkeypatch.setattr(loader, "default_packs_root", lambda: root)
    return root


OWNER = Decider(user_id="asaf", role="owner", allowed_ventures=None)


def test_approved_verification_raises_the_pack_level(db, pack_copy):
    from realize_core.governance.gates import decide_approval

    manifest_before = (pack_copy / "market" / "pt" / "pack.yaml").read_bytes()
    approval_id = request_verification(
        "ops", kind="market", pack_id="pt", level=2, reviewer="Ana Silva, advogada", corrections={"pt.vat.rates": 1}
    )
    out = asyncio.run(decide_approval(approval_id, True, decider=OWNER))
    assert out["execution"]["executed"] is True
    assert out["execution"]["success"] is True
    assert "market/pt and its" in out["execution"]["output"]
    pack = load_pack(pack_copy / "market" / "pt")
    assert pack.verification_level == 2
    assert all(c.verification == 2 and c.verified_by == "Ana Silva, advogada" for c in pack.rules.values())
    assert pack.verification["approved_by"] == "asaf"
    assert pack.verification["corrections"] == {"pt.vat.rates": 1}
    assert pack.verification["approval_id"] == approval_id
    # Recorded as operational data; the shipped manifest is untouched (audit N04).
    assert (pack_copy / "market" / "pt" / "pack.yaml").read_bytes() == manifest_before
    assert yaml.safe_load(manifest_before)["verification"]["level"] == 1


def test_card_level_verification_keeps_pack_level(db, pack_copy):
    from realize_core.governance.gates import decide_approval

    approval_id = request_verification(
        "ops", kind="market", pack_id="pt", level=2, reviewer="R", cards=["pt.vat.rates"]
    )
    asyncio.run(decide_approval(approval_id, True, decider=OWNER))
    pack = load_pack(pack_copy / "market" / "pt")
    assert pack.verification_level == 1
    assert pack.rules["pt.vat.rates"].verification == 2
    assert pack.rules["pt.contracts.price-revision"].verification == 1


def test_rejected_verification_changes_nothing(db, pack_copy):
    from realize_core.governance.gates import decide_approval
    from realize_core.packs import state

    before = (pack_copy / "market" / "pt" / "pack.yaml").read_text(encoding="utf-8")
    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="R")
    out = asyncio.run(decide_approval(approval_id, False, decider=OWNER))
    assert out["approval"]["status"] == "rejected"
    assert (pack_copy / "market" / "pt" / "pack.yaml").read_text(encoding="utf-8") == before
    assert not state.state_path().exists()
    assert load_pack(pack_copy / "market" / "pt").verification_level == 1


def test_unknown_pack_cannot_be_requested(db, pack_copy):
    with pytest.raises(PackVerificationError, match="not installed"):
        request_verification("ops", kind="market", pack_id="zz", level=2, reviewer="R")
