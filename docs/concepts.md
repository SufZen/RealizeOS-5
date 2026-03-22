# RealizeOS Concepts

## Architecture Overview

```
User Message
    │
    ▼
┌─────────────────┐
│  Channel Layer   │  (API, Telegram, etc.)
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  Base Handler    │  Message processing pipeline
│  1. Session?     │  → Check active creative session
│  2. Skill?       │  → Auto-detect and execute skills
│  3. Route        │  → Select agent, classify task
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  LLM Router      │  Task classification → model selection
│  Simple → Flash   │
│  Content → Sonnet │
│  Complex → Opus   │
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  Prompt Builder   │  Multi-layer assembly from KB
│  Identity → Vent. │
│  → Agent → Context│
│  → Memory → Session│
│  → Format         │
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  Tools Layer      │  Google, Web, Browser, MCP
└─────────────────┘
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

RealizeOS learns and improves over time:

1. **Interaction Tracking** — Every request is logged with metadata
2. **Gap Detection** — Finds unhandled patterns, repeated ad-hoc requests
3. **Skill Suggestion** — Auto-generates skill YAML for detected gaps
4. **Prompt Refinement** — Suggests agent prompt improvements from feedback

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

RealizeOS can use external tools during conversations:

- **Google Workspace** — Gmail (search, read, send, draft), Calendar (list, create, update, free time), Drive (search, read, create)
- **Web** — Search (Brave API) and fetch/read web pages
- **Browser** — Headless Chromium for page interaction
- **MCP** — Connect to any MCP-compatible tool server

Tools are activated based on task classification. Write operations (sending emails, creating events) always require confirmation.
