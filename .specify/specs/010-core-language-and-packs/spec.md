# Core Language and Packs — v0.1

> The shared object model every RealizeOS pack and agent speaks, and the format of profession, market and firm packs that layer on top of it. Decided in [ADR 0005](../../../docs/adr/0005-core-language-and-packs.md).
>
> Status: Draft v0.1 · Builds on [spec 002](../002-fabric-entity-schemas/spec.md) (soft FABRIC schemas) · Feature flag: `features.packs` (default `false`)

---

## 1. Goals and non-goals

**Goals**

- A small set of typed core objects, so a payment claim, a change or a decision means the same thing to every profession, market and agent.
- A pack format that is pure content, so partners and agents can author packs and professionals can review them.
- A run-time cascade (firm > market > profession > core) that returns every resolved value with its provenance.
- Market knowledge that carries a source, an as-of date and a verification level.
- Existing ventures and `python cli.py` paths keep working with the flag off.

**Non-goals (v0.1)**

- No pack registry, marketplace or remote installation. Packs ship in the repo or sit in a local folder.
- No executable code inside packs. Tools stay in `realize_core/tools/` and in extensions.
- No hard validation. As in spec 002, schemas produce warnings and never refuse content.
- No new runtime dependencies. YAML is read with PyYAML, and schemas are checked by the existing hand-rolled validator (`realize_core/fabric/validator.py`).

---

## 2. Core objects

Nine object families. Each is a soft JSON Schema (Draft 2020-12) in `docs/fabric-schemas/`, inherits the common fields from spec 002 (`id`, `type`, `venture`, `source`, `created_by`, `verified`, …), and adds the fields below. Packs specialise a family through its `kind` field and add fields of their own (§4.3).

| Family | Schema file | Status | Key fields | Example kinds |
|---|---|---|---|---|
| Project · Site | `project.json` | new | `name`, `status`, `site.address`, `site.country`, `market`, `members[]`, `budget`, `currency` | `development`, `renovation`, `acquisition` |
| Party · Role | `contact.json` | **exists** (spec 002), add `roles[]` | `roles[].project`, `roles[].role` | `client`, `contractor`, `lender`, `tenant`, `authority`, `investor` |
| Document · Source | `source.json` | new | `uri`, `media_type`, `language`, `locator` (page, cell, timestamp, message id), `captured_at` | `contract`, `drawing`, `message`, `voice_note`, `quote` |
| Requirement | `requirement.json` | new | `statement`, `mandatory`, `owner`, `due`, `status`, `sources[]` | `tender_item`, `code_rule`, `covenant`, `brief_line` |
| Money event | `money-event.json` | new | `amount`, `currency`, `direction`, `counterparty`, `milestone`, `lines[]`, `status`, `sources[]` | `budget_line`, `quote`, `payment_claim`, `invoice`, `capital_call` |
| Milestone | `milestone.json` | new | `name`, `due`, `criteria[]`, `percent_of_contract`, `status` | `construction_stage`, `design_stage`, `permit`, `handover` |
| Change | `change.json` | new | `requested_by`, `scope_delta`, `cost_delta`, `time_delta_days`, `status`, `decision` | `client_change`, `variation`, `design_revision` |
| Decision · Approval | `decision.json` | **exists** (spec 002), link to approvals | `approval_id` (row in `approval_queue`), `basis` (sources) | `commercial`, `technical`, `payment`, `scope` |
| Issue · Risk | `issue.json` | new | `severity`, `likelihood`, `owner`, `status`, `raised_from` | `defect`, `delay`, `discrepancy`, `compliance` |

Rules:

- **`sources[]` everywhere money or obligations appear.** Each entry is a `source` id plus a `locator`. This is what lets the trail show "where did this number come from".
- **Amounts carry their currency.** There is no implicit currency; the market pack only supplies the default.
- **`kind` values are open strings.** The core lists the kinds above. Packs may add kinds and must map each one to a family.
- **Relations are ids.** For example `money_event.milestone → milestone.id` and `change.decision → decision.id`. The indexer's `x-indexing.graph_relations` declares them, as in spec 002.

---

## 3. Layers and the cascade

```
firm        systems/<venture>/        (FABRIC: F-foundations, B-brain, rules, overrides)
market      packs/market/<id>/        e.g. il, pt
profession  packs/profession/<id>/    e.g. developer, architect
core        realize_core + docs/fabric-schemas/
```

A venture enables packs in `systems/<venture>/packs.yaml`:

```yaml
profession:
  - id: developer
    version: "0.1.0"
market:
  - id: il
    version: "0.1.0"
```

### 3.1 What resolves through the cascade

| Item | Key | Merge rule |
|---|---|---|
| Glossary term | `(language, term)` | Higher layer wins per key; all layers' terms stay searchable |
| Rule card | `rule.id` | Higher layer replaces by id; the firm can also `disable` an id |
| Document template | `template.id` | Higher layer replaces |
| Skill | `skill.id` | The venture's own skill wins; then higher layer replaces; skills from all layers are listed. `skill-settings.yaml` adds triggers from any layer and variables from the firm only |
| Agent | agent key | The venture's own agent wins; then higher layer replaces |
| Schema extension | file name | Higher layer replaces; never a core schema (extend only) |
| Trust default | `action_name` | Only stricter: packs and firm overrides tighten the venture's trust ladder (`realize-os.yaml`) and never loosen it; a looser value is ignored and logged (owner decision 2026-10-13) |
| Measure (value-report line) | `measure.id` | Union; the firm can disable |
| Defaults (currency, units, locale, work week) | field name | Higher layer wins |

### 3.2 Resolver contract

```python
def resolve(item_type: str, key: str, *, venture: str) -> Resolved | None: ...

@dataclass(frozen=True)
class Resolved:
    value: Any
    layer: Literal["firm", "market", "profession", "core"]
    pack_id: str | None        # e.g. "il@0.1.0"
    verification: int | None   # 0-4, for market facts
    source: str | None         # rule-card source URL or FABRIC path
```

- Resolution is deterministic and cached per venture until a pack or `packs.yaml` changes.
- Every resolved value used in an agent answer adds a `source` event to the chat trail (spec 006), carrying `layer`, `pack_id` and `verification`.
- With `features.packs=false` the resolver returns only the firm and core layers, which is today's behaviour.

---

## 4. Pack format

### 4.1 Layout

```
packs/<kind>/<id>/
  pack.yaml            manifest
  A-agents/            agent definitions (same format as templates)
  R-routines/skills/   skills v2 YAML
  skill-settings.yaml  extra triggers for skills of lower layers
  schemas/             JSON Schema extensions of core families
  glossary/<lang>.yaml term -> family/kind mapping
  rules/               rule cards (market packs mainly)
  documents/           document templates (STORY-31 format)
  measures.yaml        value-report lines
  trust.yaml           trust defaults per action
  README.md            what the pack does and what it can't do
```

Every folder is optional. A pack with only a glossary and rules is valid.

### 4.2 `pack.yaml`

```yaml
id: il
kind: market                  # profession | market
version: 0.1.0
title: Israel
requires:
  core: ">=0.1"
  packs: []                   # e.g. ["developer>=0.1"] for a pack that extends another
languages: [he, en]
defaults:                     # market packs only
  country: IL                 # ISO 3166-1 alpha-2
  currency: ILS
  units: metric
  work_week: [sun, mon, tue, wed, thu]
  locale: he-IL
verification:                 # market packs: the pack's overall level
  level: 1                    # 0-4, see §5
  reviewed_by: null
  reviewed_at: null
  review_by: 2027-04-01
limits:                       # shown to users; candor (filter 7)
  - "Does not replace a lawyer, appraiser or licensed engineer."
authors: ["Realization"]
license: BSL-1.1
```

### 4.3 Extending a core family

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "pack://developer/payment-claim.json",
  "title": "Payment claim (developer)",
  "allOf": [{ "$ref": "https://realizeos.ai/schemas/v0.1/money-event.json" }],
  "properties": {
    "kind": { "const": "payment_claim" },
    "retention_percent": { "type": "number" },
    "checked_lines": { "type": "integer" }
  }
}
```

Extensions may add properties and constrain `kind`. They may not remove or retype core properties; the validator warns if they try.

### 4.4 Glossary

```yaml
# packs/market/il/glossary/he.yaml
- term: "חשבון חלקי"
  family: money-event
  kind: payment_claim
- term: "פקודת שינויים"
  family: change
  kind: variation
- term: "הצמדה למדד תשומות הבנייה"
  family: money-event
  field: indexation
```

Agents get the merged glossary in their prompt context for the venture's languages. Ingestion uses it to classify incoming documents and messages into core families.

### 4.5 Rule card

```markdown
---
id: il.indexation.construction-input-index
applies_to: { family: money-event, kinds: [payment_claim, quote] }
statement: Residential construction contracts are commonly linked to the construction input index published by the Central Bureau of Statistics.
source: https://www.cbs.gov.il/
as_of: 2026-10-13
review_by: 2027-04-13
verification: 1
verified_by: null
---
Explanation, exceptions and how agents should use the rule.
```

A rule card without `source` and `as_of` is invalid and is ignored with a warning.

---

## 5. Verification

| Level | Name | Set when |
|---|---|---|
| 0 | General knowledge | No market pack for the project's market. Agents may answer from model knowledge, and the answer is labelled "unverified, no market pack". |
| 1 | Drafted | An agent or person drafted the card with a source and a date. |
| 2 | Reviewed | A named local professional approved it (`verified_by`, `reviewed_at`). |
| 3 | Maintained | A partner owns the pack and every card has an unexpired `review_by`. |
| 4 | Field-proven | The pack was used in a paid engagement and a value-report number exists. |

- A card's effective level is the lowest of its own level and the pack's level.
- An expired `review_by` drops a card to level 1 until it is reviewed again.
- Raising a pack to level 2 or higher is a governed action (`pack_verify`) that goes through the approval queue and the audit log.

---

## 6. MCP surface

New read tools, available when the `kb` family is on:

- `list_packs(venture)` lists enabled packs with versions and verification levels.
- `resolve(venture, item_type, key)` returns a `Resolved` record.
- `glossary_lookup(venture, term)` returns the family, kind and layer.

Writes such as enabling a pack or verifying one are `ops` tools and go through `ToolGate` (STORY-16).

---

## 7. Migration from templates

- `templates/real-estate-developer/` (STORY-20) splits in two:
  - `packs/profession/developer/` gets the agents, the three skills, payment-claim and tender schemas, and the measures.
  - `packs/market/il/` gets Hebrew terms, ILS, index linkage, standard form 3210 references and the work week.
  - Content that's both firm-specific and demo-only stays in the demo venture.
- `scaffold_venture(template=...)` keeps accepting template names. A template that maps to packs writes `packs.yaml` and copies only firm-layer starter files.
- Ventures created before the flag keep their copied files, which count as the firm layer. Nothing is deleted.

---

## 8. Acceptance (v0.1 as a whole)

- The nine core schemas exist and validate the demo venture's entities with warnings only.
- With `features.packs=true`, a venture with `developer` + `il` resolves the payment-claim glossary term, a rule card, a document template and a trust default, each with the right layer.
- Switching `il` for a drafted `pt` pack changes terms, currency and rules with no code change (STORY-45).
- With the flag off, the full test suite passes unchanged.

---

## 9. Decisions on the open questions (2026-10-13)

1. **Party·Role extends `contact.json`.** One record per person or company, with `roles[]` per project (`{project, role, from, to}`). A second person type would split the address book and duplicate contacts across projects. The same company can then be a contractor on one project and a supplier on another.
2. **Firm overrides live in the venture's FABRIC, at `F-foundations/overrides/`,** with `packs.yaml` at the venture root. The firm layer stays file-based and inside the folder the client owns and exports (portability, filter 7). Overrides mirror the pack layout (`glossary/`, `rules/`, `documents/`, `trust.yaml`), and a firm can `disable: [rule ids]`.
3. **Each pack has its own semver, plus `requires.core`.** Ventures pin an exact pack version. Upgrades are explicit: the change list is shown and confirmed through an approval, and nothing updates silently.
   - **Major:** removes or retypes fields, or removes rule cards.
   - **Minor:** adds terms, rules, skills or templates.
   - **Patch:** fixes wording or sources.

   Every rule-card change is recorded in the pack's `CHANGELOG.md`.
4. **Who raises verification levels:**
   - **Level 2:** any named professional licensed or practising in that market, through the `pack_verify` approval. Their name and date are stored on each card.
   - **Level 3:** only an organisation with a signed maintenance agreement (a partner), granted by the owner. It is that organisation that stays accountable for review dates.
   - **Level 4:** set automatically from a paid engagement's value report.
   - **Lowering:** levels drop automatically when `review_by` expires.
