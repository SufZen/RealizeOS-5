# Sprint Coordination Guide

## How to Run Parallel Agent Sessions

### Starting a Sprint

1. **Open 4 chat sessions** (e.g., 4 Gemini Code Assist windows, Claude sessions, or any AI coding tool)
2. **Paste the agent brief** into each session:
   - Session 1: `docs/dev-process/agent-briefs/agent-1-infra-agents.md`
   - Session 2: `docs/dev-process/agent-briefs/agent-2-skills-dashboard.md`
   - Session 3: `docs/dev-process/agent-briefs/agent-3-llm-cli.md`
   - Session 4: `docs/dev-process/agent-briefs/agent-4-google-extensions.md`
3. **Each session should also read**: `project-context.md` and `CLAUDE.md`
4. **Tell each agent**: "Start Sprint N for your track"

### Sprint 1 Execution Order

> [!IMPORTANT]
> **Agent 4 (Interfaces) is the critical path.** It must finish the shared base classes
> before Sprint 2 can begin for ANY agent.

```
Week 1:
  Agent 4 → Shared interfaces (base.py files)     ★ CRITICAL PATH
  Agent 1 → Docker improvements (parallel)
  Agent 2 → Migration engine (parallel)
  Agent 3 → CI/CD workflows (parallel)

Week 1 Gate: Agent 4 commits all base.py files → notify other agents

Week 2: Remaining Sprint 1 work wraps up
```

### Sprint 2-4 Execution

All 4 agents work in parallel within their file ownership boundaries. At the **end of each sprint**, run the integration gate.

### Integration Gate (End of Each Sprint)

Run this between sprints:

```bash
cd h:\RealizeOS-5\RealizeOS-5

# 1. Pull all agent branches (if using branches)
git pull --all

# 2. Run full test suite
python -m pytest tests/ -v --tb=short

# 3. Lint check
python -m ruff check realize_core/ realize_api/

# 4. Verify server starts
python cli.py serve --port 8080

# 5. If Sprint 2: Integration story (wire new systems into base_handler.py)
# This is done by ONE agent coordinating the merge of all new capabilities
```

### Git Strategy

**Option A (Simple):** All agents commit to `main` directly. Works because file ownership prevents conflicts.

**Option B (Branches):** Each agent works on a branch:
- `sprint-N/agent-1-infra`
- `sprint-N/agent-2-skills`
- `sprint-N/agent-3-llm`
- `sprint-N/agent-4-extensions`

Merge all at the sprint integration gate.

### Communication Protocol

Agents don't talk directly. They communicate through:
1. **Interface contracts** (the `base.py` files from Sprint 1)
2. **Commit messages** (conventional commits)
3. **Test assertions** (if a test fails, the responsible agent fixes it)
4. **You (the coordinator)** relay integration needs between sessions
