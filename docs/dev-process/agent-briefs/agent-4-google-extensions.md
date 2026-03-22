# Agent 4 Brief: Google Workspace & Extensions

## Role
You are **Agent 4** in a 4-agent parallel BMAD development session for RealizeOS V5.

## Context
Read these files first to understand the project:
- `project-context.md` — conventions, tech stack, architecture decisions
- `CLAUDE.md` — development rules and anti-patterns
- `docs/dev-process/plans/realizeos-5-improvement-plan.md` — full improvement plan

## Your File Ownership
You own these files exclusively — NO other agent may modify them:

### Sprint 1 ★ CRITICAL PATH — Shared Interfaces
> **You must complete this before Sprint 2 starts for ALL agents.**
> These interface files define the abstract contracts that other agents implement.

- `realize_core/agents/base.py` [NEW] — shared by Agent 1's Sprint 2 work
  - `BaseAgent` protocol/dataclass with V2 fields: scope, inputs, outputs, guardrails, tools, critical_rules, decision_logic, success_metrics, learning, communication_style
  - `AgentConfig` Pydantic model for V2 YAML agent definitions
  - `HandoffData` dataclass for structured inter-agent communication
  - `PipelineStage` dataclass for pipeline stage definitions
  - `HandoffType` enum: standard, QA-pass, QA-fail, escalation, phase-gate, sprint, incident
- `realize_core/skills/base.py` [NEW] — shared by Agent 2's Sprint 2 work
  - `BaseSkill` protocol with `SkillFormat` enum (yaml / skill_md)
  - `SkillTriggerResult` dataclass with match score, trigger method (keyword vs semantic)
- `realize_core/storage/base.py` [NEW] — shared by Agent 2's Sprint 4 work
  - `BaseStorageProvider` abstract with methods: read, write, list, delete, exists
- `realize_core/extensions/base.py` [NEW] — shared by your own Sprint 3 work
  - `BaseExtension` protocol with `ExtensionType` enum
  - Registration protocol for auto-discovery
- `realize_core/optimizer/base.py` [NEW] — shared by Agent 3's Sprint 4 work
  - `BaseExperiment`, `ExperimentResult`, `OptimizationTarget` dataclasses
  - Experiment status enum: pending, running, improved, regressed, neutral
- `realize_core/tools/gws_base.py` [NEW] — shared by your own Sprint 2 work
  - `GwsToolConfig` schema for shell executor configuration

### Sprint 2 (Core Intelligence)
- `realize_core/tools/` (MODIFY existing + ADD new):
  - `gws_cli_tool.py` [NEW] — generic shell executor wrapping `gws` CLI
  - `google_sheets.py` [NEW] — native sheets_read, sheets_append, sheets_create
  - `google_workspace.py` [MODIFY] — add reply, forward, triage for Gmail; upload, download, permissions for Drive
  - `google_auth.py` [MODIFY] — expanded OAuth scopes for new services
  - `tool_registry.py` [MODIFY] — register new tools

### Sprint 3 (Extensions)
- `realize_core/extensions/` (ALL implementation files — new directory):
  - `registry.py` — unified extension registration and discovery
  - `loader.py` — auto-discover from config + filesystem
  - `cron.py` — cron scheduler (APScheduler integration)
  - `hooks.py` — event hooks (on_message, on_venture_change, on_agent_complete)

### Sprint 4 (Distribution & Docs)
- `README.md` [MODIFY] — comprehensive V5 documentation
- `CONTRIBUTING.md` [MODIFY] — updated contribution guide
- `docs/self-hosting-guide.md` [NEW]
- `docs/upgrade-from-v03.md` [NEW]
- `.github/ISSUE_TEMPLATE/` [NEW] — bug report, feature request templates

## Files You Must NOT Touch
- `realize_core/agents/` files OTHER than `base.py` (Agent 1 owns the implementations)
- `realize_core/skills/` files OTHER than `base.py` (Agent 2 owns the implementations)
- `dashboard/src/` (Agent 2)
- `realize_core/llm/` (Agent 3)
- `realize-os-cli/` (Agent 3)
- `realize_core/optimizer/` files OTHER than `base.py` (Agent 3)
- `Dockerfile`, `docker-compose.yml` (Agent 1)
- `realize_core/base_handler.py` — SHARED, only at sprint integration gate
- `realize_core/config.py` — SHARED, only at sprint integration gate

## BMAD Workflow Per Story
1. Load Context (read relevant files)
2. Plan (outline approach)
3. Implement (write code + tests)
4. Self-Review (verify no anti-patterns from CLAUDE.md)
5. Verify (run `python -m pytest tests/ -v --tb=short`)
6. Close (commit with conventional commit message)

## Sprint 1 Start ★ HIGHEST PRIORITY
This is the **critical path** for the entire project. Begin immediately with:
1. `realize_core/agents/base.py` — define BaseAgent, AgentConfig, HandoffData, PipelineStage, HandoffType
2. `realize_core/skills/base.py` — define BaseSkill, SkillFormat, SkillTriggerResult
3. `realize_core/storage/base.py` — define BaseStorageProvider
4. `realize_core/extensions/base.py` — define BaseExtension, ExtensionType
5. `realize_core/optimizer/base.py` — define BaseExperiment, ExperimentResult
6. `realize_core/tools/gws_base.py` — define GwsToolConfig

Use Pydantic v2 models and Python protocols. Keep interfaces minimal — only define what other agents need to import.

## Sprint 2 Start
Begin with `realize_core/tools/gws_cli_tool.py`:
1. Read existing `realize_core/tools/google_workspace.py` to understand patterns
2. Read existing `realize_core/tools/tool_registry.py` for registration
3. Implement generic shell executor wrapping `gws` CLI
4. Add Google Sheets native tools

## Tests
- `tests/test_interfaces.py` (Sprint 1 — verify all base classes are importable)
- `tests/test_gws_cli_tool.py`
- `tests/test_google_sheets.py`
- `tests/test_extension_registry.py`
