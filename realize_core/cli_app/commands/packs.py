"""``realize-os packs`` — reviewer kit for market packs (STORY-45).

Commands:
    realize-os packs review-sheet MARKET [--format csv|md] [--out PATH]
    realize-os packs review-submit MARKET --sheet PATH --reviewer "Name, title (registration)"
                                   [--venture KEY] [--apply-corrections [--yes]] [--whole-pack]
    realize-os packs desk-check MARKET

The sheet goes to a named local professional; their filled sheet comes back
through ``review-submit``, which records the review in the pack and queues a
``pack_verify`` approval. A person approves the level change in the dashboard.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import click
import typer

if TYPE_CHECKING:
    from realize_core.packs.review import SubmitOutcome

packs_app = typer.Typer(no_args_is_help=True)

_DELIMITERS = {"auto": None, "comma": ",", ",": ",", "semicolon": ";", ";": ";", "tab": "\t"}


def _echo(text: str = "", *, err: bool = False) -> None:
    """Print, replacing characters the console can't show instead of failing."""
    try:
        typer.echo(text, err=err)
    except UnicodeEncodeError:
        typer.echo(text.encode("ascii", "replace").decode("ascii"), err=err)


def _default_venture() -> str:
    from realize_core.config import load_config

    for system in load_config().get("systems") or []:
        if isinstance(system, dict) and system.get("key"):
            return str(system["key"])
    return ""


@packs_app.command("review-sheet")
def review_sheet(
    market: Annotated[str, typer.Argument(help="Market pack id, e.g. pt.")],
    fmt: Annotated[str, typer.Option("--format", "-f", help="csv (to fill in) or md (printable).")] = "csv",
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="Output file. Default: packs/market/<id>/reviews/.")
    ] = None,
    delimiter: Annotated[
        str, typer.Option("--delimiter", help="CSV separator: auto (by the pack's locale), comma, semicolon or tab.")
    ] = "auto",
) -> None:
    """Export a review sheet for a local professional to fill in."""
    from realize_core.packs.review import ReviewError, write_review_sheet

    if delimiter not in _DELIMITERS:
        _echo(f"Unknown delimiter '{delimiter}': use auto, comma, semicolon or tab", err=True)
        raise typer.Exit(2)
    try:
        path = write_review_sheet(market, fmt.casefold(), out=out, delimiter=_DELIMITERS[delimiter])
    except ReviewError as exc:
        _echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    _echo(f"Review sheet written: {path}")
    if fmt.casefold() == "csv":
        _echo("Send it with docs/reviewing-a-market-pack.md. Submit the filled sheet with: packs review-submit")


def _confirm_diff(yes: bool) -> Callable[[str], bool]:
    def confirm(diff: str) -> bool:
        _echo("Changes to the pack:")
        _echo(diff)
        if yes:
            return True
        try:
            return typer.confirm("Write these changes to the pack?", default=False)
        except click.exceptions.Abort:
            return False

    return confirm


def _print_outcome(outcome: SubmitOutcome, market: str, reviewer: str) -> None:
    review = outcome.review
    rules = review.totals("rule")
    pct = f"{rules['facts_corrected'] / rules['facts_checked']:.1%}" if rules["facts_checked"] else "n/a"
    result = "PASS" if review.passed else "FAIL"
    _echo(f"Review of market/{market} by {reviewer}")
    _echo(
        f"  Rule cards: {rules['rows']} ({rules['correct']} correct, {rules['corrected']} corrected, "
        f"{rules['removed']} removed)"
    )
    _echo(
        f"  Facts corrected: {rules['facts_corrected']} of {rules['facts_checked']} checked = {pct} "
        f"-> {result} (signal: fewer than 1 in 5)"
    )
    for kind, label in (("defaults", "Defaults"), ("glossary", "Glossary")):
        totals = review.totals(kind)
        if totals["rows"]:
            _echo(
                f"  {label}: {totals['reviewed']} of {totals['rows']} rows reviewed, "
                f"{totals['facts_corrected']} of {totals['facts_checked']} facts corrected"
            )
    for warning in review.warnings:
        _echo(f"  Warning: {warning}")
    for line in outcome.applied:
        _echo(f"  Applied: {line}")
    _echo(f"Record: {outcome.record_path}")
    if outcome.previous_approval:
        _echo(
            f"An earlier submission of this review queued approval {outcome.previous_approval}; "
            "reject it in the dashboard so only this one stands."
        )
    if outcome.approval_id:
        scope = "the whole pack (pack.yaml and every card)" if outcome.whole_pack else f"{len(outcome.cards)} cards"
        _echo(f"Approval queued: {outcome.approval_id} (pack_verify, {scope} to level 2).")
        _echo("Nothing changes until a person approves it in the dashboard (Approvals).")
        if not outcome.whole_pack:
            _echo(
                "Note: a card's level is the lower of its own and the pack's, so answers show level 2 only "
                "once the pack is raised too (re-submit with --whole-pack when every row is reviewed)."
            )
    else:
        _echo("No approval queued: every card was marked removed.")
    if outcome.pending_corrections:
        _echo(
            "Corrections not yet in the cards: "
            + ", ".join(outcome.pending_corrections)
            + ". Re-run with --apply-corrections before the approval is decided."
        )
    if outcome.hand_edits:
        _echo("Edit by hand (no corrected statement to apply): " + ", ".join(outcome.hand_edits))
    if outcome.applied:
        _echo("Spec 010: bump the pack version when you release this (patch for wording, major if cards were removed).")


@packs_app.command("review-submit")
def review_submit(
    market: Annotated[str, typer.Argument(help="Market pack id, e.g. pt.")],
    sheet: Annotated[Path, typer.Option("--sheet", "-s", help="The filled-in CSV sheet.")],
    reviewer: Annotated[
        str, typer.Option("--reviewer", "-r", help='Named professional: "Name, title (registration)".')
    ],
    venture: Annotated[
        str | None, typer.Option("--venture", "-v", help="Venture whose approval queue gets the request.")
    ] = None,
    apply_corrections: Annotated[
        bool, typer.Option("--apply-corrections", help="Write corrected statements into the cards (shows a diff).")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Apply corrections without asking.")] = False,
    whole_pack: Annotated[
        bool, typer.Option("--whole-pack", help="Ask to raise the pack's own level too (every row reviewed).")
    ] = False,
) -> None:
    """Record a professional's filled review sheet and queue the level change for approval."""
    from realize_core.db.schema import init_schema
    from realize_core.packs.review import ReviewDeclinedError, ReviewError, ReviewSheetError, submit_review
    from realize_core.packs.verify import PackVerificationError

    venture_key = venture or _default_venture()
    if not venture_key:
        _echo("Error: pass --venture KEY (no venture is configured in realize-os.yaml)", err=True)
        raise typer.Exit(1)
    if "," not in reviewer or "(" not in reviewer:
        _echo('Warning: name the reviewer as "Name, title (registration)" so the record shows who vouched.')
    try:
        init_schema()
        outcome = submit_review(
            market,
            sheet,
            reviewer,
            venture=venture_key,
            apply=apply_corrections,
            whole_pack=whole_pack,
            confirm=_confirm_diff(yes),
        )
    except ReviewSheetError as exc:
        _echo(f"The sheet has {len(exc.errors)} problem(s); nothing was recorded:", err=True)
        for error in exc.errors:
            _echo(f"  - {error}", err=True)
        raise typer.Exit(1) from exc
    except ReviewDeclinedError as exc:
        _echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    except (ReviewError, PackVerificationError) as exc:
        _echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    _print_outcome(outcome, market, reviewer.strip())


@packs_app.command("desk-check")
def desk_check(
    market: Annotated[str, typer.Argument(help="Market pack id, e.g. pt.")],
    on: Annotated[str | None, typer.Option("--on", help="Check dates as of this day (YYYY-MM-DD).")] = None,
) -> None:
    """Mechanical checks on every card (sources, dates, fields). No network; not a review."""
    from realize_core.packs.review import desk_check as run_desk_check

    try:
        today = date.fromisoformat(on) if on else None
        findings = run_desk_check(market, today=today)
    except ValueError as exc:  # a bad --on date, or ReviewError (unknown pack)
        _echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    _echo(f"Desk check of market/{market} (mechanical; not a professional review)")
    for finding in findings:
        _echo(f"  {finding.level.upper():7} {finding.target}: {finding.message}")
    errors = sum(1 for f in findings if f.level == "error")
    warnings = sum(1 for f in findings if f.level == "warning")
    _echo(f"{errors} error(s), {warnings} warning(s), {len(findings) - errors - warnings} note(s)")
    if errors:
        raise typer.Exit(1)
