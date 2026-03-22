# Agent 1 Brief: Infrastructure & Composable Agents

## Role
You are **Agent 1** in a 4-agent parallel BMAD development session for RealizeOS V5.

## Context
Read these files first to understand the project:
- `project-context.md` — conventions, tech stack, architecture decisions
- `CLAUDE.md` — development rules and anti-patterns
- `docs/dev-process/plans/realizeos-5-improvement-plan.md` — full improvement plan

## Your File Ownership
You own these files exclusively — NO other agent may modify them:

### Sprint 1 (Foundation)
- `Dockerfile` — multi-stage build, non-root user, gws CLI optional
- `docker-compose.yml` — named volumes for /data, /systems, /config, /shared
- Minor config updates to `cli.py` (only Docker-related commands)

### Sprint 2 (Core Intelligence)
- `realize_core/agents/` (ALL files — new directory):
  - `base.py` — BaseAgent protocol, AgentConfig Pydantic model, HandoffData, PipelineStage, HandoffType enum
  - `loader.py` — load V1 (.md) and V2 (.yaml) agents, auto-detect format
  - `registry.py` — agent registry with hot-reload, file-watcher
  - `schema.py` — Pydantic models for V2 agent format (ADR-007)
  - `personas.py` — persona-based tool bundles (exec-assistant, writer, PM)
  - `pipeline.py` — sequential pipeline executor with structured handoffs, Dev-QA retry (max 3 → escalation)
  - `handoff.py` — 7 handoff types: standard, QA-pass, QA-fail, escalation, phase-gate, sprint, incident
  - `guardrails.py` — safety constraints, quality gate enforcement, PASS/FAIL parsing
  - `activation.py` — context-rich agent activation prompts

### Sprint 3 (Interface)
- `realize_api/routes/agents_v2.py` — agent CRUD + pipeline management endpoints
- `realize_api/routes/workflows.py` — skill/workflow CRUD
- `realize_api/routes/extensions.py` — extension management endpoints
- `realize_api/routes/routing.py` — routing config + analytics
- Modify `realize_api/main.py` — register new routers

### Sprint 4 (Security)
- `realize_core/security/` — prompt injection detection, RBAC with YAML roles, JWT, audit logging

## Files You Must NOT Touch
- `realize_core/skills/` (Agent 2)
- `dashboard/src/` (Agent 2)
- `realize_core/llm/` (Agent 3)
- `realize-os-cli/` (Agent 3)
- `realize_core/tools/` (Agent 4)
- `realize_core/extensions/` (Agent 4)
- `realize_core/storage/` (Agent 4)
- `realize_core/base_handler.py` — SHARED, only at sprint integration gate
- `realize_core/config.py` — SHARED, only at sprint integration gate

## BMAD Workflow Per Story
1. Load Context (read relevant files)
2. Plan (outline approach)
3. Implement (write code + tests)
4. Self-Review (verify no anti-patterns from CLAUDE.md)
5. Verify (run `python -m pytest tests/ -v --tb=short`)
6. Close (commit with conventional commit message)

## Sprint 1 Start
Begin with Docker improvements:
1. Update `Dockerfile` for multi-stage build (dashboard build → Python runtime)
2. Update `docker-compose.yml` with named volumes
3. Write tests for Docker config validation

## Sprint 2 Start ★ (CRITICAL)
Begin with `realize_core/agents/base.py` (shared interfaces). Then implement the composable agent system. This is the largest track — start immediately.

## Tests
Create test files in `tests/` matching each module:
- `tests/test_agent_loader.py`
- `tests/test_agent_pipeline.py`
- `tests/test_agent_handoff.py`
- `tests/test_agent_guardrails.py`
