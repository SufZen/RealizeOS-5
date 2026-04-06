# Agent Routing Guide — Real Estate

This directory contains your AI agent team specialized for real estate operations.

## How Routing Works

| Request Type | Primary Agent | Backup |
|---|---|---|
| Property listings (write, optimize) | Listing Specialist | Reviewer |
| Market analysis (CMA, pricing) | Market Analyst | Orchestrator |
| Deal evaluation (ROI, feasibility) | Deal Analyst | Orchestrator |
| Content creation (blogs, social) | Writer | Reviewer |
| Quality review | Reviewer | Writer |
| Operations (clients, docs, deadlines) | Operations | Orchestrator |
| Planning & coordination | Orchestrator | — |

## Available Agents

- **orchestrator** — Routes requests, coordinates multi-agent workflows, maintains project context
- **listing-specialist** — Creates and optimizes property listings for portals and marketing
- **market-analyst** — Comparative market analysis, price trends, area reports
- **deal-analyst** — Investment feasibility, ROI/IRR analysis, worst-case modeling
- **writer** — Content creation (blogs, newsletters, social, email campaigns)
- **reviewer** — Quality control for all publishable content
- **operations** — Client management, document tracking, deadline monitoring

## Adding New Agents

Create a new `.md` file following the format of existing agents. The agent will be auto-discovered on restart.
