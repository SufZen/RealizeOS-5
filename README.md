# RealizeOS

**The AI operations system for your business.**

RealizeOS gives you a coordinated team of AI agents that understand your venture, remember your preferences, and execute multi-step workflows — not just another chatbot.

## Two Editions

### Lite (Obsidian + Claude Code) — $79
For operators who want AI assistance without servers or coding.

- Pre-structured knowledge base using the FABRIC system
- 4 agent templates (Orchestrator, Writer, Reviewer, Analyst)
- Venture voice and identity wizards (fill-in-the-blank)
- Skill workflows (YAML-defined pipelines)
- Works with Claude Code or Claude Desktop
- **Get started in 15 minutes**

### Full (Docker Self-Hosted) — $249

For technical users who want the complete engine.

- Multi-LLM routing with provider registry (Claude, Gemini, OpenAI, Ollama)
- Multi-layer dynamic prompt assembly from living knowledge base
- Hybrid KB search (FTS5 + vector embeddings)
- Multi-step skill executor (agent, tool, condition, human workflows)
- Creative pipelines with session management
- Tool integrations: Google Workspace (13 tools), web search, browser automation, MCP
- REST API + Telegram channels
- Self-evolution engine (gap detection, skill suggestion, prompt refinement)
- 8 system templates + CLI tooling (including venture management)
- **Deploy with one command:** `docker compose up`

## Quick Start — Lite Edition

```bash
# 1. Download and unzip the Lite package

# 2. Open the folder as an Obsidian vault
#    Obsidian → "Open folder as vault" → select the unzipped folder

# 3. Follow the in-vault setup guide (setup-guide.md)
#    Fill in: venture identity, voice rules, agent tweaks (15 min)

# 4. Start working with Claude
#    Open Claude Code in the vault directory
#    Claude reads CLAUDE.md and becomes your AI team
```

## Quick Start — Full Edition

```bash
# 1. Download, unzip, and install
cd realize-os
pip install -r requirements.txt

# 2. Initialize from a template
python cli.py init --template consulting

# 3. Configure API keys
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY and/or GOOGLE_AI_API_KEY

# 4a. Run locally
python cli.py serve

# 4b. Or deploy with Docker
docker compose up
```

**Test it:**

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Help me plan Q2 strategy", "system_key": "consulting"}'
```

## The FABRIC System

Every system's knowledge base follows the FABRIC directory structure:

| Directory | Purpose |
| --- | --- |
| **F**-foundations/ | Venture identity, voice rules, core standards |
| **A**-agents/ | Agent team definitions and routing guide |
| **B**-brain/ | Domain knowledge, market data, expertise |
| **R**-routines/ | Skills, workflows, state maps, SOPs |
| **I**-insights/ | Memory: learning log, feedback, decisions |
| **C**-creations/ | Output: deliverables, drafts, final assets |

## Architecture

```
User Message
    │
    ▼
┌─────────────────┐
│  Channel Layer   │  API / Telegram / CLI
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  Base Handler    │  Session → Skill → Agent routing
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  LLM Router      │  Task classification → model selection
│  Simple → Flash   │  Content → Sonnet  │  Complex → Opus
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  Prompt Builder   │  Multi-layer assembly from KB files
│  Identity → Vent. │  → Agent → RAG Context → Memory
│  → Session →      │  Proactive → Channel Format
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  Tools           │  Google (13) / Web / Browser / MCP
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  Evolution       │  Track → Detect gaps → Suggest skills
└─────────────────┘
```

## Templates

Pre-built system configurations:

| Template | Best For |
| --- | --- |
| `consulting` | Solo consultants, advisory firms |
| `agency` | Creative/marketing agencies |
| `portfolio` | Multi-venture operators |
| `saas` | SaaS founders, product teams |
| `ecommerce` | Online stores, D2C ventures |
| `accounting` | Accountants, bookkeepers, tax advisors |
| `coaching` | Business/life coaches, course creators |
| `freelance` | Freelance developers, designers, writers |

```bash
python cli.py init --template agency
```

## CLI Commands

```bash
python cli.py init --template NAME    # Initialize from template
python cli.py serve --port 8080       # Start API server
python cli.py bot                     # Start Telegram bot
python cli.py status                  # Show system status
python cli.py index                   # Rebuild KB search index
python cli.py venture create --key X  # Create a new venture
python cli.py venture delete --key X  # Delete a venture
python cli.py venture list            # List all ventures
```

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/chat` | Send message, get AI response |
| GET | `/api/systems` | List all systems |
| GET | `/api/systems/{key}` | System details |
| GET | `/api/systems/{key}/agents` | List agents |
| GET | `/api/systems/{key}/skills` | List skills |
| POST | `/api/systems/reload` | Hot-reload config |
| GET | `/health` | Health check |
| GET | `/status` | Detailed status |

## Documentation

- [Getting Started](docs/getting-started.md)
- [Core Concepts](docs/concepts.md)
- [Configuration Guide](docs/configuration.md)
- [Lite Guide](docs/lite-guide.md)
- [Full Guide](docs/full-guide.md)
- [Skill Authoring Guide](docs/skill-authoring.md)
- [API Reference](docs/api-reference.md)

## License

Core engine: MIT License
