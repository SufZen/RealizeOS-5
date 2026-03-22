# Full Edition Guide

RealizeOS Full is a self-hosted AI operations engine with multi-LLM routing, REST API, Telegram integration, and a self-evolution system.

## Requirements

- Python 3.11+
- Docker (optional, for containerized deployment)
- API key for at least one LLM provider (Anthropic, Google AI, OpenAI, or Ollama)

## Installation

```bash
# 1. Download and unzip the Full package
cd realize-os

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize from a template
python cli.py init --template consulting
```

Available templates: `consulting`, `agency`, `portfolio`, `saas`, `ecommerce`, `accounting`, `coaching`, `freelance`

## Configuration

```bash
# Copy the environment template
cp .env.example .env
```

Edit `.env` with your API keys (at least one LLM provider required):
- `ANTHROPIC_API_KEY` — enables Claude Sonnet and Opus
- `GOOGLE_AI_API_KEY` — enables Gemini Flash
- `OPENAI_API_KEY` — enables GPT-4o models
- `OLLAMA_BASE_URL` — enables local Ollama models (no API key needed)
- `TELEGRAM_BOT_TOKEN` — optional, enables Telegram channel
- `BRAVE_API_KEY` — optional, enables web search

The provider registry auto-discovers available providers at startup. You can use any combination — the router will use what's available and fall back gracefully.

See [Configuration Guide](configuration.md) for all options.

## Running

### Local Development

```bash
python cli.py serve                    # Start API on localhost:8080
python cli.py serve --port 3000       # Custom port
python cli.py serve --reload          # Auto-reload on code changes
```

### Docker Deployment

```bash
docker compose up                      # Start all services
docker compose up -d                   # Detached mode
```

### Telegram Bot

```bash
python cli.py bot                      # Start Telegram bot
```

## Managing Ventures

```bash
python cli.py venture list                              # List all ventures
python cli.py venture create --key my-saas --name "My SaaS"  # Create new
python cli.py venture delete --key my-saas --confirm my-saas  # Delete (requires confirmation)
```

New ventures get a complete FABRIC directory structure with template agents, skills, and knowledge base files. They're immediately available to the engine via auto-discovery.

## CLI Reference

```bash
python cli.py init --template NAME    # Initialize from template
python cli.py serve [--port PORT]     # Start API server
python cli.py bot                     # Start Telegram bot
python cli.py status                  # Show system status
python cli.py index                   # Rebuild KB search index
python cli.py venture create          # Create a new venture
python cli.py venture delete          # Delete a venture
python cli.py venture list            # List all ventures
```

## API Quick Test

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Help me plan Q2 strategy", "system_key": "consulting"}'
```

## Next Steps

- [Core Concepts](concepts.md)
- [Configuration Guide](configuration.md)
- [Skill Authoring Guide](skill-authoring.md)
- [API Reference](api-reference.md)
