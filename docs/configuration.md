# Configuration Guide

RealizeOS is configured through `realize-os.yaml` and environment variables in `.env`.

## realize-os.yaml

This is the main configuration file. It defines your systems, agents, routing, and features.

### Structure

```yaml
name: "My Business"

systems:
  - key: my-business-1
    name: "My Business"
    directory: systems/my-business-1

    routing:
      content: [writer, reviewer]
      strategy: [analyst, orchestrator]
      general: [orchestrator]

    agent_routing:
      writer: [write, draft, post, blog, content]
      analyst: [analyze, research, data, market]
      reviewer: [review, check, quality, approve]
      orchestrator: [plan, help, think, prioritize]

features:
  agents_v2: true          # V2 agent system
  skills_detection: true   # Auto-detect skills from conversation
  skills_v2: true          # V2 skill format with enhanced metadata
  creative_sessions: true  # Multi-turn creative workflows
  evolution: true          # Self-improvement engine
  extensions: true         # Extension system
  kb_indexing: true        # Knowledge base search indexing
  audit_logging: true      # Security audit trail
  agent_lifecycle: true    # Agent lifecycle hooks
  heartbeats: true         # Agent heartbeat monitoring
  mcp: true                # MCP tool server protocol
  approval_gates: true     # Human-in-the-loop approval gates

routing:
  default_class: flash            # Default routing class
  classes:
    flash:
      provider: google
      model: gemini-2.0-flash-001
    sonnet:
      provider: anthropic
      model: claude-3-5-sonnet-20241022
    opus:
      provider: anthropic
      model: claude-3-opus-20240229
    strategy:
      provider: anthropic
      model: claude-3-5-sonnet-20241022  # For strategic/planning tasks

channels:
  - type: api
    port: 8080
```

### Systems

Each system represents a venture or business unit. Key fields:

| Field | Description |
|-------|-------------|
| `key` | Unique identifier, used in API calls and directory name |
| `name` | Display name |
| `directory` | Path to FABRIC directories (relative to project root) |
| `routing` | Task type → agent pipeline mapping |
| `agent_routing` | Agent → keyword list for message-based routing |
| `locale` | Content language, e.g. `he`. A right-to-left language (Hebrew, Arabic, ...) turns the dashboard RTL while that venture is selected |

**Language and direction.** The dashboard follows the selected venture's `locale`: with
`locale: he` the page is right-to-left, and each message, approval and trail line takes the
direction of its own text, so mixed Hebrew/English reads correctly. The language button in the
sidebar overrides it per browser (venture → עברית → English). UI labels stay in English.

### Agent Routing

The `agent_routing` section maps keywords to agents. When a user sends a message, the system scores each agent by counting keyword matches and routes to the highest-scoring agent.

```yaml
agent_routing:
  writer: [write, draft, post, blog, content, newsletter, email]
  analyst: [analyze, research, compare, market, data, competitor]
```

To add a new agent, create a `.md` file in `A-agents/` and add routing keywords here.

### Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `review_pipeline` | `true` | Enable automatic review pipeline for content |
| `auto_memory` | `true` | Log learnings after meaningful interactions |
| `proactive_mode` | `true` | Enable proactive suggestions in prompts |
| `cross_system` | `false` | Share context across all configured systems |
| `email_digest` | `false` | Email a daily Dream Inbox digest (see below) |
| `dreaming_curator` | `false` | Run the Curator per venture on a daily schedule |
| `dreaming_reflex` | `false` | Run Reflex enrichment over recently-changed entities |
| `enforce_gates` | `false` | Enforce the trust ladder at the tool-dispatch chokepoint (see below) |
| `enforce_guardrails` | `false` | Reserved placeholder; guardrail post-response enforcement is deferred (no-op) |
| `agent_tools` | `false` | Agents call registry tools (Google, Sheets, ClickUp, MCP) while answering. Without `enforce_gates`, only read-only tools are offered (see below) |
| `cite_sources` | `false` | Answers cite knowledge-base sources inline as `[S1]` on the `api`, `dashboard` and `mcp` channels; the trail lists the sources (see below) |
| `agent_tokens` | `true` | Accept venture-scoped agent tokens (`rzag_...`) for outside agents on MCP and REST. Nothing changes until an owner creates one; `false` makes every agent token stop working at once. See [mcp-server.md](mcp-server.md#agent-tokens-one-agent-one-clients-brain) |
| `packs` | `false` | Profession and market packs (spec 010). Each venture's linked packs (`systems/<venture>/packs.yaml`) add context, skills, agents and schema extensions, and their trust defaults can only tighten the trust ladder. The API loads the skills at startup and on reload; templates that name packs link them instead of copying their agents and skills. Off: everything works as before packs. See [packs.md](packs.md#what-packs-change-at-run-time) |

Custom flags are passed through without error — the engine ignores unknown flags.

### Agent Tools (`agent_tools`)

With `features.agent_tools: true`, agents answer through a tool loop: the model may call any
available registry tool and gets the results back before answering. Every call goes through
the tool registry, so the governance gate applies. Write actions (sending mail, appending to
a sheet, creating tasks, any MCP tool not listed as read-only) are offered **only when
`enforce_gates` is also on**; otherwise agents get read-only tools. Narrow an agent's tools with
`tools_allowlist` / `tools_denylist` in `A-agents/<agent>.persona.yaml`. MCP tools are writes
unless listed under `read_only_tools` for their server in `mcp-servers.yaml`. Agent Drive
uploads/downloads are confined to `REALIZE_AGENT_FILES_DIR` (default `<KB_PATH>/data/agent-files`).

### "What I used" trail and citations (`cite_sources`)

Every chat answer carries a trail: the knowledge-base sources its prompt included, numbered
`[S1]…[Sn]`, the pack rule cards numbered `[R1]…[Rn]` with their verification level, layer and
pack (see [packs](packs.md#rule-cards-in-the-answer-trail)), and the tools it called, in order. The dashboard shows the trail live under each
answer and again in history; the API returns it as `trail` (see the
[API reference](api-reference.md#post-apichat)). Trails are stored per message in `memory.db` and
deleted with the conversation. They are never sent back to a model.

With `features.cite_sources: true`, the model is also told to cite those markers inline after each
fact or figure, and the dashboard renders them as footnotes. Citations are requested only on the
`api`, `dashboard` and `mcp` channels; Telegram, Slack and other text channels get answers
without markers. New installs from `realize_lite` ship with `cite_sources: true`; the engine
default stays `false`.

### Governance Enforcement (`enforce_gates`)

> **Since 5.7.0, approving executes.** A held action is stored in `approval_queue` with its full
> parameters and the conversation it came from. Approving it (dashboard, `POST /api/approvals/{id}/approve`,
> or the MCP `approve_request` tool) dispatches it **at most once** through the tool registry, stores
> the result or error on the approval, and posts a status line back into that conversation. Rejecting
> never runs it. Only one decision can win (the item must still be pending and unexpired), and the
> approval records who decided (`decided_by`) and from where (`decision_channel`). An approved pack
> verification (`pack_verify`, owner only) stores its outcome in the same fields; see [packs.md](packs.md).
>
> **Outcome.** `execution_status` moves `claimed` → `succeeded` or `failed`. A row left at `claimed`
> means the process stopped while the action was running: the outcome is unknown, it is not retried
> automatically, and a person should check the external system (for example the sheet) and note the
> result. Expired approvals can't be approved or run: lists report them as `expired` (never as
> pending), and the dashboard shows them under **Expired** with no decision controls. In the
> dashboard, a decided item shows what really happened (done, failed with the error, or unknown
> after a restart), right after the decision and later under **Decided**.
>
> **Fails closed.** If the governance check itself fails (for example a malformed `trust.level`,
> which also falls back to level 1) or the approval can't be saved, write actions are blocked; reads
> keep working.
>
> Skill `human` steps create a question item (`skill_input`). Answering it — in chat or by approving
> with a note in the dashboard — records it as `answered` (input, not an approval) and resumes the
> skill; rejecting it stops the skill. New installs from `realize_lite` ship with `enforce_gates: true`;
> the engine default stays `false` for existing configs.


By default RealizeOS does **not** intercept tool execution: the trust ladder
under `trust:` is advisory only. Setting `features.enforce_gates: true` installs
a governance gate at the single tool-dispatch chokepoint
(`ToolRegistry.execute`). Before each tool action runs, the gate consults
`realize_core.governance.trust_ladder.check_trust` for the current trust level:

- **AUTO** → the action runs as normal.
- **APPROVE** → the action is held; an approval request is created (visible at
  `GET /api/approvals`) and the tool returns a "requires operator approval"
  result instead of executing.
- **BLOCK** → the action is refused.

With `features.packs` on, a call made for a venture also gets that venture's pack trust
defaults (`trust.yaml` in its packs and in `F-foundations/overrides/`), **only where they are
stricter** than the ladder's decision: `auto` → `approve` or `block`, `approve` → `block`. A pack
value that would loosen a decision is ignored and logged. See
[packs.md](packs.md#what-packs-change-at-run-time).

The gate **fails open**: any internal gate error logs and allows the action, so
a gate bug can never brick tool execution. When `enforce_gates` is `false`
(the default) the gate is never installed and tool dispatch is byte-for-byte
unchanged. Tune per-action behavior with the `trust:` block (level + action
rules) documented above.

### Email Dream Inbox Digest

When `features.email_digest` is `true`, RealizeOS emails a deterministic,
grouped-by-venture digest of the **pending** Dream Inbox proposals so you can
supervise the Dreaming subsystem by exception without opening the dashboard.
It is **disabled by default**, so existing deployments are unaffected.

Each item shows its cycle type, action, title, confidence and creation date,
plus per-proposal approve/reject links targeting
`/api/dreams/{proposal_id}/approve|reject`. Low-confidence (`<0.6`) or
high-impact items are surfaced in a "NEEDS YOUR ATTENTION" section at the top.
If nothing is pending, **no email is sent** (the run is still recorded in the
event log). Gmail send failures are logged and never crash the scheduler.

It requires Google Workspace credentials (the `gws` extra + OAuth setup). When
enabled without a recipient it warns and stays inert.

```yaml
features:
  email_digest: true          # turn the digest on

email_digest:
  recipient: info@realization.co.il   # where the digest is emailed
  base_url: ""                        # public base URL for links, e.g. https://app.example.com
  schedule: daily                     # scheduler interval (daily, weekly, 12h, ...)
  workdays_only: true                 # only run Mon–Fri
  timezone: "Europe/Lisbon"           # time zone for the schedule
```

Immediate **urgent alerts** piggyback on the same `email_digest.recipient`:
when the feature is enabled, `realize-os fabric apply` sends a one-off alert
email the moment the apply-loop *blocks* an approved-but-hard-denied action (a
forbidden write attempt). These blocked items never appear in the digest, so
the alert is their only notification. Dry-runs never alert.

The API server starts a dedicated scheduler at startup only when the flag is
on. You can also send or preview the digest on demand from the CLI:

```bash
realize-os fabric digest --dry-run     # print the digest, send nothing
realize-os fabric digest               # email it to the configured recipient
```

### Scheduled Dreaming (Curator & Reflex)

Two background Dreaming jobs can run on a schedule. Both are **disabled by
default** and gated behind feature flags, so existing deployments are
unaffected. Each runs **per venture** under that venture's effective Trust
Policy, and every proposal lands in the Dream Inbox for review.

- **Curator** (`features.dreaming_curator`) runs once daily at `dreaming.hour`
  in `dreaming.timezone`, generating FABRIC-hygiene proposals.
- **Reflex** (`features.dreaming_reflex`) runs every
  `dreaming.reflex_interval_minutes` (default `60`). On each pass it finds
  entities modified since the previous run (lookback = one interval plus a
  small buffer), caps the batch at 200 entities per venture per run, and emits
  low-risk enrichment proposals (tags, references, missing-field annotations).

Reflex is a **scheduled** pass rather than a live-pipeline hook: it reuses the
Dream scheduler so recently-changed entities get enrichment with zero risk to
the message-handling path. Each venture and the overall pass are fully guarded —
a failure for one venture is logged and never crashes the scheduler.

```yaml
features:
  dreaming_curator: true     # turn the scheduled Curator on
  dreaming_reflex: true      # turn scheduled Reflex on

dreaming:
  hour: 3                          # wall-clock hour the Curator runs daily
  timezone: "Europe/Lisbon"        # time zone for the Curator schedule
  reflex_interval_minutes: 60      # how often Reflex enriches changed entities
```

### Dreaming Trust Policy (per-venture)

The Trust Policy controls what autonomous **Dreaming** cycles may do to your
knowledge base. Each action maps to one of three levels:

| Level | Behavior |
|-------|----------|
| `full-auto` | Applied without approval (e.g. adding a tag) |
| `propose` | Queued in the Dream Inbox for human review |
| `deny` | Never allowed |

Policies are resolved **per venture** with later layers merging over earlier
ones, so each file only needs to specify what differs:

1. Built-in defaults (safe: most actions `propose`, dangerous ones `deny`).
2. Global `shared/trust-policy.yaml`.
3. Venture override `systems/<venture_key>/trust-policy.yaml`.

A venture file may be **partial** — only the actions it lists are overridden,
the rest are inherited. This lets one venture be stricter than another (e.g.
Arena can `deny` an action that is `propose` globally) without duplicating the
whole policy. Missing files are skipped silently, falling back to the global
policy and then the built-in defaults.

```yaml
# systems/<venture_key>/trust-policy.yaml — merges over the global policy
trust_policy:
  add_tag: propose        # stricter than the global/default full-auto
  update_summary: full-auto
  suggest_decision: deny
```

The same `trust_policy:` map format is used for the global
`shared/trust-policy.yaml`. A bare action→level map (without the
`trust_policy:` key) is also accepted for backward compatibility.

### LLM Routing

**Any one provider is enough.** Every feature (chat, tools, skills, vision, search) works on Anthropic, Gemini, OpenAI, Ollama, or anything LiteLLM routes to. A provider may be better at a task, but none is required.

The router classifies each task into a **tier**, and each provider maps the tier to one of its own models:

| Tier | Task classes | Claude | Gemini | OpenAI | Ollama |
|------|--------------|--------|--------|--------|--------|
| `fast` | `simple`, unknown | Sonnet | Flash | GPT-4o Mini | `OLLAMA_MODEL` |
| `standard` | `content`, `reasoning`, `financial`, `google`, `web_research`, `web_action` | Sonnet | Pro | GPT-4o | `OLLAMA_MODEL` |
| `deep` | `complex` | Opus | Pro | GPT-4o | `OLLAMA_MODEL` |

The generic LiteLLM provider uses `LITELLM_MODEL` for every tier. Setting a quality override still moves a task to `standard` or `deep`.

**Choosing the primary provider and the models.** Set the environment variables below, or use **Settings -> LLM Routing** in the dashboard (it writes the same variables, applies without a restart, and needs the `system:manage` permission). The onboarding wizard also asks which connected provider to prefer. Over the API: `GET` and `PUT /api/llm/routing`.

| Variable | Default | What it does |
|----------|---------|--------------|
| `LLM_PRIMARY` | first available | Provider tried first: `anthropic`, `gemini`, `openai`, `ollama` or `litellm` (`google` and `claude` are accepted as aliases) |
| `LLM_FALLBACK` | see below | Provider order used when the primary fails, e.g. `gemini,openai,ollama`. Unknown names are ignored with a warning |
| `LLM_MODEL_FAST` | provider default | Pin the `fast` tier to a LiteLLM model string, e.g. `gemini/gemini-2.5-flash` |
| `LLM_MODEL_STANDARD` | provider default | Pin the `standard` tier, e.g. `openai/gpt-4o` |
| `LLM_MODEL_DEEP` | provider default | Pin the `deep` tier, e.g. `anthropic/claude-opus-5-5` |

Without `LLM_FALLBACK` the order is `LLM_PRIMARY` first, then Claude, Gemini, OpenAI, Ollama, LiteLLM, then any other registered provider. A pinned tier model's prefix chooses the provider: `anthropic/` (Claude), `gemini/`, `openai/`, `ollama/` (or `ollama_chat/`), and anything else goes to the generic LiteLLM provider.

When the primary fails, the router tries the next available provider with that provider's own model for the same tier. A refusal is final and is not retried elsewhere.

### LLM Providers

Providers are registered at startup from the keys and URLs found in the environment. A provider is available only when it can actually be used.

| Provider | Env variables | Notes |
|----------|---------------|-------|
| Anthropic (Claude) | `ANTHROPIC_API_KEY`; optional `ANTHROPIC_WORKSPACE_ID`, `CLAUDE_SONNET_MODEL`, `CLAUDE_OPUS_MODEL` | Set the workspace ID for workspace-scoped keys. It is sent as the `anthropic-workspace-id` header |
| Google AI (Gemini) | `GOOGLE_AI_API_KEY`; optional `GEMINI_FLASH_MODEL`, `GEMINI_PRO_MODEL` | Runs through LiteLLM |
| OpenAI | `OPENAI_API_KEY` | Runs through LiteLLM |
| Ollama (local) | `OLLAMA_BASE_URL` (default `http://localhost:11434`), `OLLAMA_MODEL` (default `llama3.1:8b`) | No key. `OLLAMA_HOST` still works as an alias when `OLLAMA_BASE_URL` is empty. Available when the server answers. **Tool use and vision are detected per model from Ollama's `/api/show`**, so a model without tools is not offered tool calls |
| Any other (LiteLLM) | `LITELLM_MODEL` plus that provider's own key (e.g. `MISTRAL_API_KEY`); optional `LITELLM_API_BASE` | `LITELLM_API_BASE` (a gateway or proxy URL) applies to this generic provider only |

**Examples.** Put one of these blocks in `.env`.

```bash
# Gemini only
GOOGLE_AI_API_KEY=<your-google-ai-key>

# OpenAI only
OPENAI_API_KEY=<your-openai-key>
LLM_PRIMARY=openai

# Ollama only (no key). Run `ollama list` for the tag.
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b

# Claude only, with a workspace-scoped key
ANTHROPIC_API_KEY=<your-anthropic-key>
ANTHROPIC_WORKSPACE_ID=<your-workspace-id>

# A LiteLLM proxy / gateway in front of any model
LITELLM_MODEL=openai/my-gateway-model
LITELLM_API_BASE=https://llm-gateway.example.com
OPENAI_API_KEY=<the gateway key>

# Mixed: Gemini for quick tasks, Claude for deep reasoning, OpenAI as the fallback
GOOGLE_AI_API_KEY=<key>
ANTHROPIC_API_KEY=<key>
OPENAI_API_KEY=<key>
LLM_PRIMARY=gemini
LLM_FALLBACK=gemini,anthropic,openai
LLM_MODEL_DEEP=anthropic/claude-opus-5-5
```

**Tools without a tool-capable provider.** When an agent has tools but no available provider can run them, the agent says it has no live data in that turn, and the "what I used" trail shows a notice (`tools_unavailable`). It no longer falls back to answering silently. Add a tool-capable provider (any hosted one, or an Ollama model that supports tools) to fix it.

**Check what is available.** `GET /api/status` lists the providers that are usable (`claude`, `gemini`, `openai`, `ollama`, `litellm`). `python scripts/provider_smoke.py --provider <name>` runs the webinar storyline against one real provider; see [Contributing](../CONTRIBUTING.md).

### Search and embeddings

| Variable | Default | What it does |
|----------|---------|--------------|
| `KB_EMBED_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | The fastembed model used for semantic search over the knowledge base (about 0.22 GB, downloaded on first use, then cached; the Docker image includes it). Set `none` (also `off`, `0`, `false`) for keyword search only. E5 prefixes are applied automatically if you name an e5 model |
| `FASTEMBED_CACHE_PATH` | fastembed's own cache | Where the model is stored. The Docker image sets `/app/models/fastembed` |

Keyword search uses SQLite FTS5 with a trigram tokenizer, so Hebrew and other non-English text match. The tokenizer depends on the SQLite version: 3.45 or later uses `trigram remove_diacritics 1`; 3.34 to 3.44 (including the Docker image) uses plain `trigram`; older uses `unicode61`. When the tokenizer changes, the knowledge-base, memory and Synapse indexes rebuild on first start. To rebuild by hand: `realize-os kb reindex` or `POST /api/kb/reindex`.

## Environment Variables

```bash
# LLM providers: set any one (see "LLM Providers" above)
ANTHROPIC_API_KEY=<your-key>        # Claude
ANTHROPIC_WORKSPACE_ID=             # Optional, for workspace-scoped keys
GOOGLE_AI_API_KEY=<your-key>        # Gemini
OPENAI_API_KEY=<your-key>           # GPT models
OLLAMA_BASE_URL=http://localhost:11434  # Local models, no key (OLLAMA_HOST also works)
OLLAMA_MODEL=llama3.1:8b
LITELLM_MODEL=                      # Any other LiteLLM model string
LITELLM_API_BASE=                   # Optional gateway URL for LITELLM_MODEL
LLM_PRIMARY=                        # anthropic | gemini | openai | ollama | litellm
LLM_FALLBACK=                       # e.g. gemini,openai,ollama
LLM_MODEL_FAST=                     # e.g. gemini/gemini-2.5-flash
LLM_MODEL_STANDARD=
LLM_MODEL_DEEP=
KB_EMBED_MODEL=                     # empty = multilingual default; none = no embeddings

# API Security
REALIZE_API_KEY=                 # API key for simple auth
REALIZE_JWT_SECRET=              # JWT signing secret
REALIZE_JWT_ENABLED=false        # Enable JWT authentication

# Telegram Bot
TELEGRAM_BOT_TOKEN=              # Bot token from @BotFather

# WhatsApp (Business API)
WHATSAPP_API_TOKEN=              # WhatsApp API token
WHATSAPP_PHONE_NUMBER_ID=        # Phone number ID
WHATSAPP_VERIFY_TOKEN=           # Webhook verification token

# Twilio (Voice/SMS)
TWILIO_ACCOUNT_SID=              # Twilio account SID
TWILIO_AUTH_TOKEN=               # Twilio auth token
TWILIO_PHONE_NUMBER=             # Twilio phone number

# Stripe (Financial tools)
STRIPE_SECRET_KEY=               # Stripe secret key

# Web Search
BRAVE_API_KEY=                   # Brave Search API key

# MCP Server (5.1.0+)
MCP_ENABLED=false                # Enable the MCP SSE endpoint
MCP_ALLOW_ADMIN=false            # Expose admin tools (venture CRUD, settings)
MCP_EXPOSE_KB=true               # Expose KB search tools
MCP_EXPOSE_OPS=true              # Expose workflow/skill/evolution tools
MCP_RATE_LIMIT_PER_MINUTE=       # Tool calls per caller per minute (empty = API_RATE_LIMIT_PER_MINUTE)
```

## MCP Server Configuration

The built-in MCP server can be configured in `realize-os.yaml`:

```yaml
mcp:
  enabled: true                   # Mount /mcp (Streamable HTTP) + /mcp/sse + /mcp/messages/
  streamable_http: true           # Serve the Streamable HTTP transport on /mcp
  public_url: https://os.example.com  # Public base URL — OAuth issuer
  oauth:
    enabled: false                # OAuth 2.1 for Claude.ai custom connectors
  allow_admin: false              # Admin tools (venture CRUD, system settings)
  expose_kb: true                 # KB search/get tools
  expose_ops: true                # Workflow, skill, evolution tools
  rate_limit_per_minute: null     # Tool calls per caller per minute (null = API_RATE_LIMIT_PER_MINUTE)
  max_sessions: 100               # Maximum concurrent MCP sessions
  session_timeout: 3600           # Session TTL in seconds
```

Or use environment variables (env vars override YAML). Start with:

```bash
realize-os mcp serve --port 8080
```

See [MCP Server Reference](mcp-server.md) for tool catalog and integration recipes.

## Developer Mode

Developer mode provides tools for AI-assisted development:

```yaml
# In realize-os.yaml
developer_mode:
  enabled: false
  allowed_roles: [admin, owner]
  auto_snapshot: true
```

CLI commands:

```bash
realize-os devmode setup      # Generate AI tool context files
realize-os devmode check      # Run system health check
realize-os devmode scaffold   # Scaffold new extensions
realize-os devmode snapshot   # Create a git safety snapshot
realize-os devmode rollback   # Rollback to a previous snapshot
```

See [Architecture: Developer Mode](architecture.md) for details.

## Extending the System

### Add an Agent

1. Create `systems/my-business-1/A-agents/my-agent.md` with the agent definition
2. Add routing keywords in `realize-os.yaml` under `agent_routing`
3. The agent is auto-discovered — no code changes needed

### Add a Skill

1. Create `systems/my-business-1/R-routines/skills/my-skill.yaml`
2. Define trigger patterns, steps, and agent assignments
3. The skill is auto-loaded — no code changes needed

### Add a Venture

```bash
realize-os venture create --key new-venture --name "New Venture"
```

This creates a full FABRIC directory structure and adds the venture to `realize-os.yaml`.

### Add a Channel

Implement a new channel adapter following the pattern in `realize_core/channels/base.py`.

## Next Steps

- [Core Concepts](concepts.md)
- [Skill Authoring Guide](skill-authoring.md)
- [CLI Reference](cli-reference.md)
- [MCP Server Reference](mcp-server.md)
- [API Reference](api-reference.md)
