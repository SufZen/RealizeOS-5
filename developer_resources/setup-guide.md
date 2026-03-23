# RealizeOS Lite — Setup Guide

> **Two tools, one workspace**: Use **Obsidian** to browse and edit your knowledge base visually. Use **Claude Code** (or Claude Desktop) to run AI operations. Both read from the same folder.

> **Interactive version**: For a step-by-step checklist with copy-paste instructions, visit [realizeos.ai/setup](https://realizeos.ai/setup).

Welcome to RealizeOS. This guide takes you from zero to a working AI operations team in about 15 minutes.

---

## What You Need

- [ ] **Obsidian** (free) — [obsidian.md](https://obsidian.md)
- [ ] **Claude Code** (CLI) or **Claude Pro** subscription
- [ ] This vault — the folder you're reading this from

---

## Step 1: Open This Vault in Obsidian

> [!info] ~2 minutes

1. Open Obsidian
2. Click **Open folder as vault**
3. Select the extracted RealizeOS folder (the one containing this file and the `systems/` directory)
4. Confirm you can see `systems/`, `shared/`, `CLAUDE.md`, and `setup-guide.md` in the sidebar. Navigate into `systems/my-business-1/` to find your FABRIC folders: `F-foundations`, `A-agents`, `B-brain`, `R-routines`, `I-insights`, `C-creations`

- [ ] Done — I can see the folder structure in the sidebar

---

## Step 2: Define Who You Are & Your Venture

> [!info] ~5-10 minutes | Choose ONE of the two options below

### Option A (recommended): Use the Venture Wizard on the website

1. Go to **[realizeos.ai/venture-worksheet](https://realizeos.ai/venture-worksheet)**
2. Complete the guided form (4 steps)
3. Download or copy the 3 generated files:
   - `identity.md` → place in `shared/`
   - `venture-identity.md` → place in `systems/my-business-1/F-foundations/`
   - `venture-voice.md` → place in `systems/my-business-1/F-foundations/`

### Option B: Fill in the files directly in the vault

1. Open **`shared/identity.md`** and fill in your personal info
2. Open **`shared/venture-worksheet.md`** — answer the guided questions
3. Ask your AI: *"Read my completed venture worksheet at `shared/venture-worksheet.md` and generate `venture-identity.md` and `venture-voice.md` in `systems/my-business-1/F-foundations/`."*

> [!warning] Choose ONE option, not both. The Venture Wizard and the venture worksheet produce the same files.

> [!tip] Most impactful thing you can do
> Paste a real example of writing that sounds exactly like your venture into the **Good Example** section of `venture-voice.md`. This calibrates the AI better than anything else.

- [ ] Done — identity and venture files are filled in

---

## Step 3: Customize Your Agent Team (Optional)

> [!info] ~3 minutes | Skip this on your first day — the defaults work well

Browse **`systems/my-business-1/A-agents/`** — you have four agents out of the box:

| Agent | What It Does |
| --- | --- |
| **Orchestrator** | General coordination, planning, multi-step tasks |
| **Writer** | Content creation, copywriting, communications |
| **Reviewer** | Quality gatekeeper, venture compliance |
| **Analyst** | Research, data analysis, strategy |

Each agent is a markdown file. Edit the personality, tone, or rules to fit your style. Add new agents as you discover gaps (6–10 agents is the sweet spot — see `A-agents/_README.md` for guidance).

- [ ] Done (or skipped for now — that's fine)

---

## Step 4: Add Domain Knowledge (Optional)

> [!info] ~2 minutes | The more you add, the smarter the AI gets

Open **`systems/my-business-1/B-brain/domain-knowledge.md`** and add:
- Your industry overview
- Key concepts in your field
- Common client questions and your standard answers
- Any frameworks or methods you use

- [ ] Done (or skipped for now — add it gradually over time)

---

## Step 5: Start Using It

### With Claude Code (CLI)

```bash
cd your-realizeos-folder
claude
```

Claude Code automatically reads `CLAUDE.md` and understands the structure.

### With Claude Desktop

Point Claude Desktop to this vault directory. Claude will read `CLAUDE.md` and understand the structure.

### What to Try First

```text
"Write a LinkedIn post about [topic]"        → Writer activates
"Analyze [competitor / market / opportunity]" → Analyst activates
"Review this draft: [paste your text]"        → Reviewer activates
"Help me plan [project]"                      → Orchestrator breaks it down
"What are my current priorities?"             → Reads state map
```

---

## Ongoing Usage

### Keep the State Map Updated

`systems/my-business-1/R-routines/state-map.md` — update it with current priorities, active projects, and pipeline items. The AI reads this for context.

### Grow Your Brain

Add to `systems/my-business-1/B-brain/` as you learn things: market notes, client feedback, competitive intelligence, new domain knowledge.

### Review Your Insights

`systems/my-business-1/I-insights/learning-log.md` — the AI logs what worked and what didn't. Review periodically to improve workflows.

### Find Your Outputs

All AI-generated content is saved in the active system's `C-creations/` with descriptive filenames (e.g., `systems/my-business-1/C-creations/`).

---

## Running Multiple Ventures

Your workspace comes with 3 venture slots out of the box (`systems/my-business-1/`, `my-business-2/`, `my-business-3/`). Each has its own FABRIC directory structure — completely isolated agents, venture voice, knowledge, and outputs.

**To activate a new venture:**
1. Rename the folder to match your venture (e.g., `systems/consulting-practice/`)
2. Fill in the FABRIC files for the new venture
3. Uncomment (or add) the matching system entry in `realize-os.yaml`

**Or simply ask:** *"Create a new venture called [name]"* — the AI will set up the directory structure and config for you.

**To remove a venture:** Ask *"Remove venture [name]"* — the AI will confirm before deleting, and won't touch other systems.

---

## Need Help?

- Read `systems/my-business-1/A-agents/_README.md` — routing guidance and how to add agents
- Read `systems/my-business-1/R-routines/skills/` — available workflows
- Ask Claude: *"How does this system work?"* — it can explain the whole structure
- Support: [realizeos@realization.co.il](mailto:realizeos@realization.co.il)
