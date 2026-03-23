# RealizeOS V5 — Setup Guide

> **Two ways to use RealizeOS V5**: Use the **Dashboard** (browser UI) for visual management. Use the **CLI** for power-user operations. Both connect to the same engine and knowledge base.

> **Interactive version**: For a step-by-step checklist with copy-paste instructions, visit [realizeos.ai/setup](https://realizeos.ai/setup).

Welcome to RealizeOS V5. This guide takes you from zero to a working AI operations team in about 15 minutes.

---

## What You Need

- [ ] **Python** 3.11+ — [python.org](https://python.org)
- [ ] **At least one LLM API key** — Anthropic (Claude) and/or Google (Gemini)
- [ ] **This repository** — the folder you're reading this from
- [ ] **Node.js** 20+ (optional) — only needed for dashboard development

---

## Step 1: Install Dependencies

> [!info] ~2 minutes

### Option A: Use the Installer (Windows)

Double-click **`Install-RealizeOS.bat`**. It will:
1. Install Python dependencies from `requirements.txt`
2. Create the `.env` file from `.env.example`
3. Build the dashboard (requires Node.js)
4. Create a desktop shortcut
5. Open the User Guide

### Option B: Manual Install

```bash
# Clone the repository
git clone https://github.com/SufZen/RealizeOS-5.git
cd RealizeOS-5

# Install Python dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY and/or GOOGLE_AI_API_KEY
```

- [ ] Done — dependencies are installed

---

## Step 2: Configure API Keys

> [!info] ~2 minutes

Edit `.env` and add at least one API key:

```bash
ANTHROPIC_API_KEY=sk-ant-...        # Claude models
GOOGLE_AI_API_KEY=AI...             # Gemini models
```

Optional keys for additional functionality:

| Variable | Purpose |
| --- | --- |
| `REALIZE_API_KEY` | Protect the API with a bearer token |
| `TELEGRAM_BOT_TOKEN` | Enable Telegram bot channel |
| `BRAVE_API_KEY` | Enable web search tool |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Workspace integration |

- [ ] Done — at least one API key is set

---

## Step 3: Initialize from a Business Template

> [!info] ~1 minute

```bash
python cli.py init --template consulting
```

**Available templates:**

| Template | Best for |
| --- | --- |
| `consulting` | Solo consultants, advisory firms |
| `agency` | Creative / marketing agencies |
| `portfolio` | Multi-venture operators |
| `saas` | SaaS founders, product teams |
| `ecommerce` | Online stores, D2C ventures |
| `accounting` | Accountants, bookkeepers |
| `coaching` | Business/life coaches |
| `freelance` | Developers, designers, writers |

- [ ] Done — template initialized

---

## Step 4: Define Your Venture Identity

> [!info] ~5-10 minutes | Choose ONE of the two options below

### Option A (recommended): Use the Venture Wizard on the website

1. Go to **[realizeos.ai/venture-worksheet](https://realizeos.ai/venture-worksheet)**
2. Complete the guided form (4 steps)
3. Download or copy the generated files into `systems/my-business-1/F-foundations/`

### Option B: Fill in the files directly

1. Open **`shared/identity.md`** and fill in your personal info
2. Open **`shared/venture-worksheet.md`** — answer the guided questions
3. Run: `python cli.py init` to generate the foundation files

> [!tip] Most impactful thing you can do
> Paste a real example of writing that sounds exactly like your venture into the **Good Example** section of `venture-voice.md`. This calibrates the AI better than anything else.

- [ ] Done — identity and venture files are filled in

---

## Step 5: Start the System

```bash
# Start the API + Dashboard
python cli.py serve

# Dashboard opens at http://localhost:8080
```

### What to Try First

```text
"Write a LinkedIn post about [topic]"        → Writer activates
"Analyze [competitor / market / opportunity]" → Analyst activates
"Review this draft: [paste your text]"        → Reviewer activates
"Help me plan [project]"                      → Orchestrator breaks it down
"What are my current priorities?"             → Reads state map
```

- [ ] Done — system is running

---

## Step 6: Configure Storage & Backup (Optional)

> [!info] ~3 minutes

By default, RealizeOS stores everything locally. To enable cloud backup:

1. Open the Dashboard → **Settings** → **Storage & Backup**
2. Select a cloud provider (AWS S3, MinIO, DigitalOcean Spaces, Backblaze B2, Cloudflare R2)
3. Enter your credentials and test the connection
4. Enable sync

Or configure via `.env`:
```bash
STORAGE_PROVIDER=s3
S3_BUCKET=my-realizeos-backup
S3_REGION=us-east-1
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
```

---

## Step 7: Enable Developer Mode (Optional, Advanced)

> [!warning] Only for users who want to use AI coding tools on the RealizeOS codebase itself.

Developer Mode allows integration with local AI coding clients (Claude Code, Gemini CLI, VS Code Copilot, Cursor, etc.) for system development and extension authoring.

```bash
# Generate context files for your AI tools
python cli.py devmode setup

# Create a safety snapshot before modifying
python cli.py devmode snapshot --label "before session"

# Run health check after modifications
python cli.py devmode check
```

You can also enable it from **Dashboard → Settings → Advanced Developer Settings**.

> [!info] See the [User Guide](docs/user-guide.html#devmode) for full Developer Mode documentation including protection levels, supported tools, and safety workflows.

---

## Ongoing Usage

### Keep the State Map Updated

`systems/my-business-1/R-routines/state-map.md` — update it with current priorities, active projects, and pipeline items. The AI reads this for context.

### Grow Your Brain

Add to `systems/my-business-1/B-brain/` as you learn things: market notes, client feedback, competitive intelligence, new domain knowledge.

### Review Your Insights

`systems/my-business-1/I-insights/learning-log.md` — the AI logs what worked and what didn't. Review periodically to improve workflows.

### Find Your Outputs

All AI-generated content is saved in the active system's `C-creations/` with descriptive filenames.

---

## Running Multiple Ventures

Your workspace comes with 3 venture slots out of the box. Each has its own FABRIC directory structure — completely isolated agents, venture voice, knowledge, and outputs.

**To activate a new venture:**
1. Rename the folder to match your venture (e.g., `systems/consulting-practice/`)
2. Fill in the FABRIC files for the new venture
3. Uncomment (or add) the matching system entry in `realize-os.yaml`

**Or simply ask:** *"Create a new venture called [name]"* — the AI will set up the directory structure and config for you.

**To remove a venture:** Ask *"Remove venture [name]"* — the AI will confirm before deleting.

---

## Updating & Maintenance

```bash
# Update to the latest version (Windows)
Update-RealizeOS.bat

# Migrate data from a previous installation
Migrate-RealizeOS.bat

# Uninstall cleanly (removes shortcut + installation directory)
Uninstall-RealizeOS.bat
```

---

## CLI Quick Reference

```bash
python cli.py serve [--port PORT]                # Start API + dashboard
python cli.py init --template NAME               # Initialize from template
python cli.py bot                                # Start Telegram bot
python cli.py status                             # Show system status
python cli.py index                              # Rebuild KB search index
python cli.py venture create --key KEY           # Create new venture
python cli.py venture delete --key KEY           # Delete venture
python cli.py venture list                       # List ventures
python cli.py setup-google                       # Google OAuth setup
python cli.py devmode setup [--tools ...]        # Generate AI tool context files
python cli.py devmode check [--quick]            # Run health check
python cli.py devmode scaffold --type TYPE       # Scaffold new extension
python cli.py devmode snapshot [--label MSG]     # Create git snapshot
python cli.py devmode rollback [--tag TAG]       # Rollback to snapshot
python cli.py devmode diff                       # Show changes since snapshot
python cli.py devmode status                     # Developer Mode status
```

---

## Need Help?

- Browse the **Dashboard → Docs** page for in-app documentation
- Open `docs/user-guide.html` for the comprehensive interactive guide
- Read `self-hosting-guide.md` for Docker deployment
- Ask your AI: *"How does this system work?"* — it understands the whole structure
- Support: [realizeos@realization.co.il](mailto:realizeos@realization.co.il)
