# RealizeOS Concepts

## Architecture Overview

```
User Message
  → Channel Adapter (API / Telegram / WhatsApp / Webhooks)
  → Security Middleware (Headers → Audit → Rate Limit → Injection Guard → JWT)
  → Base Handler (session management)
  → Skill Detection → Agent Selection
  → Prompt Builder (multi-layer FABRIC context injection)
  → LLM Router (Flash / Sonnet / Strategy / Opus)
  → Tool Execution (Workspace, Stripe, Web, MCP, etc.)
  → Governance (approval gates) → Response
```

## The Multi-Layer Prompt

Every response is built from layers of context assembled from your knowledge base:

1. **Identity Layer** — Who you are (shared/identity.md)
2. **Preferences Layer** — User communication preferences
3. **Venture Layer** — Your venture identity and voice rules
4. **Routing Layer** — Agent team overview and capabilities
5. **Agent Layer** — The active agent's full definition
6. **Extra Context Layer** — Additional files loaded for the task
7. **Dynamic KB Layer** — RAG: relevant KB documents for this message
8. **Memory Layer** — Recent learnings and accumulated insights
9. **Cross-System Layer** — Context from other ventures (when enabled)
10. **Session Layer** — Active creative session state (if any)
11. **Proactive Layer** — Collaboration instructions (ask, suggest, push back)
12. **Format Layer** — Channel-specific formatting rules

## Creative Sessions

When a task requires multiple steps (write → review → iterate), RealizeOS creates a creative session that tracks:

- **Stage**: briefing → drafting → iterating → reviewing → approved
- **Pipeline**: Which agents are involved and in what order
- **Drafts**: Version history of all outputs
- **Context**: Files loaded for reference

Sessions persist across messages so you can iterate naturally.

## Self-Evolution

RealizeOS learns and improves over time. Key features:

- **Gap Detection** — Identifies missing capabilities from conversation patterns
- **Skill Generation** — Proposes new skill YAML from detected gaps
- **Performance Tracking** — Monitors which agents/skills perform well

## Governance

The governance system provides human oversight for consequential actions:

- **Approval Gates** — Configurable checkpoints requiring human approval before execution
- **Audit Logging** — JSONL persistent logs of all system actions with SSE streaming
- **Tool Gating** — Per-agent allowlists/denylists for tool access
- **RBAC** — 6 built-in roles (owner, admin, operator, user, viewer, guest)

## Developer Mode

Developer mode provides tools for AI-assisted system development:

- **Context Generation** — Generate AI tool context files for your system
- **Git Safety** — Snapshot and rollback for safe experimentation
- **Scaffolder** — Generate extension/tool/agent boilerplate
- **Health Check** — Verify system configuration and dependencies

All changes require user approval before being applied.

## Multi-System Architecture

Each system is isolated with its own:

- Knowledge base (FABRIC directories)
- Agent definitions
- Venture voice rules
- Skills and workflows
- Conversation history

Cross-system context is available when `cross_system: true` is set in your `realize-os.yaml` features. When enabled, agents can see state maps and venture summaries from all configured ventures, allowing informed cross-venture coordination.

## Tool Integration

Tools extend the OS's capabilities beyond conversation:

- **Google Workspace** — Gmail, Calendar, Drive, Sheets
- **Web Tools** — Search (Brave API), page fetch, browser automation
- **MCP** — Protocol for connecting to external tool servers
- **Stripe** — Charges, subscriptions, invoices with safety guards
- **Messaging** — Agent-to-agent communication, human notifications
- **Telephony** — Twilio-powered voice/SMS
- **Social** — Social media publishing
- **Approval** — Human-in-the-loop approval workflows
- **Custom Tools** — BaseTool SDK for building new capabilities

Tools are activated based on task classification. Write operations (sending emails, creating events) always require confirmation.

> 📖 See [Architecture](architecture.md) for full technical details.
