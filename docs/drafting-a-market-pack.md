# Drafting a market pack

A market pack gives RealizeOS the local language, money rules, permits, contract forms and duties of one country or region. An agent can draft one in under a day. A local professional then reviews it before anyone treats it as more than a draft. See [packs.md](packs.md) for the format and [ADR 0005](adr/0005-core-language-and-packs.md) for why.

## 1. Draft (verification level 1)

Use any capable agent (Claude, ChatGPT or another) with web search. Give it this brief, replacing the parts in angle brackets:

> Draft a RealizeOS market pack for **<country>** for the **<profession>** profession, following `docs/packs.md`.
> 1. `pack.yaml` with id, `kind: market`, version `0.1.0`, languages, defaults (country, currency, units, locale, work week), `verification.level: 1`, and a `limits` list that names what it does not replace.
> 2. A glossary per language that maps 15 to 25 local professional terms to core families: payment claims, quotes, changes and variations, permits, handover, contracts, the parties, defects.
> 3. 10 to 20 rule cards on VAT and other taxes on works, indexation or price revision, change rules, contractor licensing, permits and approvals, sale and disclosure duties, and energy certificates. Each card needs one statement, an `applies_to` family and kinds, a `source` URL (official where possible; say so in the body when it is secondary), `as_of` set to today, `review_by` six months ahead, and `verification: 1`.
> 4. A README that states the level, what is missing, and who could review it.
>
> Never state a rate, threshold or deadline without a source. If sources disagree, say so in the card body.

Put the result in `packs/market/<id>/`. Then:

- run `pytest tests/test_market_pack_pt.py` as a model for a smoke test, or copy it for the new market;
- confirm the pack loads with no warnings: `python -c "from realize_core.packs import discover_packs; print(discover_packs()[('market', '<id>')].warnings)"`;
- confirm no core code was needed. If it was, stop and reopen ADR 0005.

## 2. Review (level 2)

A named local professional (lawyer, solicitor, engineer, quantity surveyor or accountant, depending on the card) reviews each card. They need no access to RealizeOS: they fill in a sheet, and the CLI does the rest. Send them [reviewing-a-market-pack.md](reviewing-a-market-pack.md) with the sheet.

**1. Export the sheet.** Every shipped level-1 pack already has one in `packs/market/<id>/reviews/`. To export it again after a card changes:

```bash
python cli.py packs review-sheet pt                # reviews/review-sheet.csv, to fill in
python cli.py packs review-sheet pt --format md    # reviews/review-sheet.md, printable
```

The CSV is UTF-8 with a byte-order mark and every cell quoted, so Greek, Hebrew and Portuguese text and multi-line cells open cleanly in Excel and Google Sheets. It uses `;` as the separator for markets whose Excel uses a decimal comma (Portugal, Spain, Greece, Cyprus) and `,` elsewhere; `--delimiter comma|semicolon|tab` overrides it. The printable sheet starts with short instructions in English and, where the pack has another language, an agent-translated copy.

The sheet has one row per rule card, one for the defaults and one per glossary file. The reviewer fills in four columns per row:

| Column | Meaning |
|---|---|
| `verdict` | `correct`, `corrected` or `removed`. Required on every rule card; optional on the defaults and glossary rows. |
| `facts_corrected` | Whole number, 0 or more. Blank means 0 for `correct` and every checked fact for `removed`. |
| `corrected_statement` | The reviewer's wording. A `corrected` row needs this or a note. |
| `reviewer_note` | Anything else: a better source, an exception. |

`facts_checked` is pre-filled with an estimate (one fact per clause of the statement). The reviewer may change it.

**2. Optional: desk-check before sending.** `python cli.py packs desk-check pt` checks every card mechanically with no network calls: an https source, sane `as_of` and `review_by` dates (the review date not passed), a statement, a core family in `applies_to`, unique ids, and a note where the body says the source is secondary. It is a pre-review aid, not a review. An agent may also open each source and write its notes to `reviews/desk-check-<date>.md`, labelled "agent desk check — not a professional review"; it never changes cards or levels.

**3. Record the filled sheet.**

```bash
python cli.py packs review-submit pt --sheet filled.csv --reviewer "Ana Silva, advogada (OA 12345)" --venture <key> --apply-corrections
```

This:

- validates the sheet and lists every problem at once (a missing verdict, a card left out, an unknown id, a facts count that is not a whole number, `correct` with facts corrected), and records nothing if there is one;
- with `--apply-corrections`, shows a diff and asks before writing (`--yes` skips the question): corrected statements go into the cards; removed cards move to `reviews/removed/`, which the loader ignores; both are logged in the pack's `CHANGELOG.md`. Glossary and defaults corrections are listed for you to edit by hand. Without the flag no card changes;
- writes the review record to `reviews/<date>-<reviewer>.yaml`: reviewer, date, every row's verdict, facts checked and corrected, notes, totals, the correction ratio and pass or fail;
- queues a `pack_verify` approval through `request_verification(...)` for the reviewed, non-removed cards, with `corrections={card_id: n}`. Nothing is raised until an owner approves it in the dashboard (Approvals).

`review-submit` writes the record (and, with `--apply-corrections`, the corrected cards) into the pack folder. Shipped packs are read-only in the production image, so run it in a checkout of the repository and release the result, or on a pack you keep in `REALIZE_PACKS_PATH` (see [packs.md](packs.md#where-packs-come-from)).

The pass signal is computed over the rule cards: facts corrected ÷ facts checked must be below 1 in 5. A removed card counts all its facts as corrected unless the reviewer says otherwise. Glossary and defaults rows are reported separately.

**4. Approve.** The pack is shared by every venture that uses it, so only an owner with access to every venture can approve or reject the request (an operator, an admin or an owner limited to some ventures gets 403, and the request stays pending). When the owner approves it, the level (2), the reviewer, the review date, the approver and the approval id of each reviewed card are recorded in the installation's verification state, `DATA_PATH/packs/verification.json`, in one atomic write. The card files are not edited, so this works with read-only shipped packs; answers show the new level straight away. The approval shows the outcome (`execution_status` `succeeded` or `failed`, with the reason in `error`). Rejecting it changes nothing. If you submit the same review again on the same day, the command names the earlier approval so you can reject it.

**5. Raise the pack's own level.** A card's effective level is the lower of its own and the pack's, so the cards only show level 2 once the pack's own level is raised too. Once every row, including the defaults and glossary rows, has a verdict and the corrections are in the cards, submit with `--whole-pack`: the approval then covers the pack's own level and every card, and records the corrections with it. To ship the reviewed level with the pack itself (for every installation), the maintainer also sets `verification` in `pack.yaml` and the cards and releases a new version.

**6. Record the result.** Write pass or fail, with the numbers from the review record, into ADR 0005's validation note. Spec 010 §9.3 also asks for a version bump when you release the corrected pack: patch for wording, major if cards were removed.

### From Python

The CLI wraps the same API. To queue a request directly, for example from an agent:

```python
from realize_core.packs.verify import request_verification

request_verification(
    "<venture used for maintenance>",
    kind="market", pack_id="pt", level=2,
    reviewer="Name Surname, advogada (OA 12345)",
    corrections={"pt.vat.rates": 1},
)
```

With no `cards`, the whole pack is raised once approved: the reviewer and date are recorded for the pack's own level and every card. Pass `cards=[...]` to verify only some cards; the pack's own level then stays as it was. `realize_core.packs.review.submit_review(...)` runs the full sheet flow above. Approving goes through `realize_core.governance.gates.decide_approval(..., decider=Decider(...))`, which refuses anyone but an owner with access to every venture before anything changes.

## 3. Maintain (level 3)

Level 3 needs a partner with a signed maintenance agreement (`partner_agreement="..."`). It is checked again when the approval is applied and recorded with the level. The partner owns updates and every card's `review_by` date. A card whose review date passes drops back to level 1 automatically, whatever level was approved.

## 4. Field-proven (level 4)

Level 4 is never requested. It comes from a paid engagement that used the pack and produced a value-report number.
