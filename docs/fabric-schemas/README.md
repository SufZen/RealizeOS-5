# FABRIC schemas

Soft JSON Schemas (Draft 2020-12) for FABRIC entities. They produce warnings and never refuse content (spec 002). The validator is `realize_core/fabric/validator.py`.

## Core language (spec 010)

These nine families are the shared language every profession pack, market pack and agent uses.

| Family | File | Example kinds |
|---|---|---|
| Project · Site | `project.json` | `development`, `renovation`, `acquisition`, `design_commission` |
| Party · Role | `contact.json` (`project_roles`) | client, contractor, supplier, lender, tenant, authority, investor |
| Document · Source | `source.json` | `contract`, `drawing`, `message`, `voice_note`, `quote`, `minutes` |
| Requirement | `requirement.json` | `tender_item`, `code_rule`, `covenant`, `brief_line` |
| Money event | `money-event.json` | `budget_line`, `quote`, `payment_claim`, `invoice`, `capital_call` |
| Milestone | `milestone.json` | `construction_stage`, `design_stage`, `permit`, `handover` |
| Change | `change.json` | `client_change`, `variation`, `design_revision` |
| Decision · Approval | `decision.json` (`approval_id`, `basis`, `affects`) | `commercial`, `technical`, `payment`, `scope` |
| Issue · Risk | `issue.json` | `defect`, `delay`, `discrepancy`, `compliance` |

Rules:

- Families that involve money or obligations carry `sources[]`, where each entry is `{source, locator}`.
- Amounts always come with a `currency` (ISO 4217).
- `kind` is an open string. Packs may add kinds of their own.

## Extending a family in a pack

A pack schema references a core family with `allOf` and adds its own fields:

```json
{
  "allOf": [{ "$ref": "https://realizeos.ai/schemas/v0.1/money-event.json" }],
  "properties": { "kind": { "const": "payment_claim" }, "retention_percent": { "type": "number" } }
}
```

`$ref` may be the `$id`, the file name (`money-event.json`) or the type name. `SchemaRegistry.register()` adds the schema and returns problems, for example when an extension retypes a core property.

## Other entity types (spec 002)

`decision`, `mission`, `contact`, `commitment`, `insight`.
