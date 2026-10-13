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
| Skill | `R-routines/skills/*.yaml` | The venture's own skill wins; then highest layer per skill id; the firm can disable an id |
| Skill settings | `skill-settings.yaml` | Triggers from every layer are added; variables come from the firm only |
| Agent | `A-agents/*.md` | The venture's own agent wins; then highest layer per agent key |
| Schema extension | `schemas/*.json` | Highest layer wins per name; never replaces a core schema |
| Trust default | `trust.yaml` | Only where stricter than the venture's trust ladder; never loosens |
| Measure | `measures.yaml` | Union; the firm can disable one |
| Default (currency, units, locale, work week) | `pack.yaml` `defaults` | Highest layer wins per field |

## What packs change at run time

With `features.packs` on, a venture's packs are used everywhere the venture's own files are. Nothing new runs: pack content goes through the same code, checks and approvals as the firm's own.

The order is always the same, highest first: **the venture's own files** (its `A-agents/`, `R-routines/skills/`, the firm's shared skills), then **firm overrides** (`F-foundations/overrides/`), then **market packs**, then **profession packs**, then **the core**.

- **Context.** Local terms, defaults and the most relevant rule cards go into the agent's prompt; each rule card appears in the answer trail with its level (see below).
- **Skills.** The skills of the venture's packs join its own skills: they trigger on their phrases, show in skill lists, and run with `trigger_skill`. A pack skill runs through the same executor as any skill: its tool steps go through the governance gate, writes wait for an approval, a held step pauses the workflow until it is approved, and an outside agent's writes are always held. A skill the venture already has (same id or name) is never replaced, so existing ventures with copied skills keep running their copies, and no skill is listed or run twice. The answer trail lists a pack skill as a `W1` source with its layer and pack. The app loads the skills at startup and on every config reload (`POST /api/systems/reload`); edit a pack, then reload.
- **Agents.** The agents of the venture's packs join its own. The venture's own file wins over a pack agent with the same key. A pack agent is only a prompt: it gets the same tools as any agent of the venture, behind the same gate, and can't bring a `persona.yaml`. The answer trail lists it as an `A1` source with its layer and pack. When the venture has no `A-agents/_README.md`, the routing guide of its highest pack is used. The agent registry (`GET /api/agents`, `?venture=<key>` for one team) lists a venture's pack agents next to its own, with `layer`, `pack` and `verification`; they are read-only there: editing or removing one returns `409` with the `override_path` where the venture's own copy goes, and nothing is written into the pack (see [api-reference.md](api-reference.md#agent-registry)).
- **Schemas.** Entity validation (`POST /api/fabric/lint`, `realize-os fabric lint`) uses the core schemas plus the schema extensions of the venture's packs, per venture: another venture never sees them. An extension may add fields and constrain `kind`; one that takes a core schema's name or `$id`, or doesn't extend a core family with `allOf`, is skipped with a warning, and a property that retypes a core one is dropped (the core type holds).
- **Trust defaults.** A pack's `trust.yaml` can only make the venture stricter: `auto` can become `approve` or `block`, `approve` can become `block`. The trust ladder in `realize-os.yaml` decides first; packs and the firm's `F-foundations/overrides/trust.yaml` are laid over it where they are stricter. A value that would loosen a decision is ignored and logged (`... would loosen gmail_send from approve to auto; ignored`). The key is a tool action (`sheets_append`) or the governance action it falls under (`data_write`, `send_email`; `unknown_write` for a write the ladder has no rule for). To switch a pack's default off, list the action in `F-foundations/overrides/disable.yaml`: the action goes back to the ladder's decision, never below it. **Settings → Trust Ladder** in the dashboard (and `GET /api/trust`, see [api-reference.md](api-reference.md#trust)) shows each venture's effective decision per action, the pack or firm default that tightened it (such as *market pack pt@0.1.0*), and the defaults that were ignored because they would loosen it.

A pack file that resolves outside its pack folder (a link to elsewhere) is skipped with a warning.

With the flag off, none of this happens: skills, agents, validation and trust are exactly what they were before packs.

## Firm overrides

A firm overrides any pack inside its own venture folder, so the overrides travel with its brain:

```
systems/<venture>/F-foundations/overrides/
  defaults.yaml        e.g. {currency: USD}
  disable.yaml         list of rule, term, measure, skill, agent, schema or trust ids to switch off
  skill-settings.yaml  the venture's ids (and extra triggers) for skills that come from packs
  glossary/ rules/ documents/ trust.yaml measures.yaml
```

### Skill settings

A skill from a pack is shared by every venture that links the pack, so its sheet and document ids can't live in it. Each venture sets them in `F-foundations/overrides/skill-settings.yaml`, by skill id:

```yaml
payment_milestone_check:
  variables:
    milestones_sheet_id: "1AbC..."
    payments_sheet_id: "1AbC..."
  triggers: ["payment claim 7"]     # optional: more phrases, in your own words
```

Triggers are added to the skill's own. A pack can ship a `skill-settings.yaml` too, to add triggers to a skill from a lower layer: the Israel market pack adds Hebrew triggers to the developer pack's skills. Only the firm sets `variables`; a pack that tries is ignored and logged. A venture created from a template that links packs gets a starter file listing the ids it needs.

## Writing a pack

```
packs/<profession|market>/<id>/
  pack.yaml  glossary/  rules/  documents/  A-agents/  R-routines/skills/  skill-settings.yaml
  schemas/  trust.yaml  measures.yaml  README.md
```

`A-agents/*.md` and `R-routines/skills/*.yaml` use the same format as a venture's own agents and skills (see [skill-authoring.md](skill-authoring.md)). `A-agents/_README.md` is the team's routing guide; other `_` files are notes.

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

A pack extends a core family with `allOf` (see [`fabric-schemas/README.md`](fabric-schemas/README.md)). It may add fields but must not retype core ones. The file name is the entity type it validates (`schemas/payment-claim.json` validates `type: payment-claim`). It can't use a core family's name or `$id`.

### Templates that link packs

A venture template can name packs (`packs:` in `templates/<name>.yaml`). With the flag on, `scaffold_venture(template=...)` (the dashboard, `realize-os venture create --template`) writes the venture's `packs.yaml`, copies only the firm's starter files, and leaves out the agents and skills the linked packs provide, at the same path, in `A-agents/` and `R-routines/skills/`. It writes `F-foundations/overrides/skill-settings.yaml` with the ids to set. With the flag off it copies the whole template, as before. `python cli.py init --template` is unchanged.

## Verification levels

| Level | Meaning | Label in the answer trail | Hebrew |
|---|---|---|---|
| 0 | No market pack. Agents answer from general knowledge, labelled unverified. | unverified | לא מאומת |
| 1 | Drafted from public sources, with links and dates. | draft — not reviewed | טיוטה — לא נבדקה |
| 2 | Reviewed by a named local professional. | reviewed | נבדק |
| 3 | Maintained by a partner with a signed agreement. | maintained | מתוחזק |
| 4 | Used in a paid engagement. | field-proven | הוכח בשטח |

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

`python cli.py storage restore <zip> --directory <new folder>` unpacks it so that `<new folder>/data` is the new `DATA_PATH` and `<new folder>/custom-packs` the new `REALIZE_PACKS_PATH` (see [self-hosting-guide.md](self-hosting-guide.md#move-to-another-server-export-and-restore)). Shipped packs come with the release and are listed in the inventory only. After restoring, check that the new installation resolves the same packs, levels and rules:

```bash
python cli.py packs inventory --compare packs-inventory.json    # exits 1 and lists each difference
```

## Rule cards in the answer trail

The rule cards an answer's prompt included appear in its "What I used" trail as `[R1]`, `[R2]`, next to the knowledge-base sources (`[S1]`…). Each rule row shows, whatever the model wrote:

- the level and its label, such as **Level 1 · draft — not reviewed** (marked as needing attention at levels 0 and 1, green from level 2);
- the layer and pack it came from, such as *market pack pt@0.1.0* (the firm's own rules show *your firm*);
- the card's `as_of` date, with its `review_by` date on hover, and a link to its source.

`[R1]` and `[S1]` markers in the answer jump to their trail rows. The labels follow the dashboard's language (English or Hebrew). The same fields (`layer`, `pack`, `verification`, `as_of`, `review_by`) come back from `POST /api/chat`, the `/api/chat/stream` events, `GET /api/conversations` and the MCP trail summary (`realize_chat` and `get_history`), so another agent can show the level too. Older answers, stored before the trail kept rule levels, have none on their rule rows; the dashboard labels those rows *unverified* rather than guess.

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

`list_packs`, `resolve_pack_item` and `glossary_lookup` are in the `kb` tool family. `resolve_pack_item` resolves `term`, `rule`, `document`, `skill`, `agent`, `trust`, `measure` and `default` items. A venture's pack skills and agents also show in `list_skills`, `list_workflows` and `list_agents` like its own, and run with `trigger_skill` (held for a person's approval when an outside agent asks). See [mcp-server.md](mcp-server.md).
