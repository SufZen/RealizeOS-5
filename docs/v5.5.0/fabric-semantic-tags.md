# FABRIC Semantic Tag Vocabulary — v0.1

> Canonical XML-style tags that live inside markdown FABRIC content. Combines markdown's human-friendly readability with structured data the indexer extracts as first-class entities and relations.
>
> Target location: `docs/fabric-semantic-tags.md`  
> Status: Draft v0.1 — starter vocabulary, designed to grow via the dreaming Synthesis cycle  
> License: MIT

---

## 1. Why Semantic Tags

Plain markdown is excellent for humans and tokens but ambiguous for agents. A line that reads *"We decided in May to use a setup-plus-maintenance pricing model"* is a decision, but the indexer has no structured handle on it.

HTML solves this but costs ~3× the tokens and breaks readability and git-diffability.

Semantic XML tags inside markdown thread the needle: ~10–20% token overhead vs plain markdown, dramatically more precise retrieval and reasoning, fully readable by humans, indexed as first-class entities by Synapse.

Anthropic's own prompt-engineering guidance has long favored XML tags for structure in long contexts. We extend that practice from prompts into knowledge storage.

---

## 2. General Syntax Rules

### 2.1 Basic Form

```markdown
<tagname attr1="value" attr2="value">
content (markdown supported inside)
</tagname>
```

### 2.2 Self-Closing

For tags that are pure pointers without content body:

```markdown
<contact ref="contact-meirav" />
```

### 2.3 Required vs Optional Attributes

Each tag declares its required and optional attributes. The indexer warns (not errors) on missing required attributes.

### 2.4 Nesting

Tags can nest. Inner tags are indexed both standalone and as part of their parent's context:

```markdown
<decision status="committed" date="2026-05-20">
Use setup-plus-maintenance pricing.

<rationale>
Avoids per-seat SaaS dynamics.
</rationale>

<impacts ventures="burtucala,realization">
Lead funnel reframing.
</impacts>
</decision>
```

`<rationale>` and `<impacts>` are indexed as children of the parent decision and queryable via the graph.

### 2.5 Attributes vs Content

Use **attributes** for structured machine-readable fields (dates, references, statuses, enums). Use **content** for free-form human-readable text. When in doubt: would the agent want to filter on this? → attribute. Is this a paragraph? → content.

### 2.6 Value Conventions

| Attribute kind | Format |
|---|---|
| Dates | ISO 8601 (`2026-05-20` or `2026-05-20T15:30:00Z`) |
| Entity refs | `<type>-<...>` (e.g., `contact-meirav`, `dec-2026-05-pricing-001`) |
| Cross-venture refs | `<scope>:<id>` (e.g., `brand:meirav`, `realization:lead-001`) |
| Lists | comma-separated, no spaces around commas: `ventures="a,b,c"` |
| Booleans | `true` / `false` |
| Numbers | bare numerals, no quotes preferred (`confidence=0.85`) |
| Enums | lowercase with hyphens (`status="in-progress"`) |

### 2.7 Whitespace

Inner content is markdown-rendered. Leading/trailing whitespace inside tags is trimmed by the indexer.

### 2.8 Escaping

If literal `<` is needed inside content, use `\<` (markdown-style escape) or HTML entity `&lt;`. The indexer respects both.

---

## 3. The 13 Canonical Tags (v0.1 Vocabulary)

### 3.1 `<decision>`

**Purpose:** A committed (or proposed/deferred/reversed) choice with rationale and impacts.

**Required attributes:**
- `status` — enum: `proposed` | `committed` | `deferred` | `reversed`
- `date` — ISO 8601 date

**Optional attributes:**
- `id` — stable ID; if omitted, indexer generates one and writes it back
- `reviewers` — comma-separated contact refs
- `ventures` — comma-separated venture keys this decision applies to
- `supersedes` — entity ref of a prior decision this replaces
- `confidence` — 0.0–1.0 (for proposed decisions)

**Content:** The decision text, with optional `<rationale>` and `<impacts>` and `<followups>` children.

**Indexing semantics:**
- Becomes an entity of type `decision` in Synapse L1
- `reviewers`, `ventures`, `supersedes` become refs in the graph
- The decision is queryable via `synapse.by_type("decision", filters={status:"committed"})`
- Committed decisions are never auto-modified by Dreaming (hard deny-list)

**Example:**

```markdown
<decision id="dec-2026-05-pricing-001" status="committed" date="2026-05-20"
          reviewers="contact-meirav,contact-miguel" ventures="realizeos">
Use setup-plus-maintenance pricing model. €X setup, €Y/month.

<rationale>
Avoids per-seat SaaS commitments while still providing recurring revenue.
Aligns with BSL 1.1 self-hosted positioning.
</rationale>

<impacts ventures="burtucala,arena-habitat">
- Lead funnel reframing on Burtucala
- F&F launch webinar messaging update
</impacts>

<followups>
- <action ref="action-update-pricing-page" />
- <action ref="action-brief-meirav-miguel" />
</followups>
</decision>
```

---

### 3.2 `<commitment>`

**Purpose:** A promise made — by you, to you, by others, or to others. The accountability primitive.

**Required attributes:**
- `by` — entity ref of who's committing (`contact-asaf`, `contact-meirav`, etc.)
- `to` — entity ref of who the commitment is to
- `deadline` — ISO 8601 date or datetime

**Optional attributes:**
- `id`
- `status` — enum: `open` | `in-progress` | `kept` | `broken` | `renegotiated` (default `open`)
- `related-decision` — entity ref
- `related-mission` — entity ref
- `priority` — enum: `low` | `medium` | `high` | `critical`

**Content:** What was committed to.

**Indexing semantics:**
- Becomes entity of type `commitment`
- Tracked in the Dreaming Curator's "open commitments" view
- Overdue open commitments surface as proposals to follow up
- Closed loop: `kept` and `broken` feed reliability scoring per contact

**Example:**

```markdown
<commitment by="contact-asaf" to="contact-meirav" deadline="2026-05-25"
            related-decision="dec-2026-05-pricing-001" priority="high">
Send Meirav the finalized pricing rationale for board review.
</commitment>
```

---

### 3.3 `<deadline>`

**Purpose:** A time-bound obligation, lighter weight than a full commitment. Use when you just need to flag "this has to be done by X" without a full who-promised-to-whom structure.

**Required attributes:**
- `when` — ISO 8601 date or datetime

**Optional attributes:**
- `for` — what the deadline is for (free text or entity ref)
- `owner` — contact ref
- `status` — enum: `pending` | `met` | `missed` | `pushed`

**Content:** Description.

**Indexing semantics:**
- Becomes entity of type `deadline`
- Surfaces in upcoming-deadlines view
- Missed deadlines flag as Curator hygiene proposals

**Example:**

```markdown
<deadline when="2026-06-15" owner="contact-asaf" for="dec-2026-05-pricing-001">
Publish updated pricing page on realization.co.il.
</deadline>
```

---

### 3.4 `<action>`

**Purpose:** A next-step action item. Lighter than a commitment (no explicit promiser/promisee), heavier than a TODO checkbox.

**Required attributes:** none

**Optional attributes:**
- `id`
- `owner` — contact ref (default: current user)
- `due` — ISO 8601 date
- `status` — enum: `todo` | `in-progress` | `done` | `cancelled`
- `priority` — enum: `low` | `medium` | `high` | `critical`
- `related-decision` / `related-mission` — entity refs

**Content:** What to do.

**Indexing semantics:**
- Becomes entity of type `action`
- Surfaces in the Workspace UI's action list, per venture
- `done` actions are archived after 30 days
- Open actions overdue by N days trigger Curator nudges

**Example:**

```markdown
<action owner="contact-asaf" due="2026-05-22" status="in-progress" priority="high">
Draft the Runtime Adapter Contract v0.1 spec.
</action>
```

---

### 3.5 `<risk>`

**Purpose:** A potential future negative event with mitigation. Distinct from `<blocker>` which is current.

**Required attributes:**
- `level` — enum: `low` | `medium` | `high` | `critical`
- `status` — enum: `identified` | `monitored` | `mitigating` | `materialized` | `closed`

**Optional attributes:**
- `id`
- `likelihood` — 0.0–1.0
- `impact` — free text
- `owner` — contact ref
- `ventures` — comma-separated

**Content:** Risk description, including `<mitigation>` child if relevant.

**Indexing semantics:**
- Becomes entity of type `risk`
- High/critical risks surface in the Workspace UI's risk panel
- Materialized risks trigger Curator proposals to extract learnings

**Example:**

```markdown
<risk level="high" status="monitored" likelihood="0.4" owner="contact-asaf"
      ventures="realizeos">
The Hermes Agent Runtime Adapter could become brittle if Hermes ships breaking
API changes faster than we can adapt.

<mitigation>
Pin Hermes minor version; subscribe to release notes; test adapter in CI on every Hermes release.
</mitigation>
</risk>
```

---

### 3.6 `<blocker>`

**Purpose:** A current obstacle preventing progress. Action-oriented; resolved or not.

**Required attributes:**
- `status` — enum: `active` | `resolved`

**Optional attributes:**
- `id`
- `blocks` — entity ref of what's blocked (mission, action, deliverable)
- `owner` — contact ref of who can resolve

**Content:** Description.

**Indexing semantics:**
- Becomes entity of type `blocker`
- Active blockers surface prominently in mission detail views
- Resolution latency tracked as a quality signal

**Example:**

```markdown
<blocker status="active" blocks="m-2026-05-20-001" owner="contact-meirav">
Awaiting Meirav's review of the pricing rationale doc before we can publish.
</blocker>
```

---

### 3.7 `<insight>`

**Purpose:** A learning, observation, pattern, or hypothesis worth preserving. The output of reflection.

**Required attributes:**
- `kind` — enum: `observation` | `learning` | `pattern` | `hypothesis`

**Optional attributes:**
- `id`
- `confidence` — 0.0–1.0
- `source` — where it came from: `manual` | `mission` | `dream-reflex` | `dream-curator` | `dream-synthesis` | `dream-genesis`
- `source-mission` — entity ref if mission-derived
- `applies-to` — comma-separated ventures or domains
- `validated` — boolean

**Content:** The insight text.

**Indexing semantics:**
- Becomes entity of type `insight`
- Indexed for cross-venture pattern detection by Synthesis cycle
- Hypotheses with `validated=false` after 90 days surface as Genesis review candidates

**Example:**

```markdown
<insight kind="pattern" confidence="0.78" source="dream-curator"
         applies-to="burtucala,realization">
Leads arriving via the international content funnel convert at 3× the rate of
domestic leads but require 2× the touchpoints before closing.
</insight>
```

---

### 3.8 `<question>`

**Purpose:** An open question awaiting an answer. The "things I don't know yet" primitive.

**Required attributes:** none

**Optional attributes:**
- `id`
- `for` — contact ref of who might answer
- `priority` — enum: `low` | `medium` | `high`
- `status` — enum: `open` | `answered` | `obsolete` (default `open`)
- `answered-by` — contact ref (set when status changes to answered)

**Content:** The question.

**Indexing semantics:**
- Becomes entity of type `question`
- Surfaces in agent context when relevant topic is discussed
- Open questions older than 30 days flagged by Curator

**Example:**

```markdown
<question for="contact-meirav" priority="medium" status="open">
Should the F&F webinar emphasize the local-first guarantee or the multi-runtime
flexibility as the lead angle?
</question>
```

---

### 3.9 `<assumption>`

**Purpose:** A working assumption being relied on. Distinct from a decision (which is acted on) — an assumption is a placeholder pending validation.

**Required attributes:** none

**Optional attributes:**
- `id`
- `confidence` — 0.0–1.0
- `needs-validation` — boolean (default `true`)
- `validate-by` — ISO 8601 date
- `status` — enum: `working` | `validated` | `invalidated`

**Content:** The assumption.

**Indexing semantics:**
- Becomes entity of type `assumption`
- Working assumptions older than 90 days surface for review
- Invalidated assumptions feed Dreaming for "what changed" insights

**Example:**

```markdown
<assumption confidence="0.6" needs-validation="true" validate-by="2026-06-15">
Most v5.5.0 users will run RealizeOS on a local laptop, not a VPS, in the first 90 days post-launch.
</assumption>
```

---

### 3.10 `<contact>`

**Purpose:** A reference to a person. Used inline anywhere a person is mentioned.

**Required attributes:**
- `ref` — entity ref (e.g., `contact-meirav` or `brand:meirav`)

**Optional attributes:**
- `role` — context-specific role this person plays here

**Content:** Optional display text (otherwise the contact's `name` from their entity is used).

**Indexing semantics:**
- Adds an inbound ref to the referenced contact entity
- Used for "who's involved in what" graph queries
- Refs to nonexistent contacts flagged by validation loop

**Example:**

```markdown
Discussed pricing with <contact ref="contact-meirav" role="strategic-partner">Meirav</contact>
and <contact ref="brand:miguel">Miguel</contact>.
```

---

### 3.11 `<reference>`

**Purpose:** A citation to an external source (web page, paper, book, document).

**Required attributes:**
- One of: `url`, `doi`, `isbn`

**Optional attributes:**
- `accessed` — ISO 8601 date
- `author` — free text
- `title` — free text
- `cite-as` — short citation key for reuse

**Content:** Optional commentary on the reference.

**Indexing semantics:**
- Becomes entity of type `reference`
- URLs are validated for reachability periodically (warn on dead links)
- Cite keys allow shorter inline references later

**Example:**

```markdown
<reference url="https://arxiv.org/abs/2502.12345" accessed="2026-05-20"
           author="Khattab et al." title="GEPA: Trace-Driven Self-Evolution"
           cite-as="gepa-2026">
Foundational paper for our Dreaming subsystem's trace analysis.
</reference>

Later in the document: As shown in <reference cite-as="gepa-2026" />, ...
```

---

### 3.12 `<metric>`

**Purpose:** A measurement, KPI, or quantitative observation worth tracking.

**Required attributes:**
- `name` — short metric identifier (lowercase-with-hyphens)
- `value` — numeric or string value
- `at` — ISO 8601 datetime of measurement

**Optional attributes:**
- `id`
- `unit` — e.g., `eur`, `count`, `ratio`, `percent`, `ms`
- `target` — desired value for comparison
- `venture` — venture this metric belongs to
- `series` — group metrics into a series for time-series queries

**Content:** Optional context.

**Indexing semantics:**
- Becomes entity of type `metric`
- Time-series queries via `series` grouping
- Targets vs actuals feed dashboard views

**Example:**

```markdown
<metric name="weekly-active-tenants" value="1" unit="count" at="2026-05-20"
        target="10" venture="realizeos" series="growth-trajectory">
End of week 1 post-internal-launch.
</metric>
```

---

### 3.13 `<draft>`

**Purpose:** A lifecycle marker indicating content is incomplete or work-in-progress. Tells agents and the indexer "treat this with lower confidence."

**Required attributes:** none

**Optional attributes:**
- `finalize-by` — ISO 8601 date
- `owner` — contact ref

**Content:** The draft content.

**Indexing semantics:**
- Content inside `<draft>` is indexed but with reduced confidence
- Excluded from "production" agent context unless explicitly requested
- `finalize-by` deadlines surface in Curator
- Drafts older than 60 days flagged for "finalize or archive" decision

**Example:**

```markdown
<draft finalize-by="2026-05-25" owner="contact-asaf">
## Burtucala Q3 content plan

[Draft outline — not yet reviewed with Meirav. Don't reference externally.]

- Theme: AI-native operators
- Cadence: 2x/week
- ...
</draft>
```

---

## 4. Composition Rules

### 4.1 What Can Nest Inside What

| Parent | Permitted children |
|---|---|
| `<decision>` | `<rationale>`*, `<impacts>`*, `<followups>`*, `<contact>`, `<reference>`, `<action>`, `<commitment>`, `<risk>`, `<assumption>` |
| `<commitment>` | `<contact>`, `<reference>`, `<deadline>` |
| `<mission>` (in mission files) | `<action>`, `<blocker>`, `<insight>`, `<question>` |
| `<insight>` | `<contact>`, `<reference>`, `<assumption>` |
| `<risk>` | `<mitigation>`*, `<contact>`, `<reference>` |
| `<draft>` | any tag (its content is still indexed) |

*Marked tags (`<rationale>`, `<impacts>`, `<followups>`, `<mitigation>`) are **child-only** — they're meaningful only inside a parent and don't have standalone entity semantics.

### 4.2 What Should NOT Nest

- `<decision>` inside `<decision>` — separate decisions are separate entities
- `<commitment>` inside `<commitment>` — same
- `<draft>` inside `<draft>` — the outer draft already marks everything inside as draft

### 4.3 Frontmatter vs Inline Tag Conflicts

If both YAML frontmatter and inline tags define the same field:
- Frontmatter wins for **file-level** metadata (e.g., `type`, `id`, `venture`)
- Inline tags win for **content-level** annotations (e.g., specific decisions inside the file)

A file with frontmatter `type: decision` and a single inline `<decision>` is **one entity** — frontmatter and inline merged. A file with multiple inline `<decision>` tags is **multiple entities** with the file as a container.

---

## 5. Indexing Behavior Summary

The Synapse background indexer extracts on each FABRIC change:

1. **Parse frontmatter** → file-level metadata
2. **Parse semantic tags** → entity-level metadata + content
3. **Build entities** in `entities` table (one per file-frontmatter or per inline tag with structural type)
4. **Extract refs** → `refs` table (from wikilinks, `ref=` attributes, and frontmatter ref fields)
5. **Extract tags** → `tags` table
6. **Generate summaries** via small local model (debounced)
7. **Compute embeddings** for L2 search (cached by content hash)
8. **Update L1 TOC** → SSE broadcast to active consumers
9. **Validate refs** → log broken refs to validation report

---

## 6. Validation Policy

**Soft validation throughout.**

- Missing required attributes → warning in `I-insights/_validation.md`, indexer proceeds with partial data
- Invalid attribute values → warning, indexer uses raw string
- Broken refs → warning, ref still indexed for later repair
- Unknown tag names → indexed as generic structural elements; not surfaced as first-class entities until promoted to the vocabulary

The user can run `realize-os fabric lint <venture>` to surface all warnings interactively.

The indexer NEVER refuses content. The contract is "you write whatever you want; I'll index what I can and tell you what I couldn't."

---

## 7. Extension Mechanism

### 7.1 Proposing New Tags

Three paths:

1. **Manual**: edit `docs/fabric-semantic-tags.md`, send PR, get review from collaborators
2. **Dreaming-proposed**: the Synthesis cycle proposes new tags when it detects repeated structural patterns ("you've used `<lesson>` 12 times this month informally — promote to vocabulary?"). Proposal goes through the Dream Inbox.
3. **Per-venture custom**: a venture can define its own tags in `ventures/<key>/_tags.yaml` that exist only within that venture's scope

### 7.2 Promotion Criteria

A custom tag is promoted to canonical when:
- Used in ≥3 ventures, OR
- Used ≥20 times across all ventures over a 30-day window
- Has stable attribute conventions (the dreaming system can verify this)

### 7.3 Deprecation

Tags that fall out of use (zero new instances for 6 months) are flagged for deprecation. Existing content keeps the tag (no auto-removal); the vocabulary entry adds a `deprecated: true` flag.

### 7.4 Versioning

The vocabulary itself follows semver. The current version is v0.1. Breaking changes (renaming a canonical tag, removing required attributes) require a major version bump and a migration path.

---

## 8. Migration from Existing FABRIC Content

For pre-v5.5.0 FABRIC content without semantic tags:

1. **Auto-suggest** mode (one-time): the indexer scans existing markdown, proposes inline tag wrappings ("this paragraph looks like a decision — add `<decision>` tags?"). Proposals go through the Dream Inbox in batches per venture.

2. **Frontmatter-first** approach: existing files with `type: decision` in frontmatter are treated as if the entire file is one `<decision>` entity, even without inline tags. Lets old content be indexed without modification.

3. **No retroactive rewriting**: the indexer never modifies existing files without explicit user approval through the Dream Inbox.

---

## 9. Reserved Tags (Future)

These names are reserved but not yet defined; do not redefine for custom use:

- `<workflow>` — extracted reusable workflow patterns (likely added in Synthesis cycle output)
- `<mission>` — full mission definitions (currently file-level; might become inline)
- `<entity>` — generic typed entity wrapper
- `<context>` — agent context boundary markers
- `<note>` — annotation/note attached to another entity

---

## 10. Open Questions

1. **Should `<contact>` inline references render the contact's name automatically in the workspace UI?** Recommendation: yes, with the entity's `name` field; falls back to `ref` if entity missing.

2. **How verbose should the human-written form be?** Should we offer a shorthand (e.g., `@decision[committed,2026-05-20]: ...`) that translates to canonical tags at write time? Recommendation: not in v0.1; let canonical form bed in first.

3. **Should `<metric>` time-series get their own database table** instead of just `entities`? Recommendation: yes if metric volume grows past ~10k per venture; SQLite can handle it either way for first year.

4. **Should `<draft>` confidence reduction be configurable per-file** or a fixed multiplier? Recommendation: fixed 0.6× multiplier for v0.1; revisit based on usage.

5. **Per-venture tag dialects** — when can a venture override the meaning of a canonical tag? Recommendation: never override; ventures can only add new tags, never modify canonical ones.

6. **Localization** — should tag names be translatable (e.g., `<החלטה>` for Hebrew)? Recommendation: no; canonical English-named tags are easier to index, and content stays in whatever language the user prefers. Display names in UI can be localized.

7. **Embedding scope** — should the indexer embed each tag's content separately or only the file as a whole? Recommendation: separate embeddings per tag-bounded section for L2 precision; file-level summary in L1 for navigation.

---

*End of FABRIC Semantic Tag Vocabulary v0.1*
