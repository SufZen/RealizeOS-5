"""Review findings on packs (2026-10-13), each reproduced first.

- P1-1: unquoted YAML dates (``as_of: 2026-10-13``) no longer drop a card or
  hide its ``review_by``; a date in skill variables keeps the others; the desk
  check fails on a card the loader skipped.
- P2-1: a new approval records the next review date, so it lifts a card whose
  old date had passed.
- P2-2: an approved level binds to the card's content, not only its id.
- P3: case-insensitive ``disable.yaml``, a broken custom pack fails closed,
  and the inventory hash ignores line endings and a byte-order mark.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from realize_core.governance.gates import Decider, decide_approval
from realize_core.packs import PackResolver, clear_cache, load_pack, loader, state
from realize_core.packs.loader import load_firm_layer
from realize_core.packs.verify import request_verification

PACKS = Path(__file__).parent.parent / "packs"
OWNER = Decider(user_id="owner@x", role="owner", allowed_ventures=None)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _card(card_id: str, *, as_of: str = "2026-10-13", review_by: str = "2027-04-13", level: int = 1, **extra) -> str:
    """A rule card with UNQUOTED dates, as the docs/packs.md example writes them."""
    lines = [
        "---",
        f"id: {card_id}",
        f"statement: {extra.get('statement', 'Works carry a 9% tax.')}",
        f"source: {extra.get('source', 'https://zz.example/tax')}",
        f"as_of: {as_of}",
        f"review_by: {review_by}",
        f"verification: {level}",
        "applies_to: {family: money-event, kinds: [payment_claim]}",
        "---",
        "Body.",
        "",
    ]
    return "\n".join(lines)


@pytest.fixture
def db(tmp_path):
    from realize_core.db.schema import init_schema, set_db_path

    path = tmp_path / "ops.db"
    set_db_path(path)
    init_schema(path)
    yield path
    set_db_path(None)


@pytest.fixture
def shipped(tmp_path, monkeypatch) -> Path:
    """A copy of the Portugal pack as the shipped packs folder, with no custom folder."""
    root = tmp_path / "shipped"
    shutil.copytree(PACKS / "market" / "pt", root / "market" / "pt", ignore=shutil.ignore_patterns("reviews"))
    monkeypatch.setattr(loader, "default_packs_root", lambda: root)
    monkeypatch.delenv(loader.PACKS_PATH_ENV, raising=False)
    clear_cache()
    yield root
    clear_cache()


def _approve(approval_id: str) -> dict:
    return asyncio.run(decide_approval(approval_id, True, decider=OWNER))


def _venture(tmp_path: Path, packs_yaml: str = "market: [pt]\n") -> Path:
    venture = tmp_path / "systems" / "acme"
    _write(venture / "packs.yaml", packs_yaml)
    return venture


# ---------------------------------------------------------------------------
# P1-1: unquoted dates
# ---------------------------------------------------------------------------


def test_a_card_with_unquoted_dates_loads(tmp_path):
    root = tmp_path / "market" / "zz"
    _write(root / "pack.yaml", "id: zz\nkind: market\nversion: 1.0.0\nverification: {level: 1}\n")
    _write(root / "rules" / "tax.md", _card("zz.tax"))

    pack = load_pack(root)

    assert "zz.tax" in pack.rules, pack.warnings
    card = pack.rules["zz.tax"]
    assert (card.as_of, card.review_by) == ("2026-10-13", "2027-04-13")
    assert not any("rule card skipped" in w for w in pack.warnings)


@pytest.mark.parametrize("packs_on", [True, False])
def test_an_unquoted_review_date_that_passed_expires_a_firm_card(tmp_path, packs_on):
    """The reviewer's case: a firm card at level 3 whose review_by passed shows level 1 (as in v5.24.0)."""
    venture = _venture(tmp_path, "market: []\n")
    _write(
        venture / "F-foundations" / "overrides" / "rules" / "firm.md",
        _card("firm.retention", review_by="2026-02-01", level=3),
    )

    resolved = PackResolver(venture, enabled=packs_on).resolve("rule", "firm.retention")

    assert resolved is not None
    assert resolved.value.review_by == "2026-02-01"
    assert resolved.verification == 1


def test_an_unquoted_review_date_that_passed_expires_a_market_card(tmp_path):
    root = tmp_path / "packs"
    _write(root / "market" / "zz" / "pack.yaml", "id: zz\nkind: market\nversion: 1.0.0\nverification: {level: 3}\n")
    _write(root / "market" / "zz" / "rules" / "old.md", _card("zz.old", review_by="2026-02-01", level=3))
    _write(root / "market" / "zz" / "rules" / "new.md", _card("zz.new", review_by="2099-01-01", level=3))
    venture = _venture(tmp_path, "market: [zz]\n")

    resolver = PackResolver(venture, enabled=True, packs_root=root)

    assert resolver.resolve("rule", "zz.old").verification == 1
    assert resolver.resolve("rule", "zz.new").verification == 3


def test_an_unquoted_date_in_skill_variables_keeps_every_variable(tmp_path):
    venture = _venture(tmp_path)
    _write(
        venture / "F-foundations" / "overrides" / "skill-settings.yaml",
        "payment_milestone_check:\n  variables:\n    milestones_sheet_id: abc123\n    start_date: 2026-10-13\n",
    )

    firm = load_firm_layer(venture)

    assert firm.skill_settings["payment_milestone_check"]["variables"] == {
        "milestones_sheet_id": "abc123",
        "start_date": "2026-10-13",
    }
    assert not any("variables" in w for w in firm.warnings)


def test_unquoted_dates_elsewhere_are_text(tmp_path):
    """Glossary, trust, disable and triggers accept a date like any scalar, as ISO text."""
    venture = _venture(tmp_path)
    overrides = venture / "F-foundations" / "overrides"
    _write(overrides / "disable.yaml", "- 2026-10-13\n")
    _write(overrides / "glossary" / "en.yaml", "- term: 2026-10-13\n  family: milestone\n")
    _write(overrides / "skill-settings.yaml", "x:\n  triggers: [2026-10-13, payment]\n")

    firm = load_firm_layer(venture)

    assert firm.disabled == {"2026-10-13"}
    assert firm.terms["2026-10-13"]["term"] == "2026-10-13"
    assert firm.skill_settings["x"]["triggers"] == ["2026-10-13", "payment"]


def test_desk_check_fails_on_a_card_the_loader_skipped(shipped):
    from realize_core.cli_app import app
    from realize_core.packs.review import desk_check
    from typer.testing import CliRunner

    rules = shipped / "market" / "pt" / "rules"
    # Passes every desk check on its own (statement isn't empty), but the loader can't use it.
    (rules / "mapping.md").write_text(
        "---\nid: pt.bad.mapping\nstatement: {text: Works carry VAT.}\nsource: https://example.pt/x\n"
        "as_of: '2026-10-01'\nreview_by: '2027-04-01'\napplies_to: {family: money-event}\n---\nBody.\n",
        encoding="utf-8",
    )
    (rules / "dated.md").write_text(_card("pt.ok.unquoted"), encoding="utf-8")

    findings = desk_check("pt", today=date(2026, 10, 13))

    [skipped] = [f for f in findings if f.target == "mapping.md" and f.level == "error"]
    assert "did not load" in skipped.message
    assert "missing statement" in skipped.message
    assert not any(f.target in {"dated.md", "pt.ok.unquoted"} for f in findings)  # unquoted dates load
    result = CliRunner().invoke(app, ["packs", "desk-check", "pt", "--on", "2026-10-13"])
    assert result.exit_code == 1, result.output
    assert "mapping.md" in result.output


# ---------------------------------------------------------------------------
# P2-1: a new review records the next review date
# ---------------------------------------------------------------------------


def test_a_whole_pack_review_lifts_a_card_whose_old_date_passed(db, shipped, tmp_path):
    card = shipped / "market" / "pt" / "rules" / "vat-rates.md"
    card.write_text(
        card.read_text(encoding="utf-8").replace("review_by: '2027-04-13'", "review_by: 2026-02-01"), encoding="utf-8"
    )
    venture = _venture(tmp_path)
    assert PackResolver(venture, enabled=True).resolve("rule", "pt.vat.rates").verification == 1

    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="Ana Silva")
    assert _approve(approval_id)["execution"]["success"] is True

    today = datetime.now(UTC).date()
    expected = state.add_months(today, 6).isoformat()
    resolved = PackResolver(venture, enabled=True).resolve("rule", "pt.vat.rates")
    assert resolved.verification == 2
    assert resolved.value.review_by == expected
    recorded = json.loads(state.state_path().read_text(encoding="utf-8"))["packs"]["market/pt"]
    assert recorded["cards"]["pt.vat.rates"]["review_by"] == expected
    assert recorded["pack"]["review_by"] == expected


def test_the_pack_can_set_its_review_interval(db, shipped):
    manifest = shipped / "market" / "pt" / "pack.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("  level: 1\n", "  level: 1\n  review_interval_months: 3\n"),
        encoding="utf-8",
    )
    approval_id = request_verification(
        "ops", kind="market", pack_id="pt", level=2, reviewer="R", cards=["pt.vat.rates"]
    )
    output = _approve(approval_id)["execution"]["output"]

    expected = state.add_months(datetime.now(UTC).date(), 3).isoformat()
    assert load_pack(shipped / "market" / "pt").rules["pt.vat.rates"].review_by == expected
    assert f"Next review by {expected}" in output


@pytest.mark.parametrize(
    ("day", "months", "expected"),
    [
        (date(2026, 10, 13), 6, date(2027, 4, 13)),
        (date(2026, 8, 31), 6, date(2027, 2, 28)),
        (date(2027, 8, 31), 6, date(2028, 2, 29)),
        (date(2026, 12, 1), 1, date(2027, 1, 1)),
    ],
)
def test_add_months(day, months, expected):
    assert state.add_months(day, months) == expected


def test_register_headline_is_the_lowest_card_level(db, shipped):
    """The tender register's headline must not claim the pack's level when a card it uses is lower."""
    from realize_core.wedge.register import get_method, render_register

    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="R")
    assert _approve(approval_id)["execution"]["success"] is True
    market = get_method("pt")["market"]
    assert market["verification"] == 2 == min(r["verification"] for r in market["rules"])

    path = state.state_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["packs"]["market/pt"]["cards"]["pt.vat.rates"]["review_by"] = "2026-02-01"
    path.write_text(json.dumps(data), encoding="utf-8")
    clear_cache()

    market = get_method("pt")["market"]
    levels = {r["id"]: r["verification"] for r in market["rules"]}
    assert levels["pt.vat.rates"] == 1
    assert market["verification"] == 1 == min(levels.values())
    assert "verification 1 (drafted)" in market["notice"]
    checked = {"items": [], "counts": {"items": 0, "mandatory": 0, "without_locator": 0}}
    assert "verification 1 (drafted)" in render_register(checked, market="pt")


def test_the_approval_date_is_today(db, shipped):
    """Sanity check on the dates the approval records (the review date is today, the next one later)."""
    approval_id = request_verification(
        "ops", kind="market", pack_id="pt", level=2, reviewer="R", cards=["pt.vat.rates"]
    )
    assert _approve(approval_id)["execution"]["success"] is True
    card = load_pack(shipped / "market" / "pt").rules["pt.vat.rates"]
    today = datetime.now(UTC).date()
    assert card.reviewed_at == today.isoformat()
    assert date.fromisoformat(card.review_by) - today > timedelta(days=150)


# ---------------------------------------------------------------------------
# P2-2: approvals follow the card's content
# ---------------------------------------------------------------------------


def test_a_card_edited_in_place_after_approval_drops_to_its_file_level(db, shipped, caplog):
    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="Ana Silva")
    assert _approve(approval_id)["execution"]["success"] is True
    root = shipped / "market" / "pt"
    assert load_pack(root).rules["pt.vat.rates"].verification == 2

    card = root / "rules" / "vat-rates.md"
    text = card.read_text(encoding="utf-8")
    statement = next(line for line in text.splitlines() if line.startswith("statement:"))
    card.write_text(text.replace(statement, "statement: Works carry no VAT at all."), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="realize_core.packs.loader"):
        first = load_pack(root)
        second = load_pack(root)
    edited = first.rules["pt.vat.rates"]
    assert edited.verification == 1
    assert edited.verified_by is None
    assert edited.effective_level(first.verification_level) == 1
    assert first.rules["pt.contracts.price-revision"].effective_level(first.verification_level) == 2
    assert second.rules["pt.vat.rates"].verification == 1
    named = [r for r in caplog.records if "pt.vat.rates changed since it was approved" in r.getMessage()]
    assert len(named) == 1  # warned once, naming the card


def test_an_edited_copy_in_the_custom_folder_with_the_same_version_drops(db, shipped, tmp_path, monkeypatch):
    approval_id = request_verification("ops", kind="market", pack_id="pt", level=2, reviewer="Ana Silva")
    assert _approve(approval_id)["execution"]["success"] is True
    custom = tmp_path / "custom"
    shutil.copytree(shipped / "market" / "pt", custom / "market" / "pt")
    card = custom / "market" / "pt" / "rules" / "vat-rates.md"
    text = card.read_text(encoding="utf-8")
    source = next(line for line in text.splitlines() if line.startswith("source:"))
    card.write_text(text.replace(source, "source: https://firm.example/our-own-reading"), encoding="utf-8")
    monkeypatch.setenv(loader.PACKS_PATH_ENV, str(custom))
    clear_cache()

    resolver = PackResolver(_venture(tmp_path), enabled=True)

    assert resolver.packs[0].root.resolve().is_relative_to(custom.resolve())  # the edited copy is the one used
    assert resolver.resolve("rule", "pt.vat.rates").verification == 1
    assert resolver.resolve("rule", "pt.contracts.price-revision").verification == 2


def test_line_endings_and_wrapping_do_not_break_an_approval(db, shipped):
    approval_id = request_verification(
        "ops", kind="market", pack_id="pt", level=2, reviewer="R", cards=["pt.vat.rates"]
    )
    assert _approve(approval_id)["execution"]["success"] is True
    card = shipped / "market" / "pt" / "rules" / "vat-rates.md"
    card.write_bytes(card.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))

    assert load_pack(shipped / "market" / "pt").rules["pt.vat.rates"].verification == 2


def test_an_approval_recorded_before_fingerprints_still_applies(db, shipped):
    """Records written by 5.28-5.29 have no fingerprint; they keep applying until the card is reviewed again."""
    approval_id = request_verification(
        "ops", kind="market", pack_id="pt", level=2, reviewer="R", cards=["pt.vat.rates"]
    )
    assert _approve(approval_id)["execution"]["success"] is True
    path = state.state_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["packs"]["market/pt"]["cards"]["pt.vat.rates"]["content"]
    path.write_text(json.dumps(data), encoding="utf-8")
    clear_cache()

    assert load_pack(shipped / "market" / "pt").rules["pt.vat.rates"].verification == 2
