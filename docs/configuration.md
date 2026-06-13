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

Custom flags are passed through without error — the engine ignores unknown flags.

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

Maps task complexity to models. The defaults use Claude and Gemini, but any provider can be substituted:

| Task Class | Default Model | When Used |
|------------|---------------|-----------|
| `simple` | `gemini-flash` | Quick lookups, simple questions |
| `content` | `claude-sonnet` | Writing, analysis, reasoning |
| `complex` | `claude-opus` | Strategy, multi-step planning |

### LLM Providers

RealizeOS supports multiple LLM providers via a provider registry. Available providers are auto-discovered at startup based on installed SDKs and configured API keys:

| Provider | Env Variable | Models |
|----------|-------------|--------|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | Claude Sonnet, Claude Opus |
| Google AI (Gemini) | `GOOGLE_AI_API_KEY` | Gemini Flash |
| OpenAI | `OPENAI_API_KEY` | GPT-4o, GPT-4o Mini |
| Ollama (local) | `OLLAMA_BASE_URL` | Any Ollama model (Llama, DeepSeek, etc.) |

At least one provider must be configured. The router automatically falls back to available providers if the primary is unavailable (fallback chain: Claude → Gemini → OpenAI → Ollama).

## Environment Variables

```bash
# LLM API Keys
ANTHROPIC_API_KEY=<your-key>    # Required for Claude models
GOOGLE_API_KEY=<your-key>         # Required for Gemini models
OPENAI_API_KEY=<your-key>         # Optional, for GPT models
OLLAMA_HOST=http://localhost:11434  # Optional, for local models

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
```

## MCP Server Configuration

The built-in MCP server can be configured in `realize-os.yaml`:

```yaml
mcp:
  enabled: true                   # Mount /mcp/sse + /mcp/messages/{session}
  allow_admin: false              # Admin tools (venture CRUD, system settings)
  expose_kb: true                 # KB search/get tools
  expose_ops: true                # Workflow, skill, evolution tools
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
