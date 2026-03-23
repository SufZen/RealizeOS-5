# Dev Process — RealizeOS Development Operations Hub

> Single source of truth for what's being worked on, what's planned, and what's been decided.
> Git-synced. Readable by any AI tool, any device, or any contributor.

## How to Use

### Starting a Session (any tool, any device)

1. **Read** `active/current-focus.md` — see what's in progress
2. **Check** for uncommitted changes: `git status`
3. **Pull** latest: `git pull --rebase`
4. **Update** `active/current-focus.md` with what you're about to do

### Ending a Session

1. **Update** `active/current-focus.md` with where you stopped
2. **Log** the session in `active/session-log.md` (date, tool, what you did)
3. **Commit & push** — don't leave uncommitted changes behind

### Switching Devices

1. **Commit & push** on current device
2. **Pull** on new device
3. **Read** `current-focus.md` — the AI can read this too for instant context

## Directory Structure

```
dev-process/
  _README.md              ← You are here
  active/                 ← Current state (updated every session)
    current-focus.md      ← What's being worked on right now
    session-log.md        ← Running log of sessions across devices
    project-context.md    ← Project constitution (always loaded first)
  plans/                  ← Implementation plans (before execution)
  decisions/              ← Architecture Decision Records (ADRs)
  reference/              ← Analysis, research, external method docs
```

## Rules

1. **Plans live here** — not in AI conversation memory or external docs
2. **One file per plan** — named `YYYY-MM-topic.md`
3. **Decisions are permanent** — ADRs don't get deleted, only superseded
4. **current-focus.md is always current** — if it's stale, update it before working
5. **project-context.md is always loaded** — every session starts by reading it

## Phase Lifecycle

Each development phase follows this cycle:

```
1. CREATE plan   → plans/YYYY-MM-phase-topic.md
2. RECORD decision → decisions/ADR-NNN-topic.md (if architectural choice)
3. TRACK in focus → active/current-focus.md (claim work stream + conflict zone)
4. EXECUTE       → Write code, tests
5. TEST          → Run "Done when" gate
6. LOG session   → active/session-log.md
7. RELEASE       → Git tag phase completion
```
