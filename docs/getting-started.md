# Getting Started with RealizeOS

RealizeOS is an AI operations system that gives you a coordinated team of AI agents, each with specialized roles, working from your knowledge base.

## Choose Your Edition

### Lite Edition (Obsidian + Claude Code)
Best for: Non-technical users, solopreneurs, small teams.

**Requirements:** Obsidian (free) + Claude Pro subscription ($20/mo)

**Setup time:** 15 minutes

1. Download and unzip the `realize_lite/` folder
2. Open it as an Obsidian vault
3. Follow the in-vault `setup-guide.md`
4. Open Claude Code in the vault directory — Claude reads your CLAUDE.md and becomes your AI team

See [Lite Guide](lite-guide.md) for the full walkthrough.

### Full Edition (Docker Self-Hosted)
Best for: Technical users, teams, businesses wanting the complete engine.

**Requirements:** Python 3.11+, Docker (optional), API keys for LLM providers

**Setup time:** 30 minutes

```bash
# 1. Download, unzip, and install
cd realize-os
pip install -r requirements.txt

# 2. Initialize from a template
python cli.py init --template consulting

# 3. Configure
cp .env.example .env
# Edit .env with your API keys

# 4. Start the API server
python cli.py serve
```

See [Full Guide](full-guide.md) for the complete walkthrough.

> **Tip:** You can also use the Venture Wizard in the Lite vault's `shared/venture-worksheet.md` to quickly define your venture identity and voice, then copy the generated files into your Full system's `F-foundations/` directory.

## Core Concepts

### Systems
A system represents a venture, business, or project. Each system has its own agents, knowledge base, venture voice, and workflows. One RealizeOS instance can run 1 or many systems.

### FABRIC Directories
Each system's knowledge base follows the FABRIC structure:
- **F-foundations/** — Venture identity, voice guidelines, core standards
- **A-agents/** — Agent definitions (who does what)
- **B-brain/** — Domain knowledge, market data, research
- **R-routines/** — Skills, workflows, state maps, SOPs
- **I-insights/** — Memory, learning log, feedback, decisions
- **C-creations/** — Deliverables and outputs

### Agents
Agents are AI team members with specialized roles. Each agent is defined by a markdown file that describes their expertise, personality, and working methods. The system automatically routes messages to the right agent.

Default agents:
- **Orchestrator** — General coordinator and router
- **Writer** — Content creation specialist
- **Reviewer** — Quality gatekeeper with scoring framework
- **Analyst** — Research, strategy, and data analysis

### Skills
Skills are YAML-defined workflows that chain multiple steps together:
- **v1 skills** — Simple trigger → agent pipeline (e.g., "write a post" → writer → reviewer)
- **v2 skills** — Multi-step workflows with tools, conditions, and human-in-the-loop steps

### Multi-LLM Routing
RealizeOS automatically routes each request to the optimal AI model based on task complexity. Default routing:
- Simple/quick tasks → Gemini Flash (fast, cheap)
- Content/reasoning → Claude Sonnet (balanced)
- Complex/strategic → Claude Opus (powerful)

The provider registry supports Claude, Gemini, OpenAI, and Ollama. Available providers are auto-discovered at startup — configure any combination via API keys in `.env`.

## Quick API Test

After starting the server:

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Help me draft a strategy for Q2",
    "system_key": "consulting",
    "user_id": "test-user"
  }'
```

## Next Steps

- [Concepts Deep Dive](concepts.md)
- [Configuration Guide](configuration.md)
- [Skill Authoring Guide](skill-authoring.md)
- [API Reference](api-reference.md)
