# Agent Routing Guide

> **Path note**: All paths referenced in agent and skill files are relative to the system directory they belong to. For example, `F-foundations/venture-voice.md` means `systems/my-business-2/F-foundations/venture-voice.md`.

This file helps Claude (or any AI) decide which agent to activate based on the user's request.

## Available Agents

| Agent | File | Handles |
| --- | --- | --- |
| Orchestrator | `orchestrator.md` | General coordination, planning, multi-step tasks, unclear requests |
| Writer | `writer.md` | Content creation, copywriting, communications, social media |
| Reviewer | `reviewer.md` | Quality review, venture compliance, editing, feedback |
| Analyst | `analyst.md` | Research, data analysis, strategy, market intelligence |

## Routing Rules

**Default**: If no clear match, use the **Orchestrator**. It will delegate to specialists as needed.

**By request type:**

- Content / writing / posts / emails / copy → **Writer**
- Review / check / edit / improve / proofread → **Reviewer**
- Research / analyze / compare / data / strategy → **Analyst**
- Plan / organize / coordinate / "help me with..." → **Orchestrator**

**Pipeline patterns** (multi-agent workflows):

- Content creation: Writer → Reviewer
- Strategy deliverable: Analyst → Writer → Reviewer
- General task: Orchestrator (delegates as needed)

## How to Switch Agents

When the task changes mid-conversation, announce the switch:
> "Switching to [Agent Name] — this task requires [their expertise]."

If a pipeline is active, follow the defined sequence before switching.

## Recommended Team Size

Start with the 4 default agents above. As your system matures, add specialists:

- **6-10 agents** is the sweet spot for most businesses
- **Maximum ~20 agents** — beyond this, routing becomes noisy and flows get harder to maintain
- Add an agent when you notice a specific, recurring gap (e.g., you need SEO-specific writing that the Writer doesn't cover well enough)
- When possible, merge overlapping roles rather than adding new ones

## Common Additional Agents

| Agent | Good For |
| --- | --- |
| Social Media Manager | Platform-specific content (LinkedIn, Twitter/X, Instagram) |
| Email Marketer | Nurture sequences, newsletters, outreach campaigns |
| SEO Specialist | Keyword research, content optimization, meta descriptions |
| Customer Support | FAQ responses, ticket templates, help articles |
| Sales Copywriter | Landing pages, ads, conversion-focused copy |
| Project Manager | Timelines, milestone tracking, status reports |

To add a new agent, create a markdown file in this folder (e.g., `seo-specialist.md`) following the same structure as the existing agents, then add a routing entry to the table above.
