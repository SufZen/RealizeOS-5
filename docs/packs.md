# Profession and market packs

RealizeOS speaks one core language. Packs add the specifics on top of it: a **profession pack** for a role (developer, architect, consultant, investor, broker) and a **market pack** for a country or region. The firm's own rules sit above both. This guide explains how to enable packs and write one. The design is in [ADR 0005](adr/0005-core-language-and-packs.md) and [spec 010](../.specify/specs/010-core-language-and-packs/spec.md).

## Turn packs on

Packs are behind a feature flag, off by default:

```yaml
# realize-os.yaml
features:
  packs: true
```

Then list the packs a venture uses in `systems/<venture>/packs.yaml`:

```yaml
profession:
  - id: developer
    version: "0.1.0"   # optional; omit to accept the installed version
market:
  - id: il
```

With the flag off, RealizeOS behaves as before: only the firm's own files and the core apply.

## Where packs come from

Packs are loaded from two folders, the first one winning:

1. **`REALIZE_PACKS_PATH`** (optional): a writable folder for your own packs, or a modified copy of a shipped pack. A pack here replaces the shipped pack with the same kind and id. Use the same layout: `<folder>/market/<id>/`, `<folder>/profession/<id>/`.
2. **The shipped packs** in `packs/`. They come with each release. In the production image this folder is read-only; change a shipped pack by copying it into `REALIZE_PACKS_PATH`, not by editing it in place.

In Docker, mount a folder for `REALIZE_PACKS_PATH` as a volume (see [self-hosting-guide.md](self-hosting-guide.md#volume-mounts)).

A venture loads only the packs its `packs.yaml` names. Loading is tolerant: a file with the wrong shape (a skill that is a list, a glossary that is a mapping, a rule card whose `applies_to` isn't a mapping, an unreadable file) is skipped with a warning that names the file, logged once. A pack that can't be loaded at all is skipped with a warning naming its folder; other packs and ventures keep working. The cascade is cached per venture and rebuilt when any pack file, override, `packs.yaml` or recorded verification changes.

## Which layer wins

The **firm** layer wins over the **market** pack, which wins over the **profession** pack, which wins over the **core**. Every resolved value records where it came from, such as `market il@0.1.0 · verification 1 (drafted)`. Agents receive that label with each rule they use.

| Item | Where packs keep it | Rule |
|---|---|---|
| Glossary term | `glossary/<lang>.yaml` | Highest layer wins per term |
| Rule card | `rules/*.md` | Highest layer wins per id; the firm can disable an id |
| Document template | `documents/` | Highest layer wins per file name |
| Skill | `R-routines/skills/*.yaml` | Highest layer wins per skill id |
| Trust default | `trust.yaml` | Highest layer wins per action |
| Measure | `measures.yaml` | Union; the firm can disable one |
| Default (currency, units, locale, work week) | `pack.yaml` `defaults` | Highest layer wins per field |

## Firm overrides

A firm overrides any pack inside its own venture folder, so the overrides travel with its brain:

```
systems/<venture>/F-foundations/overrides/
  defaults.yaml      e.g. {currency: USD}
  disable.yaml       list of rule, term or measure ids to switch off
  glossary/ rules/ documents/ trust.yaml measures.yaml
```

## Writing a pack

```
packs/<profession|market>/<id>/
  pack.yaml  glossary/  rules/  documents/  R-routines/skills/  schemas/  trust.yaml  measures.yaml  README.md
```

`pack.yaml`:

```yaml
id: il
kind: market            # profession | market
version: 0.1.0
title: Israel
languages: [he, en]
defaults: {country: IL, currency: ILS, units: metric, locale: he-IL}
verification: {level: 1, reviewed_by: null, review_by: 2027-04-01}
limits:
  - Does not replace a lawyer, appraiser or licensed engineer.
```

Packs contain content only. Python code belongs in the core or in an extension.

### Glossary

Each glossary entry maps a local term to a core family and, optionally, a kind:

```yaml
- term: "auto de medição"
  family: money-event
  kind: payment_claim
```

### Rule cards

A rule card is a dated fact with its source. A card without `source` and `as_of` is skipped with a warning.

```markdown
---
id: pt.price-revision
statement: Public works contracts include price revision under Decree-Law 6/2004.
source: https://diariodarepublica.pt/
as_of: 2026-10-13
review_by: 2027-04-13
verification: 1
applies_to: {family: money-event, kinds: [payment_claim]}
---
How agents should use the rule, and its exceptions.
```

### Schemas

A pack extends a core family with `allOf` (see [`fabric-schemas/README.md`](fabric-schemas/README.md)). It may add fields but must not retype core ones.

## Verification levels

| Level | Meaning |
|---|---|
| 0 | No market pack. Agents answer from general knowledge, labelled unverified. |
| 1 | Drafted from public sources, with links and dates. |
| 2 | Reviewed by a named local professional. |
| 3 | Maintained by a partner with a signed agreement. |
| 4 | Used in a paid engagement. |

A card's level is the lower of its own level and the pack's level. A card whose `review_by` date has passed drops to level 1.

### Raising a level: approvals and where they are recorded

Levels 2 and 3 are raised through a `pack_verify` approval (level 3 also needs a partner maintenance agreement; level 4 never comes from an approval). A pack is shared by every venture that uses it, so **only an owner with access to every venture** can approve or reject that request, from the dashboard, the API or MCP. An operator, an admin or an owner limited to some ventures gets 403 (`MCP_FORBIDDEN` over MCP), an outside agent never decides (`MCP_AGENT_CANNOT_DECIDE`), and the request stays pending.

An approved verification doesn't edit the pack. The level, the reviewer, the review date, the approver and the approval id are recorded in one file under `DATA_PATH`:

```
DATA_PATH/packs/verification.json
```

Each approval writes it once, atomically, so a failure leaves the previous state, never part of a review. The loader lays it over the pack files, so answers, `list_packs` and the tender register show the approved levels. A whole-pack approval raises the pack's own level and every card; a card approval raises those cards only. The usual rules still apply on top: the lower of card and pack, and a card past its `review_by` date shows level 1. If the pack's version changes after an approval, the pack carries a warning asking for the changed cards to be reviewed again.

The approval shows what happened, like any approved action: `execution_status` is `succeeded` or `failed`, `result_json` holds `{"output": "..."}` (for example "market/pt and its 10 rule cards raised to verification 2 (reviewed); reviewed by ..."), and `error` says why it failed (pack no longer installed, data folder not writable, ...). A failed approval is not retried: fix the cause and submit the request again (`review-submit` or `request_verification`).

## Moving to another server

**Settings → Storage & Backup → Export** (or `POST /api/storage/export`) includes, besides the ventures and databases:

- `data/packs/verification.json`: the approved levels (restore it into `DATA_PATH/packs/`);
- `custom-packs/`: everything in `REALIZE_PACKS_PATH` (restore it into the new `REALIZE_PACKS_PATH` folder);
- `packs-inventory.json`: every installed pack with its version, origin, content hash and levels, and what each venture resolves.

Shipped packs come with the release and are listed in the inventory only. After restoring, check that the new installation resolves the same packs, levels and rules:

```bash
python cli.py packs inventory --compare packs-inventory.json    # exits 1 and lists each difference
```

## Reviewing a market pack

Raising a market pack above level 1 needs a named local professional. Each level-1 pack ships a review sheet in `packs/market/<id>/reviews/` (`review-sheet.csv` to fill in, `review-sheet.md` to print). The loader ignores `reviews/`, so sheets, review records and removed cards kept there never reach an answer.

```bash
python cli.py packs review-sheet <id> [--format csv|md]     # export a sheet
python cli.py packs desk-check <id>                          # mechanical card checks, no network
python cli.py packs review-submit <id> --sheet filled.csv --reviewer "Name, title (registration)" [--venture KEY] [--apply-corrections [--yes]] [--whole-pack]
python cli.py packs inventory [--compare packs-inventory.json]   # installed packs, levels, each venture's rules
```

`review-submit` validates the sheet, writes a review record with the correction ratio, and queues a `pack_verify` approval; an owner with access to every venture approves the level change. The review record and any corrections are written into the pack folder, so run `review-submit` in a checkout of the repository (shipped packs) or on a pack in `REALIZE_PACKS_PATH`. See [drafting-a-market-pack.md](drafting-a-market-pack.md#2-review-level-2) for the flow and [reviewing-a-market-pack.md](reviewing-a-market-pack.md) for the page to send the reviewer.

## Agent access (MCP)

`list_packs`, `resolve_pack_item` and `glossary_lookup` are in the `kb` tool family. See [mcp-server.md](mcp-server.md).
