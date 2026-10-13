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

## Reviewing a market pack

Raising a market pack above level 1 needs a named local professional. Each level-1 pack ships a review sheet in `packs/market/<id>/reviews/` (`review-sheet.csv` to fill in, `review-sheet.md` to print). The loader ignores `reviews/`, so sheets, review records and removed cards kept there never reach an answer.

```bash
python cli.py packs review-sheet <id> [--format csv|md]     # export a sheet
python cli.py packs desk-check <id>                          # mechanical card checks, no network
python cli.py packs review-submit <id> --sheet filled.csv --reviewer "Name, title (registration)" [--venture KEY] [--apply-corrections [--yes]] [--whole-pack]
```

`review-submit` validates the sheet, writes a review record with the correction ratio, and queues a `pack_verify` approval; a person approves the level change. See [drafting-a-market-pack.md](drafting-a-market-pack.md#2-review-level-2) for the flow and [reviewing-a-market-pack.md](reviewing-a-market-pack.md) for the page to send the reviewer.

## Agent access (MCP)

`list_packs`, `resolve_pack_item` and `glossary_lookup` are in the `kb` tool family. See [mcp-server.md](mcp-server.md).
