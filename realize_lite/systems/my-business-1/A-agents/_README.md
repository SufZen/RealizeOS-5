# Agent Routing Guide

This directory contains your AI agent team. Each `.md` file defines one agent with a specific role.

## How Routing Works

When you send a message, the system identifies the best agent based on keywords and context:

| Request Type | Primary Agent | Backup |
|---|---|---|
| Content creation (write, draft, post) | Writer | Reviewer |
| Research & analysis (analyze, compare) | Analyst | Orchestrator |
| Quality review (review, check, approve) | Reviewer | Writer |
| Planning & coordination (plan, help) | Orchestrator | Analyst |

## Available Agents

- **orchestrator** — Your general coordinator. Routes complex requests, breaks down multi-step tasks, and maintains project context.
- **writer** — Content creator. Drafts posts, emails, reports, and marketing copy aligned with your venture voice.
- **analyst** — Researcher and data analyst. Market research, competitive analysis, data interpretation.
- **reviewer** — Quality controller. Reviews content for accuracy, voice consistency, and completeness before publishing.

## Adding New Agents

Create a new `.md` file in this directory following the format:

```markdown
# Agent Name

## Role
What this agent does.

## Personality
How this agent behaves.

## Core Capabilities
- Capability 1
- Capability 2

## Operating Rules
1. Rule 1
2. Rule 2
```

The agent will be auto-discovered on the next server restart.
