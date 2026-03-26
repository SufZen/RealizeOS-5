# RealizeOS V5 — Quickstart

> From zero to running in under 10 minutes.

## Prerequisites

- **Docker** and **Docker Compose** installed ([Get Docker](https://docs.docker.com/get-docker/))
- At least one LLM API key: `ANTHROPIC_API_KEY` or `GOOGLE_AI_API_KEY`

## Step 1: Clone

```bash
git clone https://github.com/SufZen/RealizeOS-5.git
cd RealizeOS-5
```

## Step 2: Configure

```bash
cp .env.example .env
```

Open `.env` and add your API key(s):

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
# and/or
GOOGLE_AI_API_KEY=AIza-your-key-here
```

## Step 3: Launch

```bash
docker compose up
```

Wait for the output:

```
realize-api    | INFO: Application startup complete.
realize-api    | INFO: Uvicorn running on http://0.0.0.0:8080
```

## Step 4: Open Dashboard

Open your browser to **http://localhost:3000**

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
python cli.py init --template consulting
```

Available templates: `consulting`, `agency`, `portfolio`, `saas`, `ecommerce`, `accounting`, `coaching`, `freelance`

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
# Edit .env — add your API key(s)

# 4. Start the server
python cli.py serve
```

Dashboard: http://localhost:3000 · API: http://localhost:8080

---

## What's Next?

- 📖 [Architecture Overview](docs/architecture.md) — Understand FABRIC and the engine
- 🛠️ [Configuration Guide](docs/configuration.md) — Customize your setup
- 🏗️ [Self-Hosting Guide](docs/self-hosting-guide.md) — Production deployment
- 🤝 [Contributing](CONTRIBUTING.md) — Join the community
