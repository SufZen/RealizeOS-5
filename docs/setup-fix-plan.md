# PRD: Fix RealizeOS Full Setup Flow

> Based on [BMAD MTH-35 Planning Workflow](D:\Antigravity\BMAD\workflows\MTH-35-planning-workflow.md) — Full PRD Track

---

## EXECUTION INSTRUCTIONS

> **This plan is shared across TWO separate sessions. Read this section to know which stories are YOURS.**

### If your working directory is the PRODUCT REPO (`D:\Antigravity\realize-os\RealizeOS-Full-V03`):
**Execute Stories 1-6 only.** These fix the product code: `.env.example`, `setup.yaml.example`, `cli.py`, `requirements.txt`, `docker-compose.yml`, `Dockerfile`. Then apply fixes to the test instance at `D:\RealizeOS Full- tests\RealizeOS-Full-V03` (Story 6). **Do NOT touch the website repo.**

### If your working directory is the WEBSITE REPO (`D:\Antigravity\realize-os-site\realizeos-site`):
**Execute Stories 7-11 only.** These fix the setup guide HTML at `public/setup.html`: Step 3 command order, Step 4 deploy, Step 5 venture, Step 6 test, and troubleshooting. **Do NOT touch the product repo.**

### Context sections (PRD, Bugs Found) are shared reference — read them for understanding but only execute YOUR stories.

### BMAD Framework
All work MUST follow the [BMAD development framework](D:\Antigravity\BMAD). Key workflows:
- **Planning**: [MTH-35 Planning Workflow](D:\Antigravity\BMAD\workflows\MTH-35-planning-workflow.md)
- **Dev Stories**: [MTH-37 Dev Story Workflow](D:\Antigravity\BMAD\workflows\MTH-37-dev-story-workflow.md) — execute one story at a time, verify acceptance criteria before moving to the next
- **Templates**: Story format with acceptance criteria, files affected, and dependencies

Read the BMAD workflows before starting implementation. Follow the dev story workflow for each story: understand → implement → verify acceptance criteria → mark complete.

---

## Overview

Running the RealizeOS Full setup guide as a case study on Windows revealed critical bugs that block setup on ALL platforms. The product repo (`SufZen/realize-os`) has missing files, broken Docker config, and a fragile init flow. The website setup guide (`SufZen/realizeos-site`) has wrong command order, syntax errors, and missing instructions.

**Who:** Any new RealizeOS Full client on Windows, Mac, or Linux.
**Problem:** Setup fails at multiple points — users can't create `.env`, Docker loads empty config, auth breaks from inline comments, and test commands don't work.

## User Stories

- As a **new client**, I want to run a single init command that sets up everything (env vars, config, venture templates) so I don't need to manually copy/edit multiple files.
- As a **non-technical user**, I want copy-paste commands that work on my OS so I don't get stuck on syntax differences.
- As a **multi-venture operator**, I want the setup to create my first venture correctly and explain how to add more.
- As a **Docker user**, I want `docker compose up` to load my config and venture files so the server works immediately.
- As a **local-dev user**, I want `python cli.py serve` to auto-load my `.env` so I don't need to manually export variables.

## Functional Requirements

### Feature 1: Consolidated Setup File (`setup.yaml`)
- New `setup.yaml.example` template captures: API keys, template choice, business name/description
- `cli.py init --setup setup.yaml` reads it and configures everything:
  - Generates `.env` from API keys
  - Copies template → `realize-os.yaml` with business name substituted
  - Creates FABRIC structure (shared/, systems/)
  - Pre-populates venture-identity.md with business name/description
  - Creates `.gitignore` for secrets
- Fallback: `cli.py init --template consulting` still works (auto-creates `.env` from `.env.example`)

### Feature 2: Docker-Safe Environment Config
- `.env.example` exists in product repo with NO inline comments
- `docker-compose.yml` mounts correct paths (realize-os.yaml, shared/, systems/)
- `KB_PATH` set correctly so server finds all KB content

### Feature 3: Cross-Platform CLI Support
- `python-dotenv` loaded in cli.py for non-Docker users
- No platform-specific commands (cp/copy) required — Python handles file creation
- All instructions work on Windows, Mac, Linux

### Feature 4: Accurate Setup Guide
- Correct command order: init BEFORE env config
- Each command in its own copyable block
- Cross-platform instructions where needed
- Auth explained, system_key explained, troubleshooting covers all error types

## Non-Functional Requirements

### Security
- `setup.yaml` and `.env` are `.gitignore`d — never committed
- API keys never leave the user's machine
- `REALIZE_API_KEY` empty by default for local dev

### Multi-Venture Architecture
- First venture created by template (e.g., `key: consulting`)
- Additional ventures via `venture create` — each gets full FABRIC structure
- All ventures visible via `venture list`, available in API via system_key

## Technical Constraints

- Python 3.11+ required
- Docker optional but recommended
- Must work on Windows (PowerShell/cmd), macOS (Terminal), Linux (bash)
- YAML-based config (realize-os.yaml) — no breaking changes to schema
- Existing `realize_core/scaffold.py` functions reused for venture creation

## Success Metrics

- A new client can complete setup from scratch in < 15 minutes
- All 3 test commands from the guide pass on first try
- `/status` returns non-empty systems list
- `/api/chat` returns venture-aware response

---

## Bugs Found (Reference)

### Product Repo

| # | Sev | Bug |
|---|-----|-----|
| P1 | CRIT | `.env.example` missing — init silently skips, user can't create `.env` |
| P2 | CRIT | Dockerfile doesn't copy `realize-os.yaml`, `shared/`, `systems/` — empty config |
| P3 | CRIT | docker-compose mounts `./kb:/app/kb` — doesn't exist; KB is in `./shared/` + `./systems/` |
| P4 | CRIT | Docker `env_file` parses inline `# comments` as values — garbage REALIZE_API_KEY |
| P5 | HIGH | No `load_dotenv` — non-Docker users must manually export vars |
| P6 | MED | `cp .env.example .env` is Unix-only |

### Setup Guide

| # | Sev | Bug | Line |
|---|-----|-----|------|
| G1 | CRIT | Wrong order: `cp .env.example` before `cli.py init` (which creates it) | 659-684 |
| G2 | HIGH | `cd` + `pip install` in one copy block | 647-648 |
| G3 | HIGH | Venture list+create+delete in one copy block | 692-694 |
| G4 | HIGH | Deploy duplicates `pip install` | 780-781 |
| G5 | HIGH | `API_PORT=8081` should be `REALIZE_PORT=8081` | 791 |
| G6 | HIGH | Test commands missing auth + hardcoded system_key | 960-973 |
| G7 | HIGH | "Invalid API key" troubleshooting only covers Anthropic | 1104-1111 |
| G8 | MED | "Restart the server" — no command given | 901 |
| G9 | MED | Venture paths missing system directory prefix | 897-898 |
| G10 | MED | No Windows alternative for `cp` | 662 |

### Correct Setup Order

**Current (broken):** Install → Keys → pip+cp+edit+init → Deploy → Venture → Test ✗
**Fixed:** Install → Keys → pip+init(setup.yaml) → Venture(refine) → Deploy → Test ✓

---

# SESSION 1: Product Repo Stories (Stories 1-6)

> **EXECUTE THESE if your working directory is `D:\Antigravity\realize-os\RealizeOS-Full-V03`**
> [BMAD MTH-37 Dev Story Workflow](D:\Antigravity\BMAD\workflows\MTH-37-dev-story-workflow.md)
> **Target:** `D:\Antigravity\realize-os\RealizeOS-Full-V03`
> **Also apply to:** `D:\RealizeOS Full- tests\RealizeOS-Full-V03`

## Story 1: Create `.env.example`

**Priority:** P0 | **Status:** todo

### Description
Create a Docker-compatible `.env.example` with ALL comments on separate lines.

### Acceptance Criteria
- [ ] `.env.example` exists at product repo root
- [ ] No inline comments (every `#` on its own line)
- [ ] Contains: `ANTHROPIC_API_KEY`, `GOOGLE_AI_API_KEY`, `REALIZE_API_KEY`, `REALIZE_HOST`, `REALIZE_PORT`, `CORS_ORIGINS`
- [ ] Optional vars as commented-out lines
- [ ] Docker `env_file` parses cleanly

### Files Affected
- `RealizeOS-Full-V03/.env.example` — **CREATE**

---

## Story 2: Create `setup.yaml.example`

**Priority:** P0 | **Status:** todo

### Description
Create consolidated setup file template for one-command init.

### Acceptance Criteria
- [ ] `setup.yaml.example` exists at product repo root
- [ ] Fields: `anthropic_api_key`, `google_ai_api_key`, `template`, `business_name`, `business_description`
- [ ] Optional: `realize_port`, `realize_api_key`, `openai_api_key`, `telegram_bot_token`, `brave_api_key`
- [ ] Clear instructions at top
- [ ] Valid YAML

### Files Affected
- `RealizeOS-Full-V03/setup.yaml.example` — **CREATE**

---

## Story 3: Enhance `cli.py init` with `--setup`

**Priority:** P0 | **Status:** todo

### Description
Add `--setup` flag. Reads `setup.yaml`, auto-creates `.env`, config, FABRIC structure, pre-populates venture files.

### Acceptance Criteria
- [ ] `--setup` flag in argparser
- [ ] `_init_from_setup_file()` reads setup.yaml, extracts API keys + business info
- [ ] Generates `.env` with keys filled in
- [ ] Copies template → `realize-os.yaml` with business name
- [ ] Creates FABRIC structure (reuses existing `realize_lite` copy, lines 54-60)
- [ ] Pre-populates `venture-identity.md` with business_name/description
- [ ] Creates `.gitignore`
- [ ] Without `--setup`: auto-creates `.env` from `.env.example`
- [ ] Cross-platform (no `cp`/`copy` needed)

### Technical Notes
- Reuse existing `cmd_init()` logic (cli.py:30-79)
- Reuse `realize_lite` copy loop (cli.py:54-60)
- Venture pre-population: after FABRIC copy, read+modify `venture-identity.md`
- YAML: `import yaml` already available

### Dependencies
- Story 1 + Story 2

### Files Affected
- `RealizeOS-Full-V03/cli.py` — **EDIT**

---

## Story 4: Add `python-dotenv`

**Priority:** P1 | **Status:** todo

### Description
Add `load_dotenv()` for non-Docker users.

### Acceptance Criteria
- [ ] `python-dotenv>=1.0.0` in `requirements.txt`
- [ ] `cli.py` calls `load_dotenv()` with `ImportError` fallback
- [ ] `python cli.py serve` reads `.env` automatically

### Files Affected
- `RealizeOS-Full-V03/cli.py` — **EDIT**
- `RealizeOS-Full-V03/requirements.txt` — **EDIT**

---

## Story 5: Fix Docker configuration

**Priority:** P0 | **Status:** todo

### Description
Fix volume mounts and KB_PATH so Docker loads config + KB correctly.

### Acceptance Criteria
- [ ] `docker-compose.yml`: mount `./realize-os.yaml:/app/realize-os.yaml:ro`
- [ ] `docker-compose.yml`: mount `./shared:/app/shared`, `./systems:/app/systems`
- [ ] Old `./kb:/app/kb` removed
- [ ] `KB_PATH=/app` in environment
- [ ] `Dockerfile`: comment explaining runtime mounts
- [ ] After rebuild: `/status` shows non-empty systems
- [ ] After rebuild: `/api/chat` works (REALIZE_API_KEY empty)

### Files Affected
- `RealizeOS-Full-V03/docker-compose.yml` — **EDIT**
- `RealizeOS-Full-V03/Dockerfile` — **EDIT**

---

## Story 6: Apply to test instance + verify

**Priority:** P1 | **Status:** todo

### Description
Apply all fixes to test instance. Fix existing `.env`. Rebuild Docker. Run all tests.

### Acceptance Criteria
- [ ] Test instance has all updated files
- [ ] `.env` inline comments removed, `REALIZE_API_KEY=` empty
- [ ] `docker compose up --build` succeeds
- [ ] `curl /status` shows systems
- [ ] `curl /api/chat` returns response

### Dependencies
- Stories 1-5

### Files Affected
- `D:\RealizeOS Full- tests\RealizeOS-Full-V03\` — multiple files

---

## Session 1 Verification

```bash
cd "D:\RealizeOS Full- tests\RealizeOS-Full-V03"
python cli.py init --setup setup.yaml
docker compose down && docker compose up --build
curl http://localhost:8080/status
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What do you know about my business?", "system_key": "consulting", "user_id": "test-user"}'
```

---

# SESSION 2: Website Guide Stories (Stories 7-11)

> **EXECUTE THESE if your working directory is `D:\Antigravity\realize-os-site\realizeos-site`**
> **Target:** `D:\Antigravity\realize-os-site\realizeos-site\public\setup.html`

## Story 7: Fix Step 3 "Download & Configure" (lines 636-702)

**Priority:** P0 | **Status:** todo

### Description
Rewrite with correct order, separate code blocks, setup.yaml workflow.

### Acceptance Criteria
- [ ] Correct order: pip install → init (not env copy then init)
- [ ] `cd realize-os` in own code block
- [ ] `pip install -r requirements.txt` in own code block
- [ ] Primary: `setup.yaml` → `python cli.py init --setup setup.yaml`
- [ ] Alternative: `python cli.py init --template consulting` + edit `.env`
- [ ] `cp .env.example .env` removed
- [ ] Venture commands in SEPARATE code blocks
- [ ] Cross-platform notes

### Files Affected
- `public/setup.html` lines 636-702

---

## Story 8: Fix Step 4 "Deploy" (lines 763-798)

**Priority:** P1 | **Status:** todo

### Acceptance Criteria
- [ ] "Without Docker" shows only `python cli.py serve`
- [ ] `API_PORT=8081` → `REALIZE_PORT=8081`
- [ ] Prerequisite note added

### Files Affected
- `public/setup.html` lines 763-798

---

## Story 9: Fix Step 5 "Define Your Venture" (lines 883-912)

**Priority:** P1 | **Status:** todo

### Acceptance Criteria
- [ ] Full paths: `systems/my-business-1/F-foundations/venture-identity.md`
- [ ] Note about setup.yaml pre-population
- [ ] Restart commands (Docker + local)
- [ ] "Complete before testing" note

### Files Affected
- `public/setup.html` lines 883-912

---

## Story 10: Fix Step 6 "Test Everything" (lines 948-992)

**Priority:** P0 | **Status:** todo

### Acceptance Criteria
- [ ] "Test 0: Verify Config" added (curl /status)
- [ ] Auth note about REALIZE_API_KEY
- [ ] System_key explanation
- [ ] All curl syntax correct

### Files Affected
- `public/setup.html` lines 948-992

---

## Story 11: Fix Troubleshooting (lines 1103-1111)

**Priority:** P1 | **Status:** todo

### Acceptance Criteria
- [ ] Server auth error explained (REALIZE_API_KEY + inline comments)
- [ ] LLM key error explained (Anthropic/Google)
- [ ] Docker inline comment warning

### Files Affected
- `public/setup.html` lines 1103-1111

---

## Session 2 Verification

- Open setup guide in browser
- Walk through all Full Edition steps
- Copy-paste each command to verify syntax
- Check Mac/Windows/Linux tabs
- Verify code blocks are individually copyable

---

# SESSION PROMPTS

> Copy-paste the relevant prompt below when starting each session.

## Prompt for Session 1 (Product Repo)

```
I need you to execute the product repo fixes from the RealizeOS setup fix plan.

**Your working directory:** D:\Antigravity\realize-os\RealizeOS-Full-V03
**Test instance to also update:** D:\RealizeOS Full- tests\RealizeOS-Full-V03
**Plan file:** Read the full plan at docs/setup-fix-plan.md in this repo.

You are executing **Stories 1-6 ONLY** (product repo fixes). Do NOT touch the website repo.

**Before starting:** Read the BMAD dev story workflow at D:\Antigravity\BMAD\workflows\MTH-37-dev-story-workflow.md. Follow it for each story — understand, implement, verify acceptance criteria, then move to the next story.

**Story sequence:**
1. Create `.env.example` (Docker-safe, no inline comments)
2. Create `setup.yaml.example` (consolidated setup template)
3. Enhance `cli.py init` with `--setup` flag (reads setup.yaml, generates .env, config, FABRIC, venture files)
4. Add `python-dotenv` to requirements.txt + load_dotenv() in cli.py
5. Fix Docker config (docker-compose.yml volumes/paths, Dockerfile mounts)
6. Apply ALL fixes to the test instance at D:\RealizeOS Full- tests\RealizeOS-Full-V03, fix the existing .env (remove inline comments, set REALIZE_API_KEY= empty), rebuild Docker, verify with curl tests

**Key files to read first:**
- cli.py (current init flow, lines 30-79)
- realize_core/config.py (config loading)
- realize_core/scaffold.py (venture scaffolding)
- docker-compose.yml + Dockerfile (current Docker setup)
- templates/consulting.yaml (default template format)

**Verification after all stories:**
cd "D:\RealizeOS Full- tests\RealizeOS-Full-V03"
docker compose down && docker compose up --build
curl http://localhost:8080/status  (should show non-empty systems)
curl -X POST http://localhost:8080/api/chat -H "Content-Type: application/json" -d '{"message": "What do you know about my business?", "system_key": "consulting", "user_id": "test-user"}'
```

## Prompt for Session 2 (Website Repo)

```
I need you to execute the website setup guide fixes from the RealizeOS setup fix plan.

**Your working directory:** D:\Antigravity\realize-os-site\realizeos-site
**Plan file:** Read the full plan at docs/setup-fix-plan.md in this repo (copy it there first if not present, from D:\Antigravity\realize-os\RealizeOS-Full-V03\docs\setup-fix-plan.md).

You are executing **Stories 7-11 ONLY** (setup guide HTML fixes). Do NOT touch the product repo.

**Before starting:** Read the BMAD dev story workflow at D:\Antigravity\BMAD\workflows\MTH-37-dev-story-workflow.md. Follow it for each story.

**Target file:** public/setup.html — the Full Edition setup wizard

**Story sequence:**
7. Fix Step 3 "Download & Configure" (lines ~636-702): Correct command order (pip install → init, NOT env copy then init), separate code blocks, setup.yaml workflow as primary path, cross-platform notes
8. Fix Step 4 "Deploy" (lines ~763-798): Remove duplicate pip install, fix API_PORT→REALIZE_PORT, add prerequisite note
9. Fix Step 5 "Define Your Venture" (lines ~883-912): Full file paths with system directory prefix, restart commands for Docker+local, note about setup.yaml pre-population
10. Fix Step 6 "Test Everything" (lines ~948-992): Add "Test 0: Verify Config" (curl /status), auth note about REALIZE_API_KEY, system_key explanation, correct curl syntax
11. Fix Troubleshooting (lines ~1103-1111): Server auth error (REALIZE_API_KEY + inline comments), LLM key errors (Anthropic/Google), Docker inline comment warning

**Key context from product repo fixes (already applied):**
- New primary setup flow: user fills setup.yaml → runs `python cli.py init --setup setup.yaml`
- Alternative flow: `python cli.py init --template consulting` → manually edit `.env`
- `.env.example` now exists, Docker-safe (no inline comments)
- Docker volumes now mount realize-os.yaml, shared/, systems/ (not kb/)
- REALIZE_API_KEY empty by default = no auth needed for local dev
- Venture commands: `venture create --key KEY`, `venture delete --key KEY`, `venture list`

**Verification:** Open setup.html in browser, walk through all Full Edition steps, verify each code block is individually copyable and syntactically correct.
```
