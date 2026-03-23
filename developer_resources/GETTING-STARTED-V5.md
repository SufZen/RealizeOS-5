# RealizeOS 5 — Getting Started Guide

## What You Have

RealizeOS 5 is a complete AI operations engine with a visual dashboard. It includes:

- **Python backend** (FastAPI) — handles AI agent orchestration, LLM routing, skills, memory
- **React dashboard** — see what your agents are doing, manage ventures, approve actions
- **SQLite database** — tracks activity events, agent states, approval queue
- **FABRIC knowledge base** — file-based structure (Foundations, Agents, Brain, Routines, Insights, Creations)

## Prerequisites

- **Python 3.11+** with pip
- **Node.js 18+** with pnpm (optional — needed for the dashboard)
- **API keys** — at least one of: `ANTHROPIC_API_KEY`, `GOOGLE_AI_API_KEY`

## Quick Setup (Recommended)

Run the interactive setup wizard — it handles everything in one command:

```bash
cd RealizeOS
python cli.py setup
```

The wizard will:
1. Check prerequisites and install Python dependencies
2. Ask for your business name, template, and API keys
3. Initialize the project (config, FABRIC structure, .env)
4. Verify the installation
5. Optionally install and build the dashboard

After it finishes, just run:

```bash
python cli.py serve
```

Then open **http://localhost:8080** in your browser.

To diagnose issues with an existing installation:

```bash
python cli.py doctor
```

## Manual Setup (Advanced)

If you prefer to set things up manually:

### 1. Install Python dependencies

```bash
cd RealizeOS
pip install -r requirements.txt
```

### 2. Configure your environment

```bash
cp .env.example .env
# Edit .env — add your API keys:
#   ANTHROPIC_API_KEY=sk-ant-...
#   GOOGLE_AI_API_KEY=AI...
```

### 3. Initialize from a template

```bash
python cli.py init --template consulting
```

This creates a `systems/consulting/` directory with the full FABRIC structure, pre-configured agents (orchestrator, writer, reviewer, analyst), and skill definitions.

### 4. Start the API server

```bash
python cli.py serve --port 8080
```

You should see:

```
INFO:     RealizeOS API starting up...
INFO:     Loaded config from realize-os.yaml: 1 system(s)
INFO:     Operational database initialized
INFO:     RealizeOS API ready — 1 system(s) loaded
INFO:     Uvicorn running on http://0.0.0.0:8080
```

### 5. Start the dashboard (dev mode)

In a second terminal:

```bash
cd dashboard
pnpm install
pnpm dev
```

You should see:

```
VITE v8.0.0  ready in 200ms
➜  Local:   http://localhost:5173/
```

Open **http://localhost:5173** in your browser.

## What You'll See in the Dashboard

### Overview Page (`/`)
- **Stat cards** — venture count, total agents, running agents, errors
- **Venture cards** — click any venture to see its detail
- **Recent activity feed** — the last 20 events across all ventures

### Ventures Page (`/ventures`)
- List of all configured ventures with agent/skill counts
- Click a venture to drill in

### Venture Detail (`/ventures/{key}`)
- **FABRIC grid** — shows which directories exist and how many files are in each (F/A/B/R/I/C)
- **Org chart** — if agents have `reports_to` in their frontmatter, you'll see the hierarchy
- **Agent list** — each agent with live status (idle/running/paused/error)
- **Skill list** — YAML skills with version and task type

### Agent Detail (`/ventures/{key}/agents/{id}`)
- **Status card** — current status, last run time, schedule, next run countdown
- **Pause/Resume** — click to pause an agent (it'll be skipped during message routing)
- **Schedule editor** — set interval (seconds) or cron expression for heartbeats
- **Configuration** — the raw `.md` file defining this agent
- **Action history** — recent activity events for this agent

### Activity Page (`/activity`)
- Full chronological event log
- **Filters** — by venture, agent, or action type
- **Live updates** — new events appear via SSE with a "new" badge

### Evolution Inbox (`/evolution`)
- Pending suggestions from the self-evolution engine
- Approve (applies the change) or Dismiss with one click
- Shows risk level, priority, and source

### Approvals (`/approvals`)
- Pending approval requests from gated agent actions
- Approve or Reject with optional decision notes
- Appears when agents try to send emails, publish content, etc.

## Testing the API Directly

```bash
# Send a chat message
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Help me plan Q2 strategy", "system_key": "consulting"}'

# Get dashboard overview
curl http://localhost:8080/api/dashboard

# List ventures
curl http://localhost:8080/api/ventures

# Get venture detail
curl http://localhost:8080/api/ventures/consulting

# Get agents with status
curl http://localhost:8080/api/ventures/consulting/agents

# Get activity feed
curl http://localhost:8080/api/ventures/consulting/activity

# Pause an agent
curl -X POST http://localhost:8080/api/ventures/consulting/agents/writer/pause

# Resume
curl -X POST http://localhost:8080/api/ventures/consulting/agents/writer/resume

# Set a schedule (every 5 minutes)
curl -X PUT http://localhost:8080/api/ventures/consulting/agents/writer/schedule \
  -H "Content-Type: application/json" \
  -d '{"schedule_interval_sec": 300}'
```

## Feature Flags

Control new features in `realize-os.yaml`:

```yaml
features:
  activity_log: true        # Log all agent actions to SQLite
  agent_lifecycle: true     # Track agent status (idle/running/paused/error)
  heartbeats: true          # Enable scheduled agent runs
  approval_gates: true      # Require human approval for consequential actions

governance:
  gates:
    send_email: true
    publish_content: true
    external_api: true
    create_event: false
    high_cost_llm: false
```

## CLI Commands

```bash
python cli.py init --template consulting  # Initialize from template
python cli.py serve --port 8080           # Start API server
python cli.py status                      # Show system status
python cli.py venture create --key my-biz # Create new venture
python cli.py venture list                # List ventures
python cli.py venture delete --key my-biz # Delete venture
python cli.py index                       # Rebuild KB search index
python cli.py bot                         # Start Telegram bot
```

## Production Build

To serve the dashboard from FastAPI (single deployment):

```bash
cd dashboard
pnpm build    # Outputs to ../static/
```

The FastAPI server will serve the built dashboard from the `static/` directory automatically. No separate frontend server needed.

## Project Structure

```
RealizeOS/
├── cli.py                    # CLI entry point
├── realize-os.yaml           # System configuration
├── realize_core/             # Python engine
│   ├── base_handler.py       # Message processing pipeline
│   ├── activity/             # Activity logging + event bus
│   ├── scheduler/            # Agent lifecycle + heartbeats + hierarchy
│   ├── governance/           # Approval gates
│   ├── plugins/              # Plugin loader + venture export/import
│   ├── db/                   # SQLite schema + migrations
│   ├── llm/                  # Multi-LLM routing (Claude, Gemini, OpenAI, Ollama)
│   ├── prompt/               # Multi-layer prompt assembly
│   ├── skills/               # Skill detection + execution
│   └── ...                   # memory, kb, tools, channels, evolution, pipeline
├── realize_api/              # FastAPI REST API (34 routes)
├── dashboard/                # React 19 + Vite + TypeScript + Tailwind
│   └── src/
│       ├── pages/            # 7 page components
│       ├── components/       # Shared UI components
│       └── lib/              # API client, utilities
├── tests/                    # 605 tests (pytest)
└── static/                   # Dashboard production build
```
