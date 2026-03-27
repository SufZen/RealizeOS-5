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

Custom flags are passed through without error — the engine ignores unknown flags.

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
ANTHROPIC_API_KEY=sk-ant-...    # Required for Claude models
GOOGLE_API_KEY=AIzaSy...         # Required for Gemini models
OPENAI_API_KEY=sk-...            # Optional, for GPT models
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
```

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
python cli.py devmode setup      # Generate AI tool context files
python cli.py devmode check      # Run system health check
python cli.py devmode scaffold   # Scaffold new extensions
python cli.py devmode snapshot   # Create a git safety snapshot
python cli.py devmode rollback   # Rollback to a previous snapshot
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
python cli.py venture create --key new-venture --name "New Venture"
```

This creates a full FABRIC directory structure and adds the venture to `realize-os.yaml`.

### Add a Channel

Implement a new channel adapter following the pattern in `realize_core/channels/base.py`.

## Next Steps

- [Core Concepts](concepts.md)
- [Skill Authoring Guide](skill-authoring.md)
- [API Reference](api-reference.md)
