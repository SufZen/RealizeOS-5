# FABRIC Entity Schemas — Top 5 — v0.1

> JSON Schemas for the five most-used entity types in FABRIC. Soft validation policy: schemas validate on save with **warnings, never errors**. Unknown fields allowed. The indexer reads schemas to know expected shape; FABRIC never refuses non-conforming content.
>
> Target location: `docs/fabric-schemas/<type>.json` (one file per schema)  
> Schema dialect: JSON Schema Draft 2020-12  
> Status: Draft v0.1  
> License: MIT

---

## Overview & Conventions

### Why Soft Schemas

A personal AI OS that refuses your knowledge because a field is missing is broken. These schemas exist to:

1. Give agents reliable expectations of entity shape
2. Power the Workspace UI's typed forms and views
3. Surface anomalies as Curator hygiene proposals
4. Enable graph queries that filter on structured fields

But they are not gatekeepers. Validation produces warnings logged to `I-insights/_validation.md`, not failures.

### Common Fields All Entities Inherit

Every FABRIC entity, regardless of type, has these fields available (none required at the type level):

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable immutable ID; format `<type-prefix>-<yyyy-mm>-<slug>-<seq>` |
| `type` | string | Canonical type name |
| `title` | string | Human-readable title |
| `slug` | string | URL-safe identifier (changeable, unlike `id`) |
| `venture` | string | Venture key (e.g., `realizeos`, `burtucala`); `_brand` for global |
| `tags` | array[string] | Free-form tags from frontmatter or inline |
| `source` | string | `manual` \| `agent-generated` \| `imported` \| `dreaming` |
| `created_at` | string | ISO 8601 datetime |
| `created_by` | string | Actor ID (`user-<name>` or `agent-<name>` or `dream-<cycle>`) |
| `last_modified_at` | string | ISO 8601 datetime |
| `last_modified_by` | string | Actor ID |
| `confidence` | number | 0.0–1.0; agent-generated content; users implicitly 1.0 |
| `verified` | boolean | Has a human reviewed this? |
| `verified_by` | string | User ID who verified |
| `last_verified_at` | string | ISO 8601 datetime |

Type-specific schemas below add to or constrain these.

### Indexing Semantics Per Schema

Each schema includes a non-standard `x-indexing` extension describing how Synapse processes the entity:

```yaml
x-indexing:
  l1: <what goes into the hot TOC>
  l2: <how it's chunked/embedded for search>
  graph_relations: <which fields create graph edges>
  dreaming_relevance: <which cycles attend to this type>
```

This is metadata for our system, not standard JSON Schema; the indexer reads it.

---

## 1. Decision Schema

### `decision.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://realizeos.ai/schemas/v0.1/decision.json",
  "title": "Decision",
  "description": "A committed (or proposed/deferred/reversed) choice with rationale, impacts, and follow-ups. The most carefully-tracked entity type; committed decisions are hard-deny-listed from Dreaming auto-modification.",
  "type": "object",

  "properties": {
    "id": {
      "type": "string",
      "pattern": "^dec-\\d{4}-\\d{2}-[a-z0-9-]+(-\\d+)?$",
      "description": "Stable ID, format: dec-YYYY-MM-slug-NN"
    },
    "type": { "const": "decision" },
    "title": {
      "type": "string",
      "minLength": 3,
      "description": "Short human-readable decision title"
    },
    "status": {
      "type": "string",
      "enum": ["proposed", "committed", "deferred", "reversed"],
      "description": "Lifecycle state of the decision"
    },
    "date": {
      "type": "string",
      "format": "date",
      "description": "Date the decision was made (or proposed)"
    },
    "reviewers": {
      "type": "array",
      "items": { "type": "string", "pattern": "^(contact-|brand:)" },
      "description": "Contact references for people involved in the decision"
    },
    "ventures": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Venture keys this decision applies to"
    },
    "supersedes": {
      "type": "string",
      "pattern": "^dec-",
      "description": "ID of a prior decision this replaces"
    },
    "superseded_by": {
      "type": "string",
      "pattern": "^dec-",
      "description": "ID of a later decision that replaced this one (auto-populated on reversal)"
    },
    "rationale": {
      "type": "string",
      "description": "Markdown explaining why this decision was made"
    },
    "impacts": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "scope": { "type": "string" },
          "description": { "type": "string" }
        }
      },
      "description": "What this decision changes, per scope"
    },
    "followups": {
      "type": "array",
      "items": { "type": "string", "pattern": "^action-" },
      "description": "Action IDs that follow from this decision"
    },
    "related_risks": {
      "type": "array",
      "items": { "type": "string", "pattern": "^risk-" }
    }
  },

  "required": ["type", "title", "status", "date"],
  "additionalProperties": true,

  "x-indexing": {
    "l1": ["id", "title", "status", "date", "ventures"],
    "l2": "Title + rationale + impacts as searchable chunks",
    "graph_relations": ["reviewers (→ contact)", "supersedes (→ decision)", "followups (→ action)", "related_risks (→ risk)"],
    "dreaming_relevance": "Committed decisions are hard-deny-listed; reversed/deferred decisions feed Genesis drift analysis"
  },

  "examples": [
    {
      "id": "dec-2026-05-pricing-001",
      "type": "decision",
      "title": "RealizeOS pricing model: setup-plus-maintenance",
      "status": "committed",
      "date": "2026-05-20",
      "reviewers": ["contact-meirav", "brand:miguel"],
      "ventures": ["realizeos"],
      "rationale": "Avoids per-seat SaaS dynamics. Aligns with BSL 1.1 self-hosted positioning. Maintains recurring revenue without lock-in friction.",
      "impacts": [
        { "scope": "burtucala", "description": "Lead funnel reframing" },
        { "scope": "realizeos", "description": "F&F launch webinar messaging update" }
      ],
      "followups": ["action-update-pricing-page", "action-brief-meirav-miguel"],
      "venture": "realizeos",
      "source": "manual",
      "created_by": "user-asaf",
      "confidence": 1.0,
      "verified": true
    }
  ]
}
```

---

## 2. Mission Schema

### `mission.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://realizeos.ai/schemas/v0.1/mission.json",
  "title": "Mission",
  "description": "A goal-oriented work unit executed by one or more agent runtimes. Central to the Mission Engine; tracked in Synapse L4 throughout its lifecycle.",
  "type": "object",

  "properties": {
    "id": {
      "type": "string",
      "pattern": "^m-\\d{4}-\\d{2}-\\d{2}-[a-z0-9-]+(-\\d+)?$",
      "description": "Stable ID, format: m-YYYY-MM-DD-slug-NN"
    },
    "type": { "const": "mission" },
    "title": { "type": "string", "minLength": 3 },
    "goal": {
      "type": "string",
      "minLength": 10,
      "description": "Plain-text statement of what the mission should accomplish"
    },
    "owner": {
      "type": "string",
      "pattern": "^(contact-|user-|brand:)",
      "description": "Who owns this mission (typically a user or contact)"
    },
    "state": {
      "type": "string",
      "enum": ["proposed", "planned", "in-progress", "paused", "awaiting-approval", "completed", "failed", "cancelled"],
      "description": "Lifecycle state"
    },
    "venture": {
      "type": "string",
      "description": "Venture key this mission belongs to"
    },
    "constraints": {
      "type": "object",
      "properties": {
        "budget_eur": { "type": "number", "minimum": 0 },
        "deadline": { "type": "string", "format": "date-time" },
        "max_duration_sec": { "type": "integer", "minimum": 0 },
        "requires_approval_for": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Categories of action requiring human approval mid-flight"
        },
        "deny_actions": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "plan": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "step_id": { "type": "string" },
          "runtime": {
            "type": "string",
            "description": "Runtime ID that executes this step"
          },
          "agent": {
            "type": "string",
            "description": "Agent name if invoking a specific agent within the runtime"
          },
          "action": { "type": "string" },
          "args": { "type": "object" },
          "inputs_from": {
            "type": "array",
            "items": { "type": "string" },
            "description": "Step IDs whose outputs feed this step"
          },
          "expected_output_schema": { "type": "object" },
          "status": {
            "type": "string",
            "enum": ["pending", "in-progress", "succeeded", "failed", "skipped"]
          },
          "started_at": { "type": "string", "format": "date-time" },
          "completed_at": { "type": "string", "format": "date-time" }
        },
        "required": ["step_id", "runtime", "action"]
      }
    },
    "cost_consumed_eur": {
      "type": "number",
      "minimum": 0,
      "description": "Running total of monetary cost (updated as steps complete)"
    },
    "cost_consumed_tokens": {
      "type": "integer",
      "minimum": 0
    },
    "started_at": { "type": "string", "format": "date-time" },
    "completed_at": { "type": "string", "format": "date-time" },
    "outcome_summary": {
      "type": "string",
      "description": "Brief summary of mission outcome (populated by Reflex cycle)"
    },
    "related_decisions": {
      "type": "array",
      "items": { "type": "string", "pattern": "^dec-" }
    },
    "produced_entities": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Entity IDs created or modified by this mission"
    }
  },

  "required": ["type", "title", "goal", "state", "venture"],
  "additionalProperties": true,

  "x-indexing": {
    "l1": ["id", "title", "goal", "state", "venture", "owner", "outcome_summary"],
    "l2": "Goal + plan step descriptions + outcome_summary as searchable chunks",
    "graph_relations": ["owner (→ contact)", "related_decisions (→ decision)", "produced_entities (→ any)"],
    "l4_special": "Active missions get their own L4 entry with continuously-updated compressed state",
    "dreaming_relevance": "Reflex cycle writes outcome_summary on completion; Synthesis cycle aggregates patterns across missions"
  },

  "examples": [
    {
      "id": "m-2026-05-20-001",
      "type": "mission",
      "title": "Find distressed Setúbal properties",
      "goal": "Find 3 distressed inheritance properties in Setúbal under €150k with verified heir contact",
      "owner": "user-asaf",
      "state": "in-progress",
      "venture": "burtucala",
      "constraints": {
        "budget_eur": 5.0,
        "deadline": "2026-05-22T18:00:00Z",
        "requires_approval_for": ["external_send", "financial_commitment"]
      },
      "plan": [
        {
          "step_id": "s1",
          "runtime": "internal",
          "agent": "maria",
          "action": "search.real_estate",
          "args": { "region": "Setúbal", "max_price": 150000, "status": "distressed" },
          "status": "succeeded",
          "started_at": "2026-05-20T10:00:00Z",
          "completed_at": "2026-05-20T10:03:45Z"
        },
        {
          "step_id": "s2",
          "runtime": "internal",
          "agent": "maria",
          "action": "enrich.heir_contacts",
          "inputs_from": ["s1"],
          "status": "in-progress",
          "started_at": "2026-05-20T10:03:50Z"
        }
      ],
      "cost_consumed_eur": 0.34,
      "started_at": "2026-05-20T10:00:00Z",
      "source": "manual",
      "created_by": "user-asaf"
    }
  ]
}
```

---

## 3. Contact Schema

### `contact.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://realizeos.ai/schemas/v0.1/contact.json",
  "title": "Contact",
  "description": "A person reference. The most-linked-to entity type in FABRIC. Lives at venture level or brand level (in _brand/contacts/) for cross-venture sharing.",
  "type": "object",

  "properties": {
    "id": {
      "type": "string",
      "pattern": "^contact-[a-z0-9-]+$",
      "description": "Stable ID, format: contact-slug"
    },
    "type": { "const": "contact" },
    "name": {
      "type": "string",
      "minLength": 1,
      "description": "Display name (full name or how you refer to them)"
    },
    "preferred_name": {
      "type": "string",
      "description": "If different from name (e.g., first name only)"
    },
    "email": {
      "type": "array",
      "items": { "type": "string", "format": "email" },
      "description": "Email addresses; first is primary"
    },
    "phone": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Phone numbers in E.164 format preferred"
    },
    "social": {
      "type": "object",
      "additionalProperties": { "type": "string" },
      "description": "Social handles, e.g. {linkedin: 'url', x: 'handle'}"
    },
    "roles": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "role": { "type": "string" },
          "since": { "type": "string", "format": "date" },
          "until": { "type": "string", "format": "date" }
        }
      },
      "description": "Roles by scope; key is venture-key or '_brand'. Example: {realization: {role: 'strategic-partner', since: '2025-01-15'}}"
    },
    "languages": {
      "type": "array",
      "items": { "type": "string", "pattern": "^[a-z]{2}(-[A-Z]{2})?$" },
      "description": "ISO 639-1 codes, optional with region. Used by agents to choose communication language."
    },
    "timezone": {
      "type": "string",
      "description": "IANA timezone name, e.g. Europe/Lisbon"
    },
    "notes": {
      "type": "string",
      "description": "Markdown notes about this contact"
    },
    "tags": {
      "type": "array",
      "items": { "type": "string" }
    },
    "relationship": {
      "type": "string",
      "description": "How you know this person (e.g., 'partner', 'client', 'family')"
    },
    "last_interaction_at": {
      "type": "string",
      "format": "date-time",
      "description": "Most recent meaningful interaction (auto-updated by Curator if event log has interactions)"
    },
    "trust_score": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Optional reliability/trust signal derived from commitment kept/broken history"
    },
    "avoid_topics": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Topics agents should not bring up with this person"
    }
  },

  "required": ["type", "name"],
  "additionalProperties": true,

  "x-indexing": {
    "l1": ["id", "name", "preferred_name", "roles", "languages", "last_interaction_at"],
    "l2": "Name + notes + roles as searchable text",
    "graph_relations": "Reverse refs from all entities pointing to this contact",
    "dreaming_relevance": "Curator updates last_interaction_at from event log; tracks commitment kept/broken history into trust_score"
  },

  "examples": [
    {
      "id": "contact-meirav",
      "type": "contact",
      "name": "Meirav Levi",
      "preferred_name": "Meirav",
      "email": ["meirav@example.com"],
      "social": { "linkedin": "https://linkedin.com/in/meirav-example" },
      "roles": {
        "realization": { "role": "strategic-partner", "since": "2025-06-01" },
        "_brand": { "role": "strategic-partner" }
      },
      "languages": ["he", "en"],
      "timezone": "Asia/Jerusalem",
      "relationship": "strategic-partner",
      "tags": ["mioliving", "italy-hotels"],
      "venture": "_brand",
      "source": "manual",
      "created_by": "user-asaf",
      "confidence": 1.0,
      "verified": true
    }
  ]
}
```

---

## 4. Commitment Schema

### `commitment.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://realizeos.ai/schemas/v0.1/commitment.json",
  "title": "Commitment",
  "description": "A promise made — by you, to you, by others, or to others. The accountability primitive. Open commitments surface in the daily Curator review; status transitions feed contact trust scoring.",
  "type": "object",

  "properties": {
    "id": {
      "type": "string",
      "pattern": "^commitment-\\d{4}-\\d{2}-[a-z0-9-]+(-\\d+)?$"
    },
    "type": { "const": "commitment" },
    "title": { "type": "string", "minLength": 3 },
    "what": {
      "type": "string",
      "minLength": 5,
      "description": "What was committed to"
    },
    "by": {
      "type": "string",
      "pattern": "^(contact-|user-|brand:)",
      "description": "Who's making the commitment"
    },
    "to": {
      "type": "string",
      "pattern": "^(contact-|user-|brand:)",
      "description": "Who the commitment is to"
    },
    "deadline": {
      "type": "string",
      "oneOf": [
        { "format": "date" },
        { "format": "date-time" }
      ],
      "description": "When this commitment is due"
    },
    "status": {
      "type": "string",
      "enum": ["open", "in-progress", "kept", "broken", "renegotiated", "cancelled"],
      "default": "open"
    },
    "priority": {
      "type": "string",
      "enum": ["low", "medium", "high", "critical"]
    },
    "related_decision": {
      "type": "string",
      "pattern": "^dec-"
    },
    "related_mission": {
      "type": "string",
      "pattern": "^m-"
    },
    "kept_at": {
      "type": "string",
      "format": "date-time",
      "description": "When marked as kept"
    },
    "broken_at": {
      "type": "string",
      "format": "date-time"
    },
    "broken_reason": {
      "type": "string"
    },
    "renegotiated_to": {
      "type": "string",
      "pattern": "^commitment-",
      "description": "ID of the new commitment that replaces this one"
    },
    "evidence": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Entity refs or URLs that prove the commitment was kept"
    }
  },

  "required": ["type", "what", "by", "to", "deadline"],
  "additionalProperties": true,

  "x-indexing": {
    "l1": ["id", "title", "what", "by", "to", "deadline", "status", "priority"],
    "l2": "what + broken_reason as searchable text",
    "graph_relations": ["by (→ contact)", "to (→ contact)", "related_decision (→ decision)", "related_mission (→ mission)", "renegotiated_to (→ commitment)"],
    "dreaming_relevance": "Open commitments past deadline surface in Curator; broken commitments contribute (negatively) to contact trust_score; pattern of renegotiation surfaces in Synthesis"
  },

  "examples": [
    {
      "id": "commitment-2026-05-pricing-rationale-001",
      "type": "commitment",
      "title": "Send Meirav pricing rationale",
      "what": "Send Meirav the finalized pricing rationale document for board review",
      "by": "user-asaf",
      "to": "contact-meirav",
      "deadline": "2026-05-25",
      "status": "in-progress",
      "priority": "high",
      "related_decision": "dec-2026-05-pricing-001",
      "venture": "realizeos",
      "source": "manual",
      "created_by": "user-asaf",
      "confidence": 1.0,
      "verified": true
    }
  ]
}
```

---

## 5. Insight Schema

### `insight.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://realizeos.ai/schemas/v0.1/insight.json",
  "title": "Insight",
  "description": "A learning, observation, pattern, or hypothesis worth preserving. The primary output of the Dreaming cycles. Used by agents for cross-venture pattern matching.",
  "type": "object",

  "properties": {
    "id": {
      "type": "string",
      "pattern": "^insight-\\d{4}-\\d{2}-[a-z0-9-]+(-\\d+)?$"
    },
    "type": { "const": "insight" },
    "title": { "type": "string", "minLength": 3 },
    "summary": {
      "type": "string",
      "minLength": 10,
      "description": "One- or two-sentence statement of the insight"
    },
    "details": {
      "type": "string",
      "description": "Markdown elaboration with evidence and context"
    },
    "kind": {
      "type": "string",
      "enum": ["observation", "learning", "pattern", "hypothesis"],
      "description": "observation: noticed something true; learning: lesson from experience; pattern: recurring structure; hypothesis: candidate explanation, needs validation"
    },
    "applies_to": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Ventures or domains this insight applies to"
    },
    "source_kind": {
      "type": "string",
      "enum": ["manual", "mission", "dream-reflex", "dream-curator", "dream-synthesis", "dream-genesis", "external"],
      "description": "Where this insight originated"
    },
    "source_mission": {
      "type": "string",
      "pattern": "^m-"
    },
    "source_dream_cycle": {
      "type": "string",
      "description": "Dream cycle ID if dreaming-derived"
    },
    "source_references": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Entity refs or URLs supporting this insight"
    },
    "validated": {
      "type": "boolean",
      "description": "Has this insight been validated against evidence?"
    },
    "validated_at": {
      "type": "string",
      "format": "date-time"
    },
    "validated_by": {
      "type": "string"
    },
    "invalidated_at": {
      "type": "string",
      "format": "date-time"
    },
    "invalidation_reason": {
      "type": "string"
    },
    "actionable": {
      "type": "boolean",
      "description": "Does this insight imply a specific action?"
    },
    "related_actions": {
      "type": "array",
      "items": { "type": "string", "pattern": "^action-" }
    },
    "supersedes": {
      "type": "string",
      "pattern": "^insight-"
    }
  },

  "required": ["type", "summary", "kind"],
  "additionalProperties": true,

  "x-indexing": {
    "l1": ["id", "title", "summary", "kind", "applies_to", "validated"],
    "l2": "Summary + details as searchable chunks; embeddings used heavily by Synthesis cycle",
    "graph_relations": ["source_mission (→ mission)", "source_references (→ any)", "related_actions (→ action)", "supersedes (→ insight)"],
    "dreaming_relevance": "PRIMARY OUTPUT TYPE. Hypotheses with validated=false older than 90 days flagged for Genesis review. Patterns aggregate into workflow extraction proposals. Insights from one venture surface in others via applies_to."
  },

  "examples": [
    {
      "id": "insight-2026-05-funnel-pattern-001",
      "type": "insight",
      "title": "International leads convert higher but slower",
      "summary": "Leads arriving via the international content funnel convert at ~3× the rate of domestic leads but require ~2× the touchpoints before closing.",
      "details": "Analysis of 47 closed Burtucala leads over Q1 2026:\n- Domestic (PT) lead → close: average 2.3 touchpoints, 18% close rate\n- International (EN content) lead → close: average 4.7 touchpoints, 54% close rate\n\nWorking hypothesis: international leads are more researched at first contact and more financially committed once engaged, but the trust-building cycle is longer due to remote-relationship dynamics.",
      "kind": "pattern",
      "applies_to": ["burtucala", "realization"],
      "source_kind": "dream-curator",
      "source_dream_cycle": "curator-2026-05-19-001",
      "source_references": ["m-2026-05-15-funnel-analysis-001"],
      "validated": true,
      "validated_at": "2026-05-19T08:30:00Z",
      "validated_by": "user-asaf",
      "actionable": true,
      "related_actions": ["action-extend-international-nurture-sequence"],
      "venture": "burtucala",
      "source": "agent-generated",
      "created_by": "dream-curator",
      "confidence": 0.78,
      "verified": true
    }
  ]
}
```

---

## 6. Cross-Schema Notes

### Reference Conventions

When one schema points at another:
- Entity IDs follow the prefix conventions in each schema's `pattern`
- Cross-venture refs use `<scope>:<id>` form (e.g., `brand:meirav`)
- Broken refs (target doesn't exist) flagged by validation loop but don't fail the schema

### Schema Versioning

- Each schema has `$id` with `/v0.1/`
- Breaking changes bump to `/v0.2/` and require migration
- Backwards-compatible additions just add fields; entities authored against v0.1 remain valid

### Where Schemas Are Stored

In the repo:
```
docs/fabric-schemas/
├── decision.json
├── mission.json
├── contact.json
├── commitment.json
├── insight.json
├── _common.json        # shared fields referenced via $ref
└── README.md           # this document, rendered
```

### How Schemas Are Discovered

The Synapse indexer scans `docs/fabric-schemas/` at startup, builds an in-memory schema registry, and applies the appropriate schema based on each entity's `type` field. Unknown types are indexed without schema validation.

### Validation Output

All warnings collected into `I-insights/_validation.md` per venture. Format:

```markdown
# FABRIC Validation Report
*Generated by Synapse indexer*

## Warnings

### dec-2026-04-old-decision-001
- Missing required field: `status`
- Suggested: add `status: "committed"` based on file context

### contact-orphan
- 0 inbound references (orphan candidate)
- Consider: delete, merge into another contact, or add reference
```

User reviews at their own pace; can `realize-os fabric lint` interactively.

---

## 7. Open Questions

1. **Should the common fields (id, type, source, created_by, etc.) be a separate referenceable `$ref` schema (`_common.json`) that each type extends?** Recommendation: yes, factor out in v0.2 once we have ~5–10 schemas and the duplication is visible.

2. **Decision `impacts` shape** — currently an array of `{scope, description}` objects. Should it instead reference impacted entities directly? Recommendation: keep free-form for now; promote to structured refs when usage shows clear patterns.

3. **Mission `plan` granularity** — should plans be hierarchical (steps containing sub-steps) or always flat? Recommendation: flat in v0.1; sub-steps express via separate child missions linked by `parent_mission`.

4. **Contact `trust_score` mechanics** — auto-computed by Dreaming from commitment history, or manually maintainable, or both? Recommendation: both; auto-computed default with manual override that takes precedence.

5. **Insight `confidence` vs `validated`** — overlapping signals. Recommendation: `confidence` is the system's belief (0.0–1.0); `validated` is human confirmation (boolean). Both meaningful, both kept.

6. **Should we add `risk.json`, `action.json`, and `deadline.json` to the top tier now?** Recommendation: yes for v0.2; v0.1 starts narrow with these five to learn validation patterns before expanding.

7. **Schema overrides per venture** — can `realization` venture extend the `contact` schema with real-estate-specific fields like `license_number`? Recommendation: yes via `docs/fabric-schemas/<venture>/<type>.json` overlay files; merged at indexing time.

---

*End of FABRIC Entity Schemas v0.1*
