"""Reviewer kit for market packs (STORY-45): review sheets, review records, desk checks.

This is tooling around a pack, not part of running one. The loader and the
resolver never read what this module writes: review sheets and review records
live in ``packs/market/<id>/reviews/``, a folder the loader ignores.

- :func:`write_review_sheet` exports a sheet a local professional fills in:
  one row per rule card, one per glossary file and one for the defaults.
- :func:`submit_review` reads the filled sheet, validates it, writes a review
  record into the pack and queues a ``pack_verify`` approval through
  :func:`realize_core.packs.verify.request_verification`. Nothing is raised
  directly: a person still approves the level change.
- :func:`desk_check` runs mechanical checks on every card (no network).

The STORY-45 pass signal is fewer than 1 in 5 drafted facts corrected, counted
over the rule cards. A card's "facts checked" starts as an estimate (one per
clause of its statement) that the reviewer may change.
"""

from __future__ import annotations

import csv
import difflib
import io
import logging
import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from realize_core.packs import loader as _loader
from realize_core.packs.models import VERIFICATION_NAMES, Pack
from realize_core.utils.cells import neutralize_cell
from realize_core.utils.text import escape_nonprintable as _shown

logger = logging.getLogger(__name__)

#: Core object families (spec 010 §2). Glossary entries and rule cards map to these.
CORE_FAMILIES = frozenset(
    {"project", "contact", "source", "requirement", "money-event", "milestone", "change", "decision", "issue"}
)
VERDICTS = ("correct", "corrected", "removed")
#: STORY-45 pass signal: fewer than 1 in 5 drafted facts corrected.
PASS_THRESHOLD = 0.2
#: Level a professional review asks for (spec 010 §5).
REVIEW_LEVEL = 2
REVIEWS_DIR = "reviews"
REMOVED_DIR = "removed"
SHEET_NAME = "review-sheet"

#: Columns of the review sheet. The last four are the reviewer's.
SHEET_COLUMNS = (
    "id",
    "type",
    "statement",
    "details",
    "source",
    "as_of",
    "review_by",
    "applies_to",
    "verification",
    "facts_checked",
    "verdict",
    "facts_corrected",
    "corrected_statement",
    "reviewer_note",
)
REQUIRED_COLUMNS = ("id", "verdict", "facts_corrected")
REVIEWER_COLUMNS = ("verdict", "facts_corrected", "corrected_statement", "reviewer_note")

#: Minutes a professional needs per row, for the time estimate on the sheet.
MINUTES_PER_ROW = {"rule": 5, "glossary": 5, "defaults": 2}

#: Languages whose Excel uses ';' as the list separator (decimal comma locales).
_SEMICOLON_LANGUAGES = frozenset({"pt", "es", "el", "fr", "de", "it", "nl", "pl", "ro", "tr", "cs", "sk", "hr"})
_RTL_LANGUAGES = frozenset({"he", "ar", "fa", "ur"})
_MARKET_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_ABBREVIATIONS = frozenset({"no", "nr", "art", "arts", "st", "vs", "cf", "etc", "inc", "co", "ltd", "approx", "para"})
_BOUNDARY = re.compile(r"(\S*)([.;!?])\s+(?=\S)")
#: Words in a card body that say its source is not the official text.
_SECONDARY_HINTS = re.compile(r"\b(secondary|opinion article|press|summari[sz]es|law-firm summary)\b", re.IGNORECASE)


class ReviewError(ValueError):
    """A review-kit request that cannot be carried out."""


class ReviewSheetError(ReviewError):
    """A filled-in sheet that fails validation. ``errors`` lists every problem found."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


class ReviewDeclinedError(ReviewError):
    """The person declined the corrections diff; nothing was written."""


# ---------------------------------------------------------------------------
# Pack access
# ---------------------------------------------------------------------------


def load_market_pack(code: str, packs_root: Path | None = None) -> Pack:
    """Load the installed market pack ``<code>`` or raise :class:`ReviewError`.

    Looks in the writable pack folder (``REALIZE_PACKS_PATH``) first, then in
    the shipped packs, like the resolver.
    """
    if not _MARKET_ID.match(code or ""):
        raise ReviewError(f"'{code}' is not a market pack id (expected something like 'pt')")
    pack = _loader.find_pack("market", code, packs_root)
    if pack is None:
        where = ", ".join(str(root / "market") for root in _loader.pack_roots(packs_root))
        raise ReviewError(f"Market pack '{code}' is not installed under {where}")
    return pack


def market_pack_ids(packs_root: Path | None = None) -> list[str]:
    """Ids of the installed market packs (folder names, every pack root), sorted."""
    ids: set[str] = set()
    for root in _loader.pack_roots(packs_root):
        market = root / "market"
        if market.is_dir():
            ids.update(p.name for p in market.iterdir() if (p / "pack.yaml").is_file())
    return sorted(ids)


def _read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = yaml.safe_load(text[3:end]) or {}
    return (meta if isinstance(meta, dict) else {}), text[end + 4 :].lstrip("\n")


def _glossary_files(pack: Pack) -> list[tuple[str, list[dict[str, Any]]]]:
    """``(language, entries)`` per glossary file, read straight from disk to keep the grouping."""
    out: list[tuple[str, list[dict[str, Any]]]] = []
    for gfile in sorted((pack.root / "glossary").glob("*.yaml")):
        try:
            data = yaml.safe_load(gfile.read_text(encoding="utf-8")) or []
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Glossary %s unreadable: %s", gfile, exc)
            continue
        entries = [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []
        out.append((gfile.stem, entries))
    return out


# ---------------------------------------------------------------------------
# Building the sheet
# ---------------------------------------------------------------------------


@dataclass
class SheetRow:
    """One row of a review sheet, before the reviewer fills it in."""

    id: str
    type: str  # "rule" | "glossary" | "defaults"
    statement: str
    details: str = ""
    source: str = ""
    as_of: str = ""
    review_by: str = ""
    applies_to: str = ""
    verification: str = ""
    facts_checked: int = 1


def estimate_facts(statement: str) -> int:
    """Estimate how many separate facts a statement makes: one per clause.

    Clauses end at a semicolon, or at a full stop followed by a new sentence.
    It is an estimate printed on the sheet; the reviewer may change it.
    """
    text = " ".join(str(statement or "").split())
    if not text:
        return 0
    count = 1
    for match in _BOUNDARY.finditer(text):
        word, mark = match.group(1), match.group(2)
        if mark == ";":
            count += 1
            continue
        nxt = text[match.end()]
        if not (nxt.isdigit() or (nxt.isalpha() and not nxt.islower())):
            continue
        stem = word.rstrip(".").casefold()
        if "." in stem or len(stem) <= 1 or stem in _ABBREVIATIONS:
            continue
        count += 1
    return count


def _level_text(level: int | None) -> str:
    if level is None:
        return ""
    return f"{level} ({VERIFICATION_NAMES.get(level, '?')})"


def _applies_to_text(applies_to: dict[str, Any]) -> str:
    family = str(applies_to.get("family") or "")
    kinds = applies_to.get("kinds") or []
    if isinstance(kinds, list) and kinds:
        return f"{family}: {', '.join(str(k) for k in kinds)}"
    return family


def _term_line(entry: dict[str, Any]) -> str:
    target = str(entry.get("family") or "?")
    if entry.get("kind"):
        target += f" / {entry['kind']}"
    elif entry.get("field"):
        target += f" (field: {entry['field']})"
    return f"{entry.get('term')} → {target}"


def _default_value(value: Any) -> str:
    return ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)


def build_sheet_rows(pack: Pack) -> list[SheetRow]:
    """Rows for a pack's review sheet: rule cards, then defaults, then one row per glossary file."""
    rows: list[SheetRow] = []
    level = pack.verification_level
    for card in sorted(pack.rules.values(), key=lambda c: c.path.name if c.path else c.id):
        rows.append(
            SheetRow(
                id=card.id,
                type="rule",
                statement=card.statement,
                details=card.body.strip(),
                source=card.source,
                as_of=card.as_of,
                review_by=card.review_by or "",
                applies_to=_applies_to_text(card.applies_to),
                verification=_level_text(card.verification),
                facts_checked=max(1, estimate_facts(card.statement)),
            )
        )
    if pack.defaults:
        rows.append(
            SheetRow(
                id="defaults",
                type="defaults",
                statement="\n".join(f"{k}: {_default_value(v)}" for k, v in pack.defaults.items()),
                details="Defaults the pack sets for every venture in this market.",
                verification=_level_text(level),
                facts_checked=len(pack.defaults),
            )
        )
    for language, entries in _glossary_files(pack):
        if not entries:
            continue
        rows.append(
            SheetRow(
                id=f"glossary:{language}",
                type="glossary",
                statement="\n".join(_term_line(e) for e in entries),
                details=(
                    f"Glossary ({language}): each local term mapped to a core family and kind. "
                    "Check that each term means what its mapping says."
                ),
                verification=_level_text(level),
                facts_checked=len(entries),
            )
        )
    return rows


def estimate_minutes(rows: list[SheetRow]) -> int:
    """Rough review time, rounded to the nearest quarter hour (at least 15 minutes)."""
    minutes = sum(MINUTES_PER_ROW.get(r.type, 5) for r in rows)
    return max(15, round(minutes / 15) * 15)


def default_delimiter(pack: Pack) -> str:
    """``;`` for markets whose Excel uses a decimal comma, else ``,``."""
    language = str(pack.defaults.get("locale") or "").split("-")[0].casefold()
    return ";" if language in _SEMICOLON_LANGUAGES else ","


def _cell(value: object) -> str:
    """Text for one CSV cell: trimmed lines, and never a formula a spreadsheet would run.

    Text a spreadsheet would read as a formula (``=``, ``+``, ``-``, ``@``,
    their full-width forms, after any leading spaces) gets the spreadsheet's
    "this is text" apostrophe (:func:`realize_core.utils.cells.neutralize_cell`).
    A leading space is not enough: some spreadsheets look through it.
    """
    text = "" if value is None else str(value)
    text = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()
    return neutralize_cell(text)


def render_csv(rows: list[SheetRow], delimiter: str = ",") -> str:
    """The sheet as CSV text: every cell quoted, so multi-line cells survive Excel and Google Sheets."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(SHEET_COLUMNS)
    for r in rows:
        values = (r.id, r.type, r.statement, r.details, r.source, r.as_of, r.review_by, r.applies_to)
        writer.writerow([*(_cell(v) for v in values), _cell(r.verification), str(r.facts_checked), "", "", "", ""])
    return buf.getvalue()


@cache
def _instructions() -> dict[str, dict[str, Any]]:
    path = Path(__file__).with_name("review_instructions.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _translation_language(pack: Pack) -> str | None:
    """The pack's first non-English language that has translated instructions."""
    for language in pack.languages:
        code = str(language).split("-")[0].casefold()
        if code != "en" and code in _instructions():
            return code
    return None


def _instruction_lines(text: dict[str, Any], minutes: int, title: str) -> list[str]:
    def fmt(s: str) -> str:
        return str(s).replace("{minutes}", str(minutes)).replace("{title}", title)

    lines = [f"## {fmt(text['heading'])}", ""]
    if text.get("label"):
        lines += [f"*{fmt(text['label'])}*", ""]
    lines += [fmt(text["intro"]), "", fmt(text["check_title"]), ""]
    lines += [f"{i}. {fmt(c)}" for i, c in enumerate(text["checks"], start=1)]
    lines += ["", fmt(text["fill_title"]), ""]
    lines += [f"- {fmt(f)}" for f in text["fill"]]
    lines += ["", fmt(text["closing"]), ""]
    return lines


def render_markdown(pack: Pack, rows: list[SheetRow]) -> str:
    """A printable sheet with short instructions in English and, where available, the pack's language."""
    minutes = estimate_minutes(rows)
    title = pack.title or pack.id
    counts = {t: sum(1 for r in rows if r.type == t) for t in ("rule", "glossary", "defaults")}
    lines = [
        f"# Review sheet: {title} market pack ({pack.ref})",
        "",
        (
            f"Verification level {_level_text(pack.verification_level) or 'unknown'}. "
            f"{counts['rule']} rule cards, {counts['glossary']} glossary lists and "
            f"{counts['defaults']} defaults row. Fill in `{SHEET_NAME}.csv`, or write on this printout "
            "and send it back."
        ),
        "",
    ]
    lines += _instruction_lines(_instructions()["en"], minutes, title)
    language = _translation_language(pack)
    if language:
        block = _instruction_lines(_instructions()[language], minutes, title)
        if language in _RTL_LANGUAGES:
            block = [f'<div dir="rtl" lang="{language}">', "", *block, "</div>", ""]
        lines += block
    lines += ["## Cards", ""]
    for number, row in enumerate(rows, start=1):
        lines += [f"### {number}. {row.id}", ""]
        if row.type == "rule":
            lines += [f"**Statement:** {row.statement}", ""]
            if row.details:
                lines += [f"> {line}" if line.strip() else ">" for line in row.details.splitlines()]
                lines.append("")
            lines += [
                f"- Source: <{row.source}>",
                f"- As of: {row.as_of}; review by: {row.review_by or 'not set'}",
                f"- Applies to: {row.applies_to or 'not set'}",
                f"- Current verification: {row.verification}",
                "",
            ]
        else:
            lines += [row.details, ""]
            lines += [f"- {line}" for line in row.statement.splitlines()]
            lines.append("")
        optional = "" if row.type == "rule" else " (optional row)"
        lines += [
            f"**Your review{optional}**",
            "",
            "- Verdict: ☐ correct ☐ corrected ☐ removed",
            f"- Facts checked: {row.facts_checked} (our estimate; change it if you count differently)",
            "- Facts corrected: ________",
            "- Corrected statement: ________",
            "- Reviewer note: ________",
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def write_review_sheet(
    code: str,
    fmt: str = "csv",
    *,
    out: Path | None = None,
    delimiter: str | None = None,
    packs_root: Path | None = None,
) -> Path:
    """Write a review sheet for a market pack. Returns the file written.

    ``fmt`` is ``csv`` (UTF-8 with BOM, every cell quoted) or ``md`` (printable).
    The default location is ``packs/market/<code>/reviews/review-sheet.<fmt>``.
    """
    if fmt not in ("csv", "md"):
        raise ReviewError(f"Unknown format '{fmt}': use csv or md")
    pack = load_market_pack(code, packs_root)
    rows = build_sheet_rows(pack)
    if not any(r.type == "rule" for r in rows):
        raise ReviewError(f"Pack {pack.ref} has no rule cards to review")
    path = Path(out) if out else pack.root / REVIEWS_DIR / f"{SHEET_NAME}.{fmt}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        path.write_text(render_csv(rows, delimiter or default_delimiter(pack)), encoding="utf-8-sig", newline="")
    else:
        path.write_text(render_markdown(pack, rows), encoding="utf-8", newline="")
    logger.info("Review sheet for %s written to %s", pack.ref, path)
    return path


# ---------------------------------------------------------------------------
# Reading and validating a filled sheet
# ---------------------------------------------------------------------------


@dataclass
class ReviewEntry:
    """The reviewer's answer for one sheet row. ``verdict`` is None when the row was not reviewed."""

    id: str
    type: str
    verdict: str | None
    facts_checked: int
    facts_corrected: int
    statement: str
    corrected_statement: str = ""
    note: str = ""


@dataclass
class Review:
    """A validated review of one pack."""

    pack_ref: str
    entries: list[ReviewEntry]
    warnings: list[str] = field(default_factory=list)

    def of_type(self, kind: str) -> list[ReviewEntry]:
        """Entries of one row type (``rule``, ``glossary`` or ``defaults``)."""
        return [e for e in self.entries if e.type == kind]

    def totals(self, kind: str = "rule") -> dict[str, Any]:
        """Counts and the correction ratio for one row type."""
        entries = self.of_type(kind)
        reviewed = [e for e in entries if e.verdict]
        checked = sum(e.facts_checked for e in reviewed)
        corrected = sum(e.facts_corrected for e in reviewed)
        out: dict[str, Any] = {"rows": len(entries), "reviewed": len(reviewed)}
        out.update({v: sum(1 for e in reviewed if e.verdict == v) for v in VERDICTS})
        out.update(
            {
                "facts_checked": checked,
                "facts_corrected": corrected,
                "ratio": round(corrected / checked, 3) if checked else None,
            }
        )
        return out

    @property
    def correction_ratio(self) -> float:
        """Facts corrected over facts checked, across the rule cards."""
        totals = self.totals("rule")
        return totals["facts_corrected"] / totals["facts_checked"] if totals["facts_checked"] else 0.0

    @property
    def passed(self) -> bool:
        """The STORY-45 signal: fewer than 1 in 5 drafted facts corrected."""
        return self.correction_ratio < PASS_THRESHOLD


def _norm_header(name: str) -> str:
    return re.sub(r"[\s\-]+", "_", name.replace("﻿", "").strip().strip('"').casefold())


def _norm_text(text: str) -> str:
    return " ".join(str(text or "").split())


def read_sheet(path: Path) -> list[dict[str, str]]:
    """Read a filled-in CSV sheet into one dict per row (comma, semicolon or tab separated)."""
    path = Path(path)
    if path.suffix.casefold() not in (".csv", ".tsv", ".txt"):
        raise ReviewSheetError([f"{path.name}: submit the CSV sheet (the .md sheet is for printing)"])
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReviewSheetError([f"cannot read {path}: {exc}"]) from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReviewSheetError(
            [
                f"{path.name} is not saved as UTF-8, so non-Latin text would be lost. In Excel use "
                "File > Save As > 'CSV UTF-8 (Comma delimited)'; in Google Sheets use File > Download > CSV."
            ]
        ) from exc
    header_line = text.lstrip().split("\n", 1)[0]
    delimiter = max((",", ";", "\t"), key=header_line.count)
    table = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    if not table:
        raise ReviewSheetError([f"{path.name} is empty"])
    header = [_norm_header(h) for h in table[0]]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ReviewSheetError([f"{path.name} has no {', '.join(missing)} column; export a fresh sheet"])
    rows: list[dict[str, str]] = []
    for values in table[1:]:
        if not any(v.strip() for v in values):
            continue
        record = {h: (values[i] if i < len(values) else "") for i, h in enumerate(header) if h}
        rows.append({k: v.replace("\r\n", "\n").replace("\r", "\n").strip() for k, v in record.items()})
    return rows


def _parse_count(text: str) -> int | None:
    """A whole number of facts, None when blank. Raises ValueError otherwise."""
    value = text.strip()
    if not value:
        return None
    number = float(value.replace(",", "."))
    if not math.isfinite(number) or number < 0 or number != int(number):  # "inf" would overflow int()
        raise ValueError(value)
    return int(number)


def parse_review(pack: Pack, raw_rows: list[dict[str, str]]) -> Review:
    """Validate a filled sheet against the pack. Raises :class:`ReviewSheetError` listing every problem.

    Every rule card needs a verdict; glossary and defaults rows are optional.
    """
    expected = {r.id: r for r in build_sheet_rows(pack)}
    errors: list[str] = []
    warnings: list[str] = []
    answers: dict[str, ReviewEntry] = {}
    seen: dict[str, int] = {}
    for number, raw in enumerate(raw_rows, start=2):
        row_id = raw.get("id", "").strip()
        answered = any(raw.get(c, "").strip() for c in REVIEWER_COLUMNS)
        if not row_id:
            if answered:
                errors.append(f"row {number}: has a review but no id")
            continue
        sheet_row = expected.get(row_id)
        if sheet_row is None:
            # Values from the sheet are shown escaped: these messages reach a terminal.
            errors.append(f"row {number}: unknown card id '{_shown(row_id)}' (not in {pack.ref})")
            continue
        if row_id in seen:
            errors.append(f"row {number}: '{row_id}' appears twice (first on row {seen[row_id]})")
            continue
        seen[row_id] = number
        where = f"row {number} ({row_id})"
        verdict = raw.get("verdict", "").strip().casefold() or None
        if verdict is None:
            if sheet_row.type == "rule":
                errors.append(f"{where}: no verdict; write correct, corrected or removed")
            elif answered:
                errors.append(f"{where}: has facts or notes but no verdict")
            continue
        if verdict not in VERDICTS:
            errors.append(f"{where}: verdict '{_shown(raw.get('verdict'))}' must be correct, corrected or removed")
            continue
        try:
            checked = _parse_count(raw.get("facts_checked", ""))
        except ValueError:
            errors.append(
                f"{where}: facts checked '{_shown(raw.get('facts_checked'))}' must be a whole number of 1 or more"
            )
            continue
        try:
            corrected = _parse_count(raw.get("facts_corrected", ""))
        except ValueError:
            errors.append(
                f"{where}: facts corrected '{_shown(raw.get('facts_corrected'))}' must be a whole number of 0 or more"
            )
            continue
        checked = sheet_row.facts_checked if checked is None else checked
        if checked < 1:
            errors.append(f"{where}: facts checked must be 1 or more")
            continue
        corrected_statement = raw.get("corrected_statement", "").strip()
        note = raw.get("reviewer_note", "").strip()
        if corrected is None:
            if verdict == "corrected":
                errors.append(f"{where}: verdict corrected needs the number of facts corrected (1 or more)")
                continue
            corrected = checked if verdict == "removed" else 0
        if verdict == "correct" and corrected:
            errors.append(f"{where}: verdict correct but {corrected} facts corrected; use corrected")
            continue
        if verdict == "corrected" and not corrected:
            errors.append(f"{where}: verdict corrected needs 1 or more facts corrected")
            continue
        if verdict == "corrected" and not (corrected_statement or note):
            errors.append(f"{where}: verdict corrected needs a corrected statement or a reviewer note")
            continue
        if corrected > checked:
            warnings.append(f"{where}: {corrected} facts corrected but {checked} checked; counting {corrected} checked")
            checked = corrected
        if (
            sheet_row.type == "rule"
            and raw.get("statement")
            # As exported (formula guard included), or with the guard a spreadsheet dropped.
            and _norm_text(raw["statement"])
            not in {_norm_text(sheet_row.statement), _norm_text(_cell(sheet_row.statement))}
        ):
            warnings.append(f"{where}: the card changed after this sheet was exported; check the review still applies")
        answers[row_id] = ReviewEntry(
            id=row_id,
            type=sheet_row.type,
            verdict=verdict,
            facts_checked=checked,
            facts_corrected=corrected,
            statement=sheet_row.statement,
            corrected_statement=corrected_statement,
            note=note,
        )
    for row_id, sheet_row in expected.items():
        if sheet_row.type == "rule" and row_id not in seen:
            errors.append(f"card '{row_id}' is missing from the sheet")
    if errors:
        raise ReviewSheetError(errors)
    entries = [
        answers.get(row_id)
        or ReviewEntry(
            id=row_id,
            type=sheet_row.type,
            verdict=None,
            facts_checked=sheet_row.facts_checked,
            facts_corrected=0,
            statement=sheet_row.statement,
        )
        for row_id, sheet_row in expected.items()
    ]
    return Review(pack_ref=pack.ref, entries=entries, warnings=warnings)


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------


@dataclass
class CardChange:
    """One change ``--apply-corrections`` would make to a rule card."""

    card_id: str
    action: str  # "edit" | "remove"
    path: Path
    old_text: str
    new_text: str = ""
    new_path: Path | None = None


def _with_statement(text: str, statement: str) -> str:
    end = text.find("\n---", 3)
    meta = yaml.safe_load(text[3:end]) or {}
    meta["statement"] = statement
    return "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=100) + text[end + 1 :]


def plan_corrections(pack: Pack, review: Review) -> list[CardChange]:
    """Card edits for corrected statements, and moves for removed cards. Glossary rows are not edited."""
    changes: list[CardChange] = []
    for entry in review.of_type("rule"):
        card = pack.rules.get(entry.id)
        if card is None or card.path is None:
            continue
        text = card.path.read_text(encoding="utf-8")
        if entry.verdict == "removed":
            target = pack.root / REVIEWS_DIR / REMOVED_DIR / card.path.name
            changes.append(CardChange(entry.id, "remove", card.path, text, new_path=target))
        elif (
            entry.verdict == "corrected"
            and entry.corrected_statement
            and _norm_text(entry.corrected_statement) != _norm_text(card.statement)
        ):
            changes.append(
                CardChange(entry.id, "edit", card.path, text, _with_statement(text, entry.corrected_statement))
            )
    return changes


def render_diff(changes: list[CardChange], pack_root: Path) -> str:
    """A unified diff of card edits, plus one line per removed card."""
    out: list[str] = []
    for change in changes:
        rel = change.path.relative_to(pack_root).as_posix()
        if change.action == "remove" and change.new_path is not None:
            dest = change.new_path.relative_to(pack_root).as_posix()
            out.append(f"remove {change.card_id}: {rel} -> {dest} (the loader stops reading it)\n")
            continue
        out.extend(
            difflib.unified_diff(
                change.old_text.splitlines(keepends=True),
                change.new_text.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )
    return "".join(out)


def _changelog_entry(pack_root: Path, line: str) -> None:
    """Record a rule-card change in the pack's CHANGELOG.md (spec 010 §9.3)."""
    path = pack_root / "CHANGELOG.md"
    bullet = f"- {line}"
    if not path.is_file():
        path.write_text(f"# Changelog\n\n## Unreleased\n\n{bullet}\n", encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    marker = "## Unreleased\n\n"
    if marker in text:
        text = text.replace(marker, f"{marker}{bullet}\n", 1)
    else:
        head, _, rest = text.partition("\n\n")
        text = f"{head}\n\n{marker}{bullet}\n\n{rest}".rstrip("\n") + "\n"
    path.write_text(text, encoding="utf-8")


def apply_corrections(pack: Pack, changes: list[CardChange], *, reviewer: str, today: str) -> list[str]:
    """Write planned changes to the pack and log them in its CHANGELOG. Returns one line per change."""
    done: list[str] = []
    for change in changes:
        if change.action == "remove" and change.new_path is not None:
            target = change.new_path
            if target.exists():
                target = target.with_name(f"{target.stem}-{today}{target.suffix}")
            target.parent.mkdir(parents=True, exist_ok=True)
            change.path.replace(target)
            rel = target.relative_to(pack.root).as_posix()
            done.append(f"removed `{change.card_id}` (moved to `{rel}`)")
        else:
            change.path.write_text(change.new_text, encoding="utf-8")
            done.append(f"corrected the statement of `{change.card_id}`")
    if done:
        _changelog_entry(pack.root, f"{today}, review by {reviewer}: " + "; ".join(done) + ".")
        logger.info("Applied %d review corrections to %s", len(done), pack.ref)
    return done


# ---------------------------------------------------------------------------
# Submitting a review
# ---------------------------------------------------------------------------


def reviewer_slug(reviewer: str) -> str:
    """File-name slug from the reviewer's name (the part before the first comma)."""
    name = reviewer.split(",", 1)[0].strip()
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
    if not slug:
        slug = re.sub(r"[^\w]+", "-", name.lower()).strip("-_")
    return slug[:60] or "reviewer"


def _unapplied(pack: Pack, review: Review) -> list[str]:
    """Rule cards whose review is not reflected in the pack yet (still present but removed, or not corrected)."""
    out = []
    for entry in review.of_type("rule"):
        card = pack.rules.get(entry.id)
        if card is None:
            continue
        if entry.verdict == "removed" or (
            entry.corrected_statement and _norm_text(entry.corrected_statement) != _norm_text(card.statement)
        ):
            out.append(entry.id)
    return out


def _whole_pack_problems(pack: Pack, review: Review, *, will_apply: bool) -> list[str]:
    """Why the pack's own level cannot be raised by this review, if anything stops it."""
    problems = [f"{e.id} was not reviewed" for e in review.entries if not e.verdict]
    problems += [
        f"{e.id} is marked corrected without a corrected statement; add the reviewer's wording to the sheet"
        for e in review.of_type("rule")
        if e.verdict == "corrected" and not e.corrected_statement
    ]
    if not will_apply:
        problems += [
            f"{card_id} needs its correction or removal applied (--apply-corrections)"
            for card_id in _unapplied(pack, review)
        ]
    return problems


@dataclass
class SubmitOutcome:
    """What :func:`submit_review` did."""

    review: Review
    record_path: Path
    approval_id: str | None
    cards: list[str]
    whole_pack: bool
    applied: list[str] = field(default_factory=list)
    pending_corrections: list[str] = field(default_factory=list)
    hand_edits: list[str] = field(default_factory=list)
    previous_approval: str | None = None


def _approval_note(
    review: Review, reviewer: str, record: Path, applied: bool, pending: list[str], hand_edits: list[str]
) -> str:
    totals = review.totals("rule")
    result = "pass" if review.passed else "fail"
    where = "/".join(record.parts[-5:]) if len(record.parts) >= 5 else record.as_posix()
    note = (
        f"Review by {reviewer}: {totals['facts_corrected']} of {totals['facts_checked']} drafted facts corrected "
        f"across {totals['rows']} rule cards ({result} against fewer than 1 in 5). Record: {where}."
    )
    if pending:
        note += f" Corrections not yet written to the cards: {', '.join(pending)}."
    elif applied:
        note += " Corrections were written to the cards before this request."
    if hand_edits:
        note += f" Edit by hand before approving: {', '.join(hand_edits)}."
    return note


def submit_review(
    code: str,
    sheet: Path,
    reviewer: str,
    *,
    venture: str,
    apply: bool = False,
    whole_pack: bool = False,
    confirm: Callable[[str], bool] | None = None,
    packs_root: Path | None = None,
    db_path: Path | None = None,
    today: str | None = None,
) -> SubmitOutcome:
    """Record a professional's review of a market pack and queue the level change for approval.

    Validates the sheet, optionally writes the reviewer's corrections into the
    cards (only after ``confirm`` accepts the diff), writes the review record to
    ``reviews/<date>-<reviewer>.yaml`` and calls
    :func:`~realize_core.packs.verify.request_verification` with the corrected
    fact counts. By default it asks for the reviewed, non-removed cards only;
    ``whole_pack`` asks for the pack's own level too (spec 010 §5: a card's
    level is the lower of its own and the pack's).
    """
    from realize_core.packs.verify import request_verification

    if not reviewer.strip():
        raise ReviewError("A named reviewer is required: --reviewer 'Name, title (registration)'")
    if not venture.strip():
        raise ReviewError("A venture is required for the approval queue")
    today = today or datetime.now(UTC).date().isoformat()
    pack = load_market_pack(code, packs_root)
    review = parse_review(pack, read_sheet(sheet))
    if whole_pack:
        problems = _whole_pack_problems(pack, review, will_apply=apply)
        if problems:
            raise ReviewError("The whole pack cannot be raised yet: " + "; ".join(problems))

    applied: list[str] = []
    if apply:
        changes = plan_corrections(pack, review)
        if changes:
            if confirm is None or not confirm(render_diff(changes, pack.root)):
                raise ReviewDeclinedError("Corrections not confirmed; nothing was written")
            applied = apply_corrections(pack, changes, reviewer=reviewer, today=today)
            pack = load_market_pack(code, packs_root)

    cards = [e.id for e in review.of_type("rule") if e.verdict != "removed" and e.id in pack.rules]
    pending = _unapplied(pack, review)
    hand_edits = [
        e.id
        for e in review.entries
        if (e.type != "rule" and e.verdict in ("corrected", "removed"))
        or (e.verdict == "corrected" and not e.corrected_statement)
    ]

    record_path = pack.root / REVIEWS_DIR / f"{today}-{reviewer_slug(reviewer)}.yaml"
    previous = None
    if record_path.is_file():
        old = yaml.safe_load(record_path.read_text(encoding="utf-8")) or {}
        previous = ((old.get("approval") or {}) if isinstance(old, dict) else {}).get("id")
    record = build_record(pack, review, reviewer, today, sheet, applied=applied, pending=pending, whole_pack=whole_pack)
    write_record(record_path, record)

    approval_id = None
    if whole_pack or cards:
        approval_id = request_verification(
            venture,
            kind="market",
            pack_id=pack.id,
            level=REVIEW_LEVEL,
            reviewer=reviewer.strip(),
            cards=[] if whole_pack else cards,
            corrections={e.id: e.facts_corrected for e in review.of_type("rule") if e.facts_corrected},
            note=_approval_note(review, reviewer.strip(), record_path, bool(applied), pending, hand_edits),
            packs_root=packs_root,
            db_path=db_path,
        )
        record["approval"] = {
            "id": approval_id,
            "action_type": "pack_verify",
            "venture": venture,
            "level": REVIEW_LEVEL,
            "cards": "all (pack level too)" if whole_pack else cards,
            "status": "pending: an owner with access to every venture approves or rejects it in the dashboard",
        }
        write_record(record_path, record)
    logger.info("Review of %s by %s recorded at %s (approval %s)", pack.ref, reviewer, record_path, approval_id)
    return SubmitOutcome(
        review=review,
        record_path=record_path,
        approval_id=approval_id,
        cards=[] if whole_pack else cards,
        whole_pack=whole_pack,
        applied=applied,
        pending_corrections=pending,
        hand_edits=hand_edits,
        previous_approval=previous,
    )


def build_record(
    pack: Pack,
    review: Review,
    reviewer: str,
    today: str,
    sheet: Path,
    *,
    applied: list[str],
    pending: list[str],
    whole_pack: bool,
) -> dict[str, Any]:
    """The review record written to ``reviews/<date>-<reviewer>.yaml``."""
    totals = review.totals("rule")
    rows = []
    for e in review.entries:
        row: dict[str, Any] = {"id": e.id, "type": e.type, "verdict": e.verdict or "not reviewed"}
        if e.verdict:
            row.update({"facts_checked": e.facts_checked, "facts_corrected": e.facts_corrected})
        row["statement"] = e.statement
        if e.corrected_statement:
            row["corrected_statement"] = e.corrected_statement
        if e.note:
            row["note"] = e.note
        rows.append(row)
    return {
        "pack": f"{pack.kind}/{pack.id}",
        "pack_version": pack.version,
        "reviewer": reviewer.strip(),
        "reviewed_on": today,
        "sheet": Path(sheet).name,
        "signal": {
            "rule": "fewer than 1 in 5 drafted facts corrected, over the rule cards (STORY-45)",
            "threshold": PASS_THRESHOLD,
            "ratio": totals["ratio"],
            "result": "pass" if review.passed else "fail",
        },
        "totals": {kind: review.totals(kind) for kind in ("rule", "defaults", "glossary") if review.of_type(kind)},
        "corrections_applied": applied,
        "corrections_pending": pending,
        "whole_pack": whole_pack,
        "approval": None,
        "warnings": review.warnings,
        "rows": rows,
        "note": (
            "Recorded from the reviewer's filled sheet by `realize-os packs review-submit`. "
            "The level change takes effect only when an owner approves the pack_verify request; it is then "
            "recorded in the verification state under DATA_PATH, not in the pack files."
        ),
    }


def write_record(path: Path, record: dict[str, Any]) -> None:
    """Write a review record as YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(record, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")


# ---------------------------------------------------------------------------
# Desk check (mechanical, no network)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeskFinding:
    """One mechanical finding: ``level`` is error, warning or info."""

    level: str
    target: str
    message: str


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _check_dates(meta: dict[str, Any], add: Callable[[str, str], None], today: date) -> None:
    as_of = _as_date(meta.get("as_of")) if meta.get("as_of") else None
    if not meta.get("as_of"):
        add("error", "as_of missing")
    elif as_of is None:
        add("error", f"as_of '{meta['as_of']}' is not a date (YYYY-MM-DD)")
    elif as_of > today:
        add("error", f"as_of {as_of} is in the future")
    review_by = _as_date(meta.get("review_by")) if meta.get("review_by") else None
    if not meta.get("review_by"):
        add("error", "review_by missing")
    elif review_by is None:
        add("error", f"review_by '{meta['review_by']}' is not a date (YYYY-MM-DD)")
    else:
        if review_by < today:
            add("error", f"review_by {review_by} has passed; the card counts as level 1 until reviewed again")
        if as_of and review_by <= as_of:
            add("error", f"review_by {review_by} is not after as_of {as_of}")
        elif as_of and (review_by - as_of).days > 366:
            add("warning", f"review_by is more than a year after as_of ({as_of} to {review_by})")


def _check_card(path: Path, code: str, today: date, seen: dict[str, str]) -> list[DeskFinding]:
    findings: list[DeskFinding] = []
    try:
        meta, body = _read_frontmatter(path)
    except (OSError, yaml.YAMLError) as exc:
        return [DeskFinding("error", path.name, f"cannot read card ({exc})")]
    card_id = str(meta.get("id") or "").strip()
    target = card_id or path.name

    def add(level: str, message: str) -> None:
        findings.append(DeskFinding(level, target, message))

    if not meta:
        add("error", "no front matter")
        return findings
    if not card_id:
        add("error", "id missing")
    elif card_id in seen:
        add("error", f"id also used by {seen[card_id]}; the loader keeps only one")
    else:
        seen[card_id] = path.name
        if not card_id.startswith(f"{code}."):
            add("warning", f"id does not start with '{code}.'")
    if not str(meta.get("statement") or "").strip():
        add("error", "statement is empty")
    source = str(meta.get("source") or "").strip()
    parsed = urlparse(source)
    if not source:
        add("error", "source missing")
    elif parsed.scheme != "https":
        add("error", f"source is not an https URL: {source}")
    elif not parsed.netloc:
        add("error", f"source has no host: {source}")
    _check_dates(meta, add, today)
    applies_to = meta.get("applies_to")
    if not isinstance(applies_to, dict) or not applies_to.get("family"):
        add("error", "applies_to.family missing")
    else:
        if applies_to["family"] not in CORE_FAMILIES:
            add("error", f"applies_to.family '{applies_to['family']}' is not a core family")
        kinds = applies_to.get("kinds")
        if kinds is not None and (not isinstance(kinds, list) or not all(isinstance(k, str) and k for k in kinds)):
            add("error", "applies_to.kinds must be a list of kind names")
    level = meta.get("verification", 1)
    if not isinstance(level, int) or not 0 <= level <= 4:
        add("error", f"verification '{level}' must be a whole number from 0 to 4")
    if not body.strip():
        add("warning", "no explanation in the card body")
    elif _SECONDARY_HINTS.search(body):
        add("info", "the body mentions secondary sources (press, opinion or summaries); check an official one")
    return findings


def desk_check(code: str, *, packs_root: Path | None = None, today: date | None = None) -> list[DeskFinding]:
    """Mechanical checks on a market pack's cards, glossary and manifest. No network calls.

    This is a pre-review aid, not a review: it can't tell whether a statement
    is true, only whether the card is complete, dated and well formed.
    """
    pack = load_market_pack(code, packs_root)
    today = today or datetime.now(UTC).date()
    findings: list[DeskFinding] = []
    seen: dict[str, str] = {}
    for path in sorted((pack.root / "rules").glob("*.md")):
        findings.extend(_check_card(path, code, today, seen))
    for language, entries in _glossary_files(pack):
        target = f"glossary/{language}.yaml"
        terms: set[str] = set()
        for entry in entries:
            term = str(entry.get("term") or "").strip()
            family = entry.get("family")
            if not term or not family:
                findings.append(DeskFinding("error", target, f"entry {entry} needs term and family"))
            elif family not in CORE_FAMILIES:
                findings.append(DeskFinding("error", target, f"'{term}' maps to '{family}', not a core family"))
            if term and term.casefold() in terms:
                findings.append(DeskFinding("warning", target, f"'{term}' is listed twice"))
            terms.add(term.casefold())
    if pack.verification_level is None:
        findings.append(DeskFinding("error", "pack.yaml", "verification.level missing"))
    if not pack.limits:
        findings.append(DeskFinding("warning", "pack.yaml", "no limits listed"))
    for message in pack.warnings:
        findings.append(DeskFinding("warning", "loader", message))
    return findings
