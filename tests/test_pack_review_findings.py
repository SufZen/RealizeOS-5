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
import shutil
from datetime import date
from pathlib import Path

import pytest
from realize_core.governance.gates import Decider, decide_approval
from realize_core.packs import PackResolver, clear_cache, load_pack, loader
from realize_core.packs.loader import load_firm_layer

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
