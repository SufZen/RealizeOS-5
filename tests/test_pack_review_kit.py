"""Reviewer kit for market packs: sheets, submission, corrections and desk checks (STORY-45)."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml
from realize_core.cli_app import app
from realize_core.governance.gates import Decider
from realize_core.packs import load_pack
from realize_core.packs.review import (
    PASS_THRESHOLD,
    ReviewEntry,
    ReviewSheetError,
    build_sheet_rows,
    desk_check,
    estimate_facts,
    load_market_pack,
    parse_review,
    read_sheet,
    render_csv,
    render_markdown,
    reviewer_slug,
    write_review_sheet,
)
from realize_core.packs.review import (
    Review as PackReview,
)
from typer.testing import CliRunner

PACKS = Path(__file__).parent.parent / "packs"
REVIEWER = "Ana Silva, advogada (OA 12345)"
OWNER = Decider(user_id="owner", role="owner", allowed_ventures=None)
runner = CliRunner()


@pytest.fixture
def packs_root(tmp_path, monkeypatch) -> Path:
    """A copy of the market packs, used as the default packs root."""
    from realize_core.packs import loader

    root = tmp_path / "packs"
    for code in ("pt", "gr", "il", "uk"):
        shutil.copytree(PACKS / "market" / code, root / "market" / code, ignore=shutil.ignore_patterns("reviews"))
    monkeypatch.setattr(loader, "default_packs_root", lambda: root)
    return root


def _read_table(path: Path) -> tuple[list[str], list[list[str]], str]:
    text = path.read_bytes().decode("utf-8-sig")
    delimiter = ";" if text.split("\n", 1)[0].count(";") > text.split("\n", 1)[0].count(",") else ","
    table = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    return table[0], table[1:], delimiter


def _fill(path: Path, answers: dict[str, dict[str, str]], out: Path | None = None) -> Path:
    """Fill reviewer columns the way a reviewer would, saving as UTF-8 CSV."""
    header, rows, delimiter = _read_table(path)
    default = answers.get("*", {})
    for row in rows:
        values = {**default, **answers.get(row[0], {})} if row[1] == "rule" else answers.get(row[0], {})
        for column, value in values.items():
            row[header.index(column)] = value
    buf = io.StringIO()
    csv.writer(buf, delimiter=delimiter, lineterminator="\r\n").writerows([header, *rows])
    target = out or path.with_name("filled.csv")
    target.write_text(buf.getvalue(), encoding="utf-8-sig", newline="")
    return target


def _sheet(tmp_path: Path, code: str = "pt") -> Path:
    return write_review_sheet(code, "csv", out=tmp_path / f"{code}-sheet.csv")


def _approval(approval_id: str) -> dict:
    from realize_core.db.schema import get_connection

    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM approval_queue WHERE id = ?", (approval_id,)).fetchone()
    finally:
        conn.close()
    return dict(row)


ALL_CORRECT = {"*": {"verdict": "correct"}}
MIXED = {
    "*": {"verdict": "correct"},
    "pt.vat.rates": {
        "verdict": "corrected",
        "facts_corrected": "1",
        "corrected_statement": "Mainland Portugal's standard VAT (IVA) rate is 23%; a reduced 6% rate applies only "
        "to listed works.",
        "reviewer_note": "Ruling reference to be checked.",
    },
    "pt.taxes.imt-current-table": {"verdict": "removed", "reviewer_note": "Duplicates the stamp-duty card."},
}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "delimiter", "sample"),
    [("pt", ";", "auto de medição"), ("gr", ";", "λογαριασμός"), ("il", ",", "חשבון חלקי")],
)
def test_csv_round_trip_keeps_non_latin_text(packs_root, tmp_path, code, delimiter, sample):
    path = _sheet(tmp_path, code)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM: Excel reads it as UTF-8
    header, _, used = _read_table(path)
    assert used == delimiter
    assert header[-4:] == ["verdict", "facts_corrected", "corrected_statement", "reviewer_note"]
    pack = load_market_pack(code)
    expected = {r.id: r for r in build_sheet_rows(pack)}
    parsed = read_sheet(path)
    assert [r["id"] for r in parsed] == list(expected)
    for row in parsed:
        assert row["statement"] == expected[row["id"]].statement  # multi-line cells survive
    assert any(sample in row["statement"] for row in parsed)


def test_csv_cells_are_quoted_and_cannot_start_a_formula():
    from realize_core.packs.review import SheetRow

    text = render_csv([SheetRow(id="x.1", type="rule", statement="=HYPERLINK(1)", details="line 1\nline 2  ")])
    header, rows, _ = _read_table_from_text(text)
    assert rows[0][2] == "'=HYPERLINK(1)"
    assert rows[0][3] == "line 1\nline 2"
    assert text.splitlines()[0].startswith('"id"')


@pytest.mark.parametrize(
    ("statement", "cell"),
    [
        ("=IMPORTXML(A1)", "'=IMPORTXML(A1)"),
        ("+SUM(1)", "'+SUM(1)"),
        ("-2+3", "'-2+3"),
        ("@cmd", "'@cmd"),
        ("\uff1dIMPORTXML(A1)", "'\uff1dIMPORTXML(A1)"),  # full-width equals sign
        ("\uff0b1", "'\uff0b1"),
        ("\u3000=HYPERLINK(1)", "'=HYPERLINK(1)"),  # leading spaces (ideographic, no-break) don't hide it
        ("\u00a0 =HYPERLINK(1)", "'=HYPERLINK(1)"),
        ("-1200", "-1200"),  # a plain number stays a number
        ("VAT is 23%", "VAT is 23%"),
    ],
)
def test_csv_cells_never_start_a_formula_spreadsheets_would_run(statement, cell):
    """The guard is the spreadsheet convention (a leading apostrophe), not a space some spreadsheets skip."""
    from realize_core.packs.review import SheetRow

    for field_name in ("statement", "details", "source", "applies_to"):
        row = SheetRow(id="x.1", type="rule", **{"statement": "ok", field_name: statement})
        _, rows, _ = _read_table_from_text(render_csv([row]))
        column = {"statement": 2, "details": 3, "source": 4, "applies_to": 7}[field_name]
        assert rows[0][column] == cell, field_name


def test_a_guarded_statement_round_trips_without_a_changed_card_warning(packs_root, tmp_path, monkeypatch):
    """The apostrophe the export adds (or a spreadsheet's removal of it) isn't a change to the card."""
    from realize_core.packs import review
    from realize_core.packs.review import SheetRow

    rows = [SheetRow(id="x.1", type="rule", statement="=1 rule, two facts", facts_checked=2)]
    monkeypatch.setattr(review, "build_sheet_rows", lambda pack: rows)
    pack = load_market_pack("pt")
    for exported in ("'=1 rule, two facts", "=1 rule, two facts"):
        parsed = parse_review(pack, [{"id": "x.1", "statement": exported, "verdict": "correct"}])
        assert parsed.warnings == []
    changed = parse_review(pack, [{"id": "x.1", "statement": "'=2 rules", "verdict": "correct"}])
    assert any("changed after this sheet was exported" in w for w in changed.warnings)


ESC = "\x1b"


def test_sheet_values_in_error_messages_cannot_drive_the_terminal(packs_root, tmp_path):
    """Values from the reviewer's CSV are shown escaped, never as raw control characters."""
    pack = load_market_pack("pt")
    first = build_sheet_rows(pack)[0].id
    raw_rows = [
        {"id": f"pt.nope{ESC}]0;owned{chr(7)}", "verdict": "correct"},
        {"id": first, "verdict": f"fine{ESC}[2J", "facts_checked": ""},
    ]
    with pytest.raises(ReviewSheetError) as caught:
        parse_review(pack, raw_rows)
    errors = "\n".join(caught.value.errors)
    assert ESC not in errors
    assert chr(7) not in errors
    assert "pt.nope\\x1b]0;owned\\x07" in errors
    assert "fine\\x1b[2J" in errors

    for column in ("facts_checked", "facts_corrected"):
        with pytest.raises(ReviewSheetError) as caught:
            parse_review(pack, [{"id": first, "verdict": "correct", column: f"1{ESC}[31m"}])
        assert ESC not in "\n".join(caught.value.errors)
        assert "1\\x1b[31m" in "\n".join(caught.value.errors)
        # Not a number a person writes, and no crash either.
        with pytest.raises(ReviewSheetError, match="'inf' must be a whole number"):
            parse_review(pack, [{"id": first, "verdict": "correct", column: "inf"}])


def test_cli_shows_sheet_values_escaped(packs_root, tmp_path):
    """review-submit's problem list and correction diff carry no raw escape sequences."""
    bad = _fill(_sheet(tmp_path), {"*": {"verdict": f"yes{ESC}[2J"}})
    result = _submit(bad)
    assert result.exit_code == 1
    assert ESC not in result.output
    assert "yes\\x1b[2J" in result.output

    # The card's YAML escapes ESC itself; a right-to-left override passes through YAML as text.
    rlo = "\u202e"
    answers = {
        **MIXED,
        "pt.vat.rates": {**MIXED["pt.vat.rates"], "corrected_statement": f"VAT is 23%.{rlo} Really.{ESC}[2J"},
    }
    result = _submit(_fill(_sheet(tmp_path), answers), "--apply-corrections", "--yes")
    assert result.exit_code == 0, result.output
    assert ESC not in result.output
    assert rlo not in result.output
    assert "VAT is 23%.\\u202e Really." in result.output


def _read_table_from_text(text: str):
    table = list(csv.reader(io.StringIO(text, newline="")))
    return table[0], table[1:], ","


def test_markdown_sheet_has_instructions_in_the_pack_language(packs_root):
    pt = render_markdown(load_market_pack("pt"), build_sheet_rows(load_market_pack("pt")))
    assert "## How to review (about" in pt
    assert "## Como rever" in pt
    assert "*Tradução feita por um agente de IA" in pt
    assert "### 1. pt." in pt
    il = render_markdown(load_market_pack("il"), build_sheet_rows(load_market_pack("il")))
    assert '<div dir="rtl" lang="he">' in il
    assert "תורגם על ידי סוכן" in il
    uk = render_markdown(load_market_pack("uk"), build_sheet_rows(load_market_pack("uk")))
    assert "Como rever" not in uk
    assert "agente" not in uk


def test_default_sheet_location_is_the_reviews_folder(packs_root):
    path = write_review_sheet("pt", "md")
    assert path == packs_root / "market" / "pt" / "reviews" / "review-sheet.md"


@pytest.mark.parametrize(
    ("statement", "facts"),
    [
        ("", 0),
        ("One fact.", 1),
        ("A is 23%. A 6% rate applies; it is narrow.", 3),
        ("Under the U.S. Code a bond is needed.", 1),
        ("See Art. 5 for details.", 1),
        ("Rate is 18% from 1 January 2025 (previously 17%). The rate follows the date.", 2),
    ],
)
def test_fact_estimate_counts_clauses(statement, facts):
    assert estimate_facts(statement) == facts


def test_reviewer_slug_handles_non_latin_names():
    assert reviewer_slug(REVIEWER) == "ana-silva"
    assert reviewer_slug("Γιώργος Παπαδόπουλος, δικηγόρος") == "γιώργος-παπαδόπουλος"
    assert reviewer_slug("  ") == "reviewer"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_submit_validation_lists_every_problem(packs_root, tmp_path):
    sheet = _fill(
        _sheet(tmp_path),
        {
            "*": {"verdict": "correct"},
            "pt.vat.rates": {"verdict": ""},
            "pt.contractors.alvara": {"verdict": "correct", "facts_corrected": "abc"},
            "pt.taxes.stamp-duty-on-purchase": {"verdict": "correct", "facts_corrected": "2"},
            "pt.sales.permit-statement": {"verdict": "corrected", "facts_corrected": "1"},
            "pt.planning.simplex-2": {"verdict": "fine"},
            "pt.contracts.price-revision": {"verdict": "corrected", "facts_corrected": "0", "reviewer_note": "x"},
            "pt.sales.energy-certificate": {"verdict": "correct", "facts_corrected": "-1"},
        },
    )
    text = sheet.read_text(encoding="utf-8-sig")
    text += '"pt.nope";"rule";"";"";"";"";"";"";"";"1";"correct";"";"";""\r\n'
    text += '"pt.vat.rates";"rule";"";"";"";"";"";"";"";"1";"correct";"";"";""\r\n'
    sheet.write_text(text, encoding="utf-8-sig", newline="")
    pack = load_market_pack("pt")
    with pytest.raises(ReviewSheetError) as caught:
        parse_review(pack, read_sheet(sheet))
    errors = "\n".join(caught.value.errors)
    assert "(pt.vat.rates): no verdict" in errors
    assert "facts corrected 'abc' must be a whole number" in errors
    assert "facts corrected '-1' must be a whole number" in errors
    assert "verdict correct but 2 facts corrected" in errors
    assert "(pt.sales.permit-statement): verdict corrected needs a corrected statement or a reviewer note" in errors
    assert "verdict 'fine' must be correct, corrected or removed" in errors
    assert "(pt.contracts.price-revision): verdict corrected needs 1 or more facts corrected" in errors
    assert "unknown card id 'pt.nope'" in errors
    assert "'pt.vat.rates' appears twice" in errors


def test_a_card_missing_from_the_sheet_is_an_error(packs_root, tmp_path):
    header, rows, delimiter = _read_table(_sheet(tmp_path))
    rows = [r for r in rows if r[0] != "pt.vat.rates"]
    for r in rows:
        r[header.index("verdict")] = "correct" if r[1] == "rule" else ""
    path = tmp_path / "short.csv"
    buf = io.StringIO()
    csv.writer(buf, delimiter=delimiter).writerows([header, *rows])
    path.write_text(buf.getvalue(), encoding="utf-8-sig")
    with pytest.raises(ReviewSheetError, match="card 'pt.vat.rates' is missing"):
        parse_review(load_market_pack("pt"), read_sheet(path))


def test_sheets_not_saved_as_utf8_or_not_csv_are_refused(packs_root, tmp_path):
    bad = tmp_path / "ansi.csv"
    bad.write_bytes("id,verdict,facts_corrected\npt.contractors.alvara,correct,0\nalvar\xe1\n".encode("cp1252"))
    with pytest.raises(ReviewSheetError, match="CSV UTF-8"):
        read_sheet(bad)
    with pytest.raises(ReviewSheetError, match="submit the CSV sheet"):
        read_sheet(write_review_sheet("pt", "md", out=tmp_path / "sheet.md"))
    no_columns = tmp_path / "plain.csv"
    no_columns.write_text("id,statement\npt.vat.rates,x\n", encoding="utf-8")
    with pytest.raises(ReviewSheetError, match="no verdict, facts_corrected column"):
        read_sheet(no_columns)


def test_a_sheet_saved_by_google_sheets_with_commas_is_read(packs_root, tmp_path):
    header, rows, _ = _read_table(_sheet(tmp_path))
    for r in rows:
        r[header.index("verdict")] = "Correct " if r[1] == "rule" else ""
    path = tmp_path / "google.csv"
    buf = io.StringIO()
    csv.writer(buf).writerows([header, *rows])
    path.write_text(buf.getvalue(), encoding="utf-8")  # no BOM, comma separated
    review = parse_review(load_market_pack("pt"), read_sheet(path))
    assert review.totals("rule")["correct"] == 10


# ---------------------------------------------------------------------------
# Ratio and pass signal
# ---------------------------------------------------------------------------


def _review(*entries: tuple[str, str, int, int]) -> PackReview:
    return PackReview(
        pack_ref="pt@0.1.0",
        entries=[ReviewEntry(i, "rule", v, checked, corrected, "s") for i, v, checked, corrected in entries],
    )


def test_ratio_and_pass_are_counted_over_drafted_facts():
    passing = _review(("a", "correct", 5, 0), ("b", "corrected", 5, 1), ("c", "removed", 1, 1), ("d", "correct", 4, 0))
    assert passing.totals("rule")["ratio"] == round(2 / 15, 3)
    assert passing.passed
    on_the_line = _review(("a", "corrected", 5, 1))  # exactly 1 in 5 is not fewer than 1 in 5
    assert on_the_line.correction_ratio == PASS_THRESHOLD
    assert not on_the_line.passed


def test_parsed_review_counts_removed_cards_as_corrected(packs_root, tmp_path):
    sheet = _fill(_sheet(tmp_path), MIXED)
    review = parse_review(load_market_pack("pt"), read_sheet(sheet))
    totals = review.totals("rule")
    checked = sum(r.facts_checked for r in build_sheet_rows(load_market_pack("pt")) if r.type == "rule")
    removed = estimate_facts(load_market_pack("pt").rules["pt.taxes.imt-current-table"].statement)
    assert (totals["correct"], totals["corrected"], totals["removed"]) == (8, 1, 1)
    assert totals["facts_checked"] == checked
    assert totals["facts_corrected"] == 1 + removed
    assert review.passed == ((1 + removed) / checked < PASS_THRESHOLD)
    assert review.totals("glossary")["reviewed"] == 0  # optional rows left blank


def test_more_facts_corrected_than_checked_raises_the_count_with_a_warning(packs_root, tmp_path):
    sheet = _fill(
        _sheet(tmp_path),
        {
            "*": {"verdict": "correct"},
            "pt.sales.permit-statement": {"verdict": "corrected", "facts_corrected": "3", "reviewer_note": "n"},
        },
    )
    review = parse_review(load_market_pack("pt"), read_sheet(sheet))
    entry = next(e for e in review.entries if e.id == "pt.sales.permit-statement")
    assert (entry.facts_checked, entry.facts_corrected) == (3, 3)
    assert any("counting 3 checked" in w for w in review.warnings)


# ---------------------------------------------------------------------------
# Submission (CLI) and the approval queue
# ---------------------------------------------------------------------------


def _submit(sheet: Path, *extra: str, input: str | None = None):
    args = ["packs", "review-submit", "pt", "--sheet", str(sheet), "--reviewer", REVIEWER, "--venture", "ops", *extra]
    return runner.invoke(app, args, input=input)


def test_submit_records_the_review_and_queues_pack_verify(packs_root, tmp_path):
    from realize_core.governance.gates import decide_approval

    before = {p.name: p.read_bytes() for p in (packs_root / "market" / "pt" / "rules").glob("*.md")}
    result = _submit(_fill(_sheet(tmp_path), MIXED))
    assert result.exit_code == 0, result.output
    assert "Approval queued:" in result.output
    assert "Corrections not yet in the cards: pt.taxes.imt-current-table, pt.vat.rates" in result.output

    records = list((packs_root / "market" / "pt" / "reviews").glob("*-ana-silva.yaml"))
    assert len(records) == 1
    record = yaml.safe_load(records[0].read_text(encoding="utf-8"))
    assert record["reviewer"] == REVIEWER
    assert record["totals"]["rule"]["removed"] == 1
    assert record["signal"]["result"] in ("pass", "fail")
    approval_id = record["approval"]["id"]

    row = _approval(approval_id)
    assert row["action_type"] == "pack_verify"
    assert row["status"] == "pending"
    params = json.loads(row["params_json"])
    assert params["level"] == 2
    assert params["reviewer"] == REVIEWER
    assert "pt.taxes.imt-current-table" not in params["cards"]
    assert len(params["cards"]) == 9
    removed = estimate_facts(load_market_pack("pt").rules["pt.taxes.imt-current-table"].statement)
    assert params["corrections"] == {"pt.vat.rates": 1, "pt.taxes.imt-current-table": removed}
    # Without --apply-corrections the card text is untouched.
    assert {p.name: p.read_bytes() for p in (packs_root / "market" / "pt" / "rules").glob("*.md")} == before

    asyncio.run(decide_approval(approval_id, True, decider=OWNER))
    pack = load_pack(packs_root / "market" / "pt")
    assert pack.verification_level == 1  # card-level request: the pack's own level stays
    assert pack.rules["pt.contractors.alvara"].verification == 2
    assert pack.rules["pt.contractors.alvara"].verified_by == REVIEWER
    assert pack.rules["pt.taxes.imt-current-table"].verification == 1


def test_apply_corrections_edits_only_the_listed_cards(packs_root, tmp_path):
    rules = packs_root / "market" / "pt" / "rules"
    before = {p.name: p.read_bytes() for p in rules.glob("*.md")}
    result = _submit(_fill(_sheet(tmp_path), MIXED), "--apply-corrections", "--yes")
    assert result.exit_code == 0, result.output
    assert "-statement: Mainland Portugal's standard VAT" in result.output
    assert "remove pt.taxes.imt-current-table: rules/imt-tables.md -> reviews/removed/imt-tables.md" in result.output

    after = {p.name: p.read_bytes() for p in rules.glob("*.md")}
    assert set(before) - set(after) == {"imt-tables.md"}
    changed = {name for name in after if after[name] != before[name]}
    assert changed == {"vat-rates.md"}
    assert (packs_root / "market" / "pt" / "reviews" / "removed" / "imt-tables.md").read_bytes() == before[
        "imt-tables.md"
    ]

    pack = load_pack(packs_root / "market" / "pt")
    assert pack.warnings == []
    assert len(pack.rules) == 9
    assert "pt.taxes.imt-current-table" not in pack.rules
    assert pack.rules["pt.vat.rates"].statement.endswith("applies only to listed works.")
    assert pack.rules["pt.vat.rates"].source.startswith("https://")
    changelog = (packs_root / "market" / "pt" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "review by Ana Silva" in changelog
    assert "removed `pt.taxes.imt-current-table`" in changelog
    record = yaml.safe_load(next((packs_root / "market" / "pt" / "reviews").glob("*.yaml")).read_text(encoding="utf-8"))
    assert record["corrections_pending"] == []
    assert len(record["corrections_applied"]) == 2


def test_declining_the_diff_changes_nothing(packs_root, tmp_path):
    pt = packs_root / "market" / "pt"
    before = {p.relative_to(pt): p.read_bytes() for p in pt.rglob("*") if p.is_file()}
    result = _submit(_fill(_sheet(tmp_path), MIXED), "--apply-corrections", input="n\n")
    assert result.exit_code == 1
    assert "nothing was written" in result.output
    assert {p.relative_to(pt): p.read_bytes() for p in pt.rglob("*") if p.is_file()} == before


def test_whole_pack_needs_every_row_and_the_corrections_applied(packs_root, tmp_path):
    from realize_core.governance.gates import decide_approval

    blocked = _submit(_fill(_sheet(tmp_path), MIXED), "--whole-pack")
    assert blocked.exit_code == 1
    assert "glossary:pt was not reviewed" in blocked.output
    assert "pt.vat.rates needs its correction or removal applied" in blocked.output

    everything = {
        **MIXED,
        "defaults": {"verdict": "correct"},
        "glossary:pt": {"verdict": "correct"},
        "glossary:en": {"verdict": "correct"},
    }
    result = _submit(_fill(_sheet(tmp_path), everything), "--whole-pack", "--apply-corrections", "--yes")
    assert result.exit_code == 0, result.output
    record = yaml.safe_load(next((packs_root / "market" / "pt" / "reviews").glob("*.yaml")).read_text(encoding="utf-8"))
    params = json.loads(_approval(record["approval"]["id"])["params_json"])
    assert params["cards"] == []  # the whole pack, so pack.yaml is raised too
    manifest_before = (packs_root / "market" / "pt" / "pack.yaml").read_bytes()
    out = asyncio.run(decide_approval(record["approval"]["id"], True, decider=OWNER))
    assert out["execution"]["success"] is True, out["execution"]
    pack = load_pack(packs_root / "market" / "pt")
    assert pack.verification_level == 2
    assert {c.verification for c in pack.rules.values()} == {2}
    # The level lives in the verification state; the reviewer kit's own edits are the only pack changes.
    assert (packs_root / "market" / "pt" / "pack.yaml").read_bytes() == manifest_before


def test_hand_edits_block_the_whole_pack_and_reach_the_approval_note(packs_root, tmp_path):
    reviewed = {"*": {"verdict": "correct"}, "defaults": {"verdict": "correct"}, "glossary:en": {"verdict": "correct"}}
    note_only = {
        **reviewed,
        "glossary:pt": {"verdict": "correct"},
        "pt.sales.permit-statement": {
            "verdict": "corrected",
            "facts_corrected": "1",
            "reviewer_note": "Use 'licence'.",
        },
    }
    blocked = _submit(_fill(_sheet(tmp_path), note_only), "--whole-pack", "--apply-corrections", "--yes")
    assert blocked.exit_code == 1
    assert "pt.sales.permit-statement is marked corrected without a corrected statement" in blocked.output

    glossary_fix = {**reviewed, "glossary:pt": {"verdict": "corrected", "facts_corrected": "1", "reviewer_note": "x"}}
    result = _submit(_fill(_sheet(tmp_path), glossary_fix))
    assert result.exit_code == 0, result.output
    assert "Edit by hand (no corrected statement to apply): glossary:pt" in result.output
    record = yaml.safe_load(next((packs_root / "market" / "pt" / "reviews").glob("*.yaml")).read_text(encoding="utf-8"))
    assert (
        "Edit by hand before approving: glossary:pt."
        in json.loads(_approval(record["approval"]["id"])["params_json"])["note"]
    )


def test_resubmitting_points_at_the_earlier_approval(packs_root, tmp_path):
    first = _submit(_fill(_sheet(tmp_path), ALL_CORRECT))
    assert first.exit_code == 0, first.output
    second = _submit(_fill(_sheet(tmp_path), ALL_CORRECT))
    assert "An earlier submission of this review queued approval" in second.output


def test_no_approval_when_every_card_is_removed(packs_root, tmp_path):
    result = _submit(_fill(_sheet(tmp_path), {"*": {"verdict": "removed"}}))
    assert result.exit_code == 0, result.output
    assert "No approval queued" in result.output


def test_bad_sheet_exits_with_the_problems(packs_root, tmp_path):
    result = _submit(_sheet(tmp_path))
    assert result.exit_code == 1
    assert "problem(s); nothing was recorded" in result.output
    assert not (packs_root / "market" / "pt" / "reviews").exists()


def test_review_sheet_command_writes_both_formats(packs_root, tmp_path):
    csv_result = runner.invoke(app, ["packs", "review-sheet", "gr", "--out", str(tmp_path / "gr.csv")])
    assert csv_result.exit_code == 0, csv_result.output
    md_result = runner.invoke(app, ["packs", "review-sheet", "gr", "--format", "md", "--out", str(tmp_path / "gr.md")])
    assert md_result.exit_code == 0, md_result.output
    assert "Πώς γίνεται" in (tmp_path / "gr.md").read_text(encoding="utf-8")
    comma = runner.invoke(
        app, ["packs", "review-sheet", "gr", "--delimiter", "comma", "--out", str(tmp_path / "c.csv")]
    )
    assert comma.exit_code == 0
    assert _read_table(tmp_path / "c.csv")[2] == ","
    missing = runner.invoke(app, ["packs", "review-sheet", "zz"])
    assert missing.exit_code == 1


# ---------------------------------------------------------------------------
# Desk check
# ---------------------------------------------------------------------------

BAD_CARDS = {
    "http.md": "---\nid: pt.bad.http\nstatement: A fact.\nsource: http://example.pt/x\nas_of: '2026-10-01'\nreview_by: '2027-04-01'\napplies_to: {family: change}\n---\nBody.\n",
    "nosource.md": "---\nid: pt.bad.nosource\nstatement: A fact.\nas_of: '2026-10-01'\nreview_by: '2027-04-01'\napplies_to: {family: change}\n---\nBody.\n",
    "expired.md": "---\nid: pt.bad.expired\nstatement: A fact.\nsource: https://example.pt/x\nas_of: '2025-01-01'\nreview_by: '2025-06-01'\napplies_to: {family: change}\n---\nBody.\n",
    "future.md": "---\nid: pt.bad.future\nstatement: ''\nsource: https://example.pt/x\nas_of: '2027-01-01'\nreview_by: '2027-04-01'\napplies_to: {family: payment}\n---\n",
    "dupe.md": "---\nid: pt.vat.rates\nstatement: Copy.\nsource: https://example.pt/x\nas_of: '2026-10-01'\nreview_by: '2027-04-01'\napplies_to: {family: change, kinds: variation}\n---\nSecondary source.\n",
}


def test_desk_check_flags_crafted_bad_cards(packs_root):
    rules = packs_root / "market" / "pt" / "rules"
    for name, text in BAD_CARDS.items():
        (rules / name).write_text(text, encoding="utf-8")
    findings = desk_check("pt", today=date(2026, 10, 13))
    by_target = {}
    for f in findings:
        by_target.setdefault(f.target, []).append((f.level, f.message))

    def has(target: str, level: str, text: str) -> bool:
        return any(lvl == level and text in msg for lvl, msg in by_target.get(target, []))

    assert has("pt.bad.http", "error", "not an https URL")
    assert has("pt.bad.nosource", "error", "source missing")
    assert has("pt.bad.expired", "error", "has passed")
    assert has("pt.bad.future", "error", "statement is empty")
    assert has("pt.bad.future", "error", "is in the future")
    assert has("pt.bad.future", "error", "not a core family")
    assert has("pt.bad.future", "warning", "no explanation")
    assert has("pt.vat.rates", "error", "id also used by")
    assert has("pt.vat.rates", "error", "kinds must be a list")
    assert has("pt.vat.rates", "info", "secondary")


def test_desk_check_cli_exits_nonzero_on_errors(packs_root):
    clean = runner.invoke(app, ["packs", "desk-check", "pt", "--on", "2026-10-13"])
    assert clean.exit_code == 0, clean.output
    assert "not a professional review" in clean.output
    assert "0 error(s)" in clean.output
    (packs_root / "market" / "pt" / "rules" / "http.md").write_text(BAD_CARDS["http.md"], encoding="utf-8")
    dirty = runner.invoke(app, ["packs", "desk-check", "pt", "--on", "2026-10-13"])
    assert dirty.exit_code == 1
    assert "ERROR   pt.bad.http" in dirty.output


@pytest.mark.parametrize("code", ["cy", "es", "gr", "il", "pt", "uk", "us"])
def test_shipped_market_packs_pass_the_desk_check(code):
    findings = desk_check(code, packs_root=PACKS, today=date(2026, 10, 13))
    assert [f for f in findings if f.level == "error"] == []


# ---------------------------------------------------------------------------
# The loader ignores reviews/, and the shipped sheets are current
# ---------------------------------------------------------------------------


def test_loader_ignores_the_reviews_folder(packs_root, tmp_path):
    pt = packs_root / "market" / "pt"
    before = load_pack(pt)
    write_review_sheet("pt", "csv")
    write_review_sheet("pt", "md")
    reviews = pt / "reviews"
    (reviews / "2026-10-20-ana-silva.yaml").write_text("reviewer: x\nrows: []\n", encoding="utf-8")
    (reviews / "removed").mkdir()
    shutil.copy(pt / "rules" / "vat-rates.md", reviews / "removed" / "old-card.md")
    (reviews / "glossary").mkdir()
    (reviews / "glossary" / "xx.yaml").write_text("- term: nope\n  family: change\n", encoding="utf-8")
    after = load_pack(pt)
    assert after.warnings == []
    assert after.rules.keys() == before.rules.keys()
    assert after.terms.keys() == before.terms.keys()
    assert after.documents == before.documents


def _level_one_market_packs() -> list[str]:
    from realize_core.packs.review import market_pack_ids

    return [c for c in market_pack_ids(PACKS) if load_market_pack(c, PACKS).verification_level == 1]


@pytest.mark.parametrize("code", _level_one_market_packs())
def test_shipped_review_sheets_match_the_pack(code):
    """The sheets in packs/market/<id>/reviews/ are ready to send: regenerate them when a card changes."""
    pack = load_market_pack(code, PACKS)
    rows = build_sheet_rows(pack)
    from realize_core.packs.review import default_delimiter

    reviews = PACKS / "market" / code / "reviews"
    shipped_csv = (reviews / "review-sheet.csv").read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    assert shipped_csv == render_csv(rows, default_delimiter(pack)), f"run: python cli.py packs review-sheet {code}"
    shipped_md = (reviews / "review-sheet.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert shipped_md == render_markdown(pack, rows), f"run: python cli.py packs review-sheet {code} --format md"


@pytest.mark.parametrize(
    "cmd",
    [
        ["packs", "--help"],
        ["packs", "review-sheet", "--help"],
        ["packs", "review-submit", "--help"],
        ["packs", "desk-check", "--help"],
    ],
)
def test_packs_help(cmd):
    result = runner.invoke(app, cmd)
    assert result.exit_code == 0, result.output
