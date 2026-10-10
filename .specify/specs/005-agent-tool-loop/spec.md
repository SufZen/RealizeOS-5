# Feature Specification: Agents Use Tools While They Answer

**Feature Branch**: `feat/story-15-tool-loop`
**Created**: 2026-10-11
**Status**: Implemented (5.7.0)
**Input**: RealizeOS upgrade brief, item 1. Agents use tools while they answer, through one loop for
chat and missions, via the tool registry (Google, Sheets, MCP servers).

## User Scenarios & Testing

### User Story 1 — Ask a question that needs live data (P1)

A project manager asks "What's the remaining budget on Tower B?". The finance agent reads the project
Google Sheet, then answers with the figure.

**Acceptance**:
1. **Given** `features.agent_tools: true` and a connected Google account, **when** the user asks, **then**
   the agent calls `sheets_read` through the registry and the answer uses its result.
2. **Given** the sheet can't be opened, **when** the tool fails, **then** the model is told
   (`is_error`) and says so instead of inventing a number.

### User Story 2 — An action that changes something waits for approval (P1)

The agent wants to append a row to the payments sheet.

**Acceptance**:
1. **Given** `enforce_gates: true` and trust level 3, **when** the agent calls `sheets_append`, **then**
   nothing is written, an approval request is created, and the agent tells the user it is pending.
2. **Given** `enforce_gates: false`, **then** write tools are not offered to the agent at all.

### User Story 3 — Missions see what the agent did (P2)

**Acceptance**: a mission step run by the internal runtime yields `tool_call`, `tool_result` and
`approval_request` events, in order, before its final result.

### Edge cases

- The model keeps calling tools: after `max_iterations` (8) it gets one wrap-up turn and must answer.
- Several tool calls in one turn run concurrently and are answered in one message.
- `pause_turn`: the loop continues the turn.
- No tool-capable provider is available: chat falls back to plain routing.
- An event listener raises: the loop continues.
- Unmapped MCP write tool: needs approval. Server-declared "read-only" is ignored unless the operator lists it.

## Requirements

- **FR-001** Tool calls from the model are executed only via `ToolRegistry.execute`.
- **FR-002** Skill `tool` steps execute via the registry. Skill LLM steps go through `route_to_llm`.
- **FR-003** Without the gate installed, only non-destructive tools are offered to agents.
- **FR-004** Per-agent `tools_allowlist` / `tools_denylist` (persona file) narrow the tool set.
- **FR-005** Progress events: `tool_call`, `tool_result`, `approval_requested`, `text`.
- **FR-006** Rate and cost limits of the router apply to every loop iteration.

## Success Criteria

- Webinar storyline steps that need data (tender register, milestones, investor figures) are
  answered from tool results, with each call visible in the trail.
- No write to an external system happens without an approval record while `enforce_gates` is on.

## Assumptions

- Claude is the tool-capable provider for 5.7.0. LiteLLM/OpenAI tool formats come later.
- Executing approved actions and resuming the conversation is STORY-16.
