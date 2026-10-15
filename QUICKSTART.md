# RealizeOS V5 — Quickstart

> From zero to running in under 10 minutes.

## Prerequisites

- **Docker** and **Docker Compose** installed ([Get Docker](https://docs.docker.com/get-docker/))
- One LLM provider is enough: an API key (`ANTHROPIC_API_KEY`, `GOOGLE_AI_API_KEY` or `OPENAI_API_KEY`), or a local [Ollama](https://ollama.com) with no key

## Step 1: Clone

```bash
git clone https://github.com/SufZen/RealizeOS-5.git
cd RealizeOS-5
```

## Step 2: Configure

```bash
cp .env.example .env
```

Open `.env` and set any one provider (more than one is fine):

```bash
ANTHROPIC_API_KEY=<your-anthropic-api-key>
# or
GOOGLE_AI_API_KEY=<your-google-ai-api-key>
# or
OPENAI_API_KEY=<your-openai-api-key>
# or a local model, no key:
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

Every feature works on every provider. To choose which one is tried first, or the model for each task size, see [LLM Routing](docs/configuration.md#llm-routing).

## Step 3: Launch

```bash
docker compose up --build
```

Wait for the output:

```
realize-api    | INFO: Application startup complete.
realize-api    | INFO: Uvicorn running on http://0.0.0.0:8080
```

## Step 4: Open Dashboard

Open your browser to **http://localhost:8080**

The dashboard shows:
- 🏢 **Ventures** — Your business configurations
- 🤖 **Agents** — AI team members
- 📊 **Activity Feed** — Real-time agent actions

## Step 5: Send Your First Message

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Help me plan Q2 strategy", "system_key": "consulting"}'
```

Or use the dashboard chat interface directly.

## Step 6: Initialize a Venture Template

```bash
# Inside the container, or locally with Python:
realize-os init --template consulting
```

Available templates: `consulting`, `agency`, `portfolio`, `saas`, `ecommerce`, `accounting`, `coaching`, `freelance`

> 💡 **Tip:** Use `realize-os setup` for an interactive wizard that handles configuration, dashboard setup, and template selection in one step.

---

## Without Docker (Manual Setup)

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate    # macOS/Linux
venv\Scripts\activate       # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env — set any one LLM provider (a key, or a local Ollama)

# 4. Start the server
realize-os serve
```

Dashboard: http://localhost:8080 (built static) · Vite dev: http://localhost:5173 · API: http://localhost:8080

> 🔧 **Troubleshooting:** Run `realize-os doctor` to diagnose installation issues.

---

## What's Next?

- 📖 [Architecture Overview](docs/architecture.md) — Understand FABRIC and the engine
- 🛠️ [Configuration Guide](docs/configuration.md) — Customize your setup
- 🏗️ [Self-Hosting Guide](docs/self-hosting-guide.md) — Production deployment
- 🛡️ [API Reference](docs/api-reference.md) — Full REST API documentation
- 🤝 [Contributing](CONTRIBUTING.md) — Join the community
