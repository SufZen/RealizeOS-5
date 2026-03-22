# Skill Authoring Guide

Skills are YAML files that define reusable workflows. They live in the `R-routines/skills/` directory of each system.

## v1 Skills — Simple Pipelines

A v1 skill triggers on keywords and runs agents in sequence.

```yaml
name: content_pipeline
triggers:
  - "write a post"
  - "create content"
  - "draft an article"
task_type: content
pipeline:
  - writer
  - reviewer
```

**How it works:**
1. User says "write a post about our Q2 results"
2. Skill triggers on "write a post"
3. Writer agent creates the draft
4. Reviewer agent reviews for quality
5. Final output returned to user

## v2 Skills — Multi-Step Workflows

v2 skills support multiple step types with context injection.

```yaml
name: competitor_analysis
version: "2.0"
description: "Research competitors and produce analysis"
triggers:
  - "analyze competitor"
  - "competitive analysis"
  - "compare with"
task_type: research

steps:
  - id: search
    type: tool
    action: web_search
    label: "Search for competitor info"
    params:
      query: "{user_message} site:linkedin.com OR site:crunchbase.com"

  - id: analyze
    type: agent
    agent: analyst
    label: "Analyze findings"
    inject_context: [search]
    prompt: |
      Based on this research data, provide a competitive analysis for: {user_message}
      Focus on: market position, strengths, weaknesses, and our differentiation.

  - id: confirm
    type: human
    question: "Should I create a detailed report from this analysis?"

  - id: report
    type: agent
    agent: writer
    label: "Write the report"
    inject_context: [search, analyze]
    prompt: |
      Write a structured competitive analysis report based on:
      Research: {search}
      Analysis: {analyze}
```

## Step Types

### `agent` — Call an LLM agent
```yaml
- id: draft
  type: agent
  agent: writer           # Agent key from your A-agents/
  label: "Draft content"
  inject_context: [step1] # Results from previous steps
  prompt: |               # Custom instructions (optional)
    Write based on: {user_message}
```

### `tool` — Execute a tool
```yaml
- id: search
  type: tool
  action: web_search      # Tool function name
  label: "Search the web"
  params:
    query: "{user_message}"
    count: 5
```

Available tools: `web_search`, `web_fetch`, `gmail_search`, `gmail_read`, `gmail_send`, `calendar_list_events`, `calendar_create_event`, `drive_search`, `drive_read_content`, `browser_navigate`

### `condition` — Branch logic
```yaml
- id: check
  type: condition
  check: "{analyze}"
  branches:
    "no data": skip       # Skip this step
    "insufficient": stop  # Stop the workflow
    "default": continue   # Continue normally
```

### `human` — Ask user for input
```yaml
- id: confirm
  type: human
  question: "Should I proceed with sending this email?"
```

The workflow pauses and waits for user confirmation before continuing.

## Variables and Context Injection

Use `{variable}` syntax in prompts and params:

- `{user_message}` — The original user message
- `{today}` — Today's date (ISO format)
- `{step_id}` — Result from a previous step (by its `id`)
- `{doc_title}` — Extracted from user message

## Triggers

Triggers are phrases that activate the skill. The detector uses substring matching, so:
- "write a post" matches "Can you write a post about our launch?"
- Be specific to avoid false triggers
- Use 3-5 triggers per skill

## File Location

Place skill files in your system's routines directory:
```
systems/my-business/R-routines/skills/
  content-pipeline.yaml
  competitor-analysis.yaml
  meeting-prep.yaml
```

Skills are loaded automatically. Use `/reload` (Telegram) or POST `/api/systems/reload` to pick up changes.
