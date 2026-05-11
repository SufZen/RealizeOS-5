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

### Full Edition Setup

1. Clone the repository
2. Copy `.env.example` to `.env` and add your API keys
3. Run `realize-os setup` (interactive wizard) or `realize-os init --template consulting`
4. Start: `realize-os serve`
5. Open http://localhost:8080

> 💡 **Tip:** Use `realize-os doctor` to diagnose any installation issues.

> 📖 Full setup: [QUICKSTART.md](../QUICKSTART.md) | [Self-Hosting Guide](self-hosting-guide.md)
> 🐳 Docker: [QUICKSTART.md](../QUICKSTART.md#step-1-pull--run)

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

Specialized AI agents handle different aspects of your business:
- Each agent has a SOUL persona, defined scope, preferred tools, and output format. Each agent is defined by a markdown file that describes their expertise, personality, and working methods. The system automatically routes messages to the right agent.

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

RealizeOS routes to different models based on task complexity:
- **Flash** (Gemini) — Fast responses for simple queries
- **Strategy** (Claude Sonnet) — Planning and strategic tasks
- **Opus** (Claude Opus) — Complex reasoning and advanced problem-solving

The provider registry supports Claude, Gemini, OpenAI, and Ollama. Available providers are auto-discovered at startup — configure any combination via API keys in `.env`.

## Quick API Test

Quick test via the CLI (5.1.0+):

```bash
realize-os chat "Hello!" --system consulting
```

Or via the REST API:

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"message": "Hello!", "system_key": "consulting"}'
```

## Enable the MCP Server

RealizeOS 5.1.0 includes a built-in MCP server that lets Claude Desktop, Cursor, or any MCP client use your instance as an AI second brain.

```bash
# Enable and start
realize-os config set mcp.enabled true
realize-os mcp serve --port 8080

# Issue a token for your MCP client
realize-os mcp token --user owner
```

Copy the token into your MCP client config (e.g., Claude Desktop’s `mcpServers` block). See [MCP Server Reference](mcp-server.md) for integration recipes.

## Next Steps

- [Concepts Deep Dive](concepts.md)
- [Configuration Guide](configuration.md)
- [CLI Reference](cli-reference.md)
- [MCP Server Reference](mcp-server.md)
- [Skill Authoring Guide](skill-authoring.md)
- [API Reference](api-reference.md)
