# Runtime Adapter Contract — v0.1 Specification

> The most consequential new interface in RealizeOS v5.5.0. Defines how any agent runtime (internal, Hermes, Claude Code CLI, Codex CLI, Gemini CLI, OpenClaw, Grok CLI, or future) plugs into the kernel as a peer.
>
> Target location: `docs/contracts/runtime-adapter.md` + `contracts/runtime-adapter.schema.json`  
> Status: Draft v0.1 — for review before Phase 0 lock  
> License: MIT (so collaborators can freely fork)

---

## 1. Purpose & Scope

### What This Contract Is

The Runtime Adapter Contract specifies the interface every **agent runtime** must satisfy to be a first-class peer in RealizeOS. A "runtime" is any system capable of executing one or more steps of a mission — receiving goals/instructions, performing actions (possibly via tools), and returning results.

### What Counts as a Runtime

- The existing internal agent system (`realize_core/agents/`) wrapped as a runtime
- External CLI tools: Claude Code, Codex CLI, Gemini CLI, Grok CLI, OpenClaw
- HTTP-based agent services: Hermes Agent, custom internal services
- Future: any agentic framework the user wants to plug in

### What Is NOT a Runtime

- A **tool** (single-action capability invoked via MCP / function call) — those satisfy the Tool Contract, not this one
- A **model** (raw LLM completion endpoint) — those go through the LLM Router
- A **workflow engine** (n8n) — those satisfy the Workflow Contract (separate, future)

The distinguishing question: *Does this thing take a goal and produce a sequence of actions to achieve it?* If yes → Runtime. If it does one specific action → Tool.

### Why This Abstraction Matters

Without it, RealizeOS picks a single agent framework and gets locked in. With it, the user mixes runtimes ("use Claude Code for code editing, Codex for autonomous research, my internal agents for client communication") and RealizeOS routes intelligently while keeping the knowledge/identity layer constant.

---

## 2. Core Interface (Python Protocol)

```python
from typing import Protocol, AsyncIterator, runtime_checkable
from datetime import datetime

@runtime_checkable
class AgentRuntime(Protocol):
    """Contract every agent runtime satisfies to participate in RealizeOS."""

    # === Identity & metadata ===

    runtime_id: str                          # Stable unique ID, e.g. "claude-code-cli"
    display_name: str                        # User-facing name
    version: str                             # Semver of the adapter
    runtime_version: str | None              # Semver of the underlying runtime if known
    
    # === Capability declaration ===
    
    def capabilities(self) -> "CapabilitySet":
        """Declare what this runtime can do. Called at registration and periodically."""
    
    # === Lifecycle ===
    
    async def health_check(self) -> "HealthStatus":
        """Is the runtime alive and ready to accept work?"""
    
    async def warmup(self) -> None:
        """Optional: pre-warm any cold caches, validate credentials."""
    
    async def shutdown(self) -> None:
        """Optional: graceful cleanup before deregistration."""
    
    # === Cost & estimation ===
    
    async def cost_estimate(
        self, task: "Task", context: "Context"
    ) -> "CostEstimate":
        """Estimated cost (tokens, time, monetary) for executing this task."""
    
    # === Execution ===
    
    async def invoke(
        self,
        mission_step: "MissionStep",
        context: "Context",
    ) -> AsyncIterator["RuntimeEvent"]:
        """
        Execute a mission step. Yields events as work progresses:
        - Progress updates
        - Tool invocations (with results)
        - Partial outputs (streaming text)
        - Final result
        - Errors
        """
    
    async def cancel(self, run_id: str) -> bool:
        """Cancel an in-flight invocation. Returns True if cancelled, False if already complete."""
    
    # === Skill exchange (optional) ===
    
    async def export_skills(self) -> list["Skill"] | None:
        """If the runtime maintains its own skill library, export it for cross-runtime reuse."""
    
    async def import_skill(self, skill: "Skill") -> bool:
        """Optional: import a skill from another runtime."""
```

---

## 3. Data Types

### 3.1 `CapabilitySet`

```python
class CapabilitySet:
    capabilities: list[Capability]           # What this runtime can do
    languages: list[str]                     # Natural languages it handles well, ISO 639 codes
    modalities: list[Modality]               # text, code, image, audio, video
    tool_protocols: list[ToolProtocol]       # mcp, openai_function, anthropic_tool, custom
    streaming: bool                          # Does it support streaming outputs
    cancellation: bool                       # Does it support mid-flight cancellation
    parallelism: int                         # Max concurrent invocations supported
    requires_internet: bool                  # Does it need network beyond LLM provider
    is_local: bool                           # All compute on this machine (no cloud)
```

### 3.2 `Capability`

A semantic tag describing what the runtime is good at. Used by the Smart Kanban Router to match tasks to runtimes.

```python
class Capability:
    name: str                                # Canonical name from registry
    confidence: float                        # Self-reported strength, 0.0-1.0
    cost_class: CostClass                    # cheap | moderate | expensive
    notes: str | None                        # Free-form context
```

**Canonical capability vocabulary v0.1** (extensible):

| Capability | Description |
|---|---|
| `code.edit` | Edit existing code files |
| `code.create` | Create new code files / scaffolds |
| `code.debug` | Debug failing code |
| `code.review` | Review code for issues |
| `research.web` | Web research with browsing |
| `research.deep` | Long-context synthesis research |
| `writing.creative` | Creative writing |
| `writing.business` | Business documents, emails |
| `writing.technical` | Technical writing, docs |
| `reasoning.long` | Complex multi-step reasoning |
| `reasoning.math` | Mathematical reasoning |
| `vision.understand` | Understand images |
| `vision.generate` | Generate images |
| `audio.understand` | STT, audio analysis |
| `audio.generate` | TTS |
| `data.analyze` | Analyze structured data |
| `browser.use` | Operate a browser autonomously |
| `computer.use` | Operate the computer autonomously |
| `agent.subagent` | Spawn and coordinate subagents |

### 3.3 `HealthStatus`

```python
class HealthStatus:
    ready: bool                              # Can accept work right now
    degraded: bool                           # Reachable but slow / partial
    last_check: datetime
    latency_ms: int | None                   # Round-trip on health check
    error: str | None                        # If unhealthy, why
    runtime_version: str | None              # Re-confirm version
```

### 3.4 `Task`

The high-level question the router uses for matching and the runtime uses for estimation.

```python
class Task:
    description: str                         # What needs to happen, plain text
    required_capabilities: list[str]         # Canonical capability names
    preferred_capabilities: list[str]        # Nice-to-have
    expected_output_tokens: int | None       # Hint for cost estimation
    language: str | None                     # ISO 639 code
    modality: Modality                       # Primary modality
    venture_id: str | None                   # For scoping context access
```

### 3.5 `MissionStep`

What actually gets executed.

```python
class MissionStep:
    step_id: str
    mission_id: str
    description: str                         # What this step achieves
    inputs: dict                             # Outputs from prior steps, structured
    expected_output_schema: dict | None      # JSON Schema for expected output
    tool_allowlist: list[str] | None         # Restrict to these tools; None = all permitted
    constraints: StepConstraints
```

### 3.6 `StepConstraints`

```python
class StepConstraints:
    max_cost_eur: float | None               # Hard cap on monetary cost
    max_duration_sec: int | None             # Hard wall-clock cap
    max_tokens: int | None                   # Hard token cap
    requires_approval_for: list[str]         # Categories of action requiring human approval mid-flight
    deny_actions: list[str]                  # Hard prohibitions, e.g. "send_external_email"
```

### 3.7 `Context`

What the runtime gets to see from the Heart.

```python
class Context:
    user_soul: dict                          # User-level SOUL (preferences, locale, voice)
    agent_soul: dict | None                  # Agent-level SOUL if invoked as a specific agent
    venture_id: str | None
    venture_summary: str | None              # From Synapse L1
    fabric_toc: dict | None                  # L1 TOC slice for this venture
    mission_memory: dict | None              # L4 for this mission, if continuing
    available_tools: list[ToolDescriptor]    # L3-ranked tools for this task
    history: list[Message] | None            # Conversation history if relevant
    audit_trace_id: str                      # For tying everything back to the event log
```

### 3.8 `RuntimeEvent`

The streaming event types the runtime emits during `invoke`.

```python
RuntimeEvent = (
    ProgressEvent
    | TextEvent
    | ToolCallEvent
    | ToolResultEvent
    | ApprovalRequestEvent
    | KnowledgeWriteEvent
    | FinalResultEvent
    | ErrorEvent
)
```

Each variant:

```python
class ProgressEvent:
    kind: Literal["progress"]
    run_id: str
    timestamp: datetime
    message: str                             # Human-readable status
    percent_complete: float | None           # 0.0–1.0 if estimable

class TextEvent:
    kind: Literal["text"]
    run_id: str
    timestamp: datetime
    delta: str                               # Streamed text chunk

class ToolCallEvent:
    kind: Literal["tool_call"]
    run_id: str
    timestamp: datetime
    tool_name: str
    args: dict
    tool_call_id: str

class ToolResultEvent:
    kind: Literal["tool_result"]
    run_id: str
    timestamp: datetime
    tool_call_id: str
    result: dict
    error: str | None

class ApprovalRequestEvent:
    kind: Literal["approval_request"]
    run_id: str
    timestamp: datetime
    category: str                            # Must match constraints.requires_approval_for
    description: str
    proposed_action: dict
    # Runtime blocks until host responds with approve/deny

class KnowledgeWriteEvent:
    kind: Literal["knowledge_write"]
    run_id: str
    timestamp: datetime
    entity_id: str
    entity_type: str
    operation: Literal["create", "update", "annotate"]
    diff: dict                               # What changed
    # Host applies write to FABRIC, returns confirmation

class FinalResultEvent:
    kind: Literal["final"]
    run_id: str
    timestamp: datetime
    output: dict
    cost_actual: CostActual
    status: Literal["success", "partial", "failed"]

class ErrorEvent:
    kind: Literal["error"]
    run_id: str
    timestamp: datetime
    error_type: ErrorType
    message: str
    retryable: bool
```

### 3.9 `CostEstimate` and `CostActual`

```python
class CostEstimate:
    estimated_tokens: int                    # Total prompt + completion
    estimated_duration_sec: float
    estimated_cost_eur: float                # Best-effort monetary estimate
    confidence: float                        # How sure the estimate is, 0.0–1.0

class CostActual:
    actual_tokens: int
    actual_duration_sec: float
    actual_cost_eur: float
    breakdown: dict                          # Per-model, per-tool breakdown
```

### 3.10 `Skill`

```python
class Skill:
    skill_id: str
    name: str
    description: str
    capability_tags: list[str]
    body: str                                # Markdown skill definition (Hermes SKILL.md style)
    source_runtime: str                      # Which runtime originated this
    portable: bool                           # Can this be used by other runtimes?
    usage_count: int
    last_used: datetime | None
```

### 3.11 `ErrorType`

```python
class ErrorType(Enum):
    AUTH = "auth"                            # Credential issue
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"
    TOOL_FAILED = "tool_failed"
    INVALID_INPUT = "invalid_input"
    INTERNAL = "internal"                    # Runtime bug
    UPSTREAM = "upstream"                    # LLM provider down
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
```

---

## 4. Lifecycle

### 4.1 Registration

A runtime adapter registers via the Runtime Registry at startup or via the Extension system:

```python
# In an extension file or core registration:
registry.register(MyRuntimeAdapter(config=...))
```

On registration:
1. Registry calls `health_check()` — must succeed within 5s
2. Registry calls `capabilities()` and caches the result
3. Registry assigns the runtime a position in the routing table
4. The runtime appears in the Smart Kanban Router as a routing target

### 4.2 Health Polling

- Registry polls `health_check()` every 30s for active runtimes (configurable)
- Runtimes that fail 3 consecutive checks are marked `degraded` and deprioritized
- Failed-for-5-minutes runtimes are marked `offline` and skipped by router until next successful check

### 4.3 Invocation

Mission engine selects a runtime, calls `invoke(mission_step, context)`, consumes the event stream:

```
invoke() opens
  → Runtime yields ProgressEvent("starting")
  → Runtime yields TextEvent (streamed)
  → Runtime yields ToolCallEvent (tool requested)
    → Mission engine invokes tool via Tool Registry
    → Mission engine yields ToolResultEvent back into the runtime's context
  → Runtime yields KnowledgeWriteEvent (proposes FABRIC write)
    → Mission engine applies write via Heart write API
    → Mission engine confirms application
  → Runtime yields ApprovalRequestEvent (mid-flight approval needed)
    → Mission engine surfaces in UI / channel
    → Mission engine blocks runtime until human responds
    → Mission engine yields approval result into runtime's context
  → Runtime yields FinalResultEvent
invoke() closes
```

### 4.4 Cancellation

`cancel(run_id)` is non-blocking. The runtime must respond by yielding an `ErrorEvent(type=CANCELLED)` from the in-flight `invoke()` call within 10s of cancellation request, or the mission engine considers it abandoned and proceeds (with cost still counted).

### 4.5 Shutdown

`shutdown()` is called when:
- RealizeOS is gracefully stopping
- The adapter is being hot-reloaded with a new version
- The user explicitly disabled the runtime

Runtime must release resources within 30s.

---

## 5. Error Model

### 5.1 Retry Semantics

The mission engine handles retries, not the runtime. The runtime indicates retryability via `ErrorEvent.retryable`.

Default retry policy (configurable per runtime):
- `RATE_LIMIT` → retry with exponential backoff up to 3 times
- `TIMEOUT` → retry once
- `UPSTREAM` → retry once after 10s
- `AUTH`, `BUDGET_EXCEEDED`, `INVALID_INPUT` → no retry; surface to user
- `TOOL_FAILED` → runtime decides if it can recover; mission engine doesn't retry the whole step

### 5.2 Budget Enforcement

The runtime is responsible for honoring `StepConstraints.max_cost_eur` and `max_tokens`. If exceeded mid-flight, the runtime must:
1. Yield an `ErrorEvent(type=BUDGET_EXCEEDED, retryable=False)`
2. Stop work
3. Include partial results in a final `FinalResultEvent` with `status="partial"`

### 5.3 Approval Timeouts

If an `ApprovalRequestEvent` doesn't receive a response within 5 minutes (configurable), the mission engine yields a denial back to the runtime. The runtime decides whether to continue with denial or abort.

---

## 6. Cost Model

### 6.1 Estimation

`cost_estimate()` is called before `invoke()` for routing decisions. The runtime should:
- Use the LLM provider's published pricing when known
- Add reasonable overhead for tool calls (best-effort)
- Mark `confidence` low when uncertain (e.g., open-ended research)

### 6.2 Reporting

Actual cost is reported in `FinalResultEvent.cost_actual`. The mission engine reconciles this against the budget and updates the per-tenant cost ledger.

### 6.3 Local Runtimes

Runtimes using only local models (Ollama, etc.) report `cost_eur: 0.0` and instead report compute time. The cost ledger tracks both axes.

---

## 7. Permission Scope

Per-runtime grants enforced by the host:

```yaml
# runtimes.yaml example
- runtime_id: claude-code-cli
  enabled: true
  scopes:
    - filesystem.read[*]
    - filesystem.write[~/dev/realizeos/**, ~/dev/burtucala/**]
    - tools.invoke[code.*, github.*]
  deny:
    - tools.invoke[email.send_external]
  cost_caps:
    per_invocation_eur: 2.0
    per_day_eur: 20.0
```

The host enforces these by:
- Filtering `Context.available_tools` to permitted ones only
- Refusing tool invocations outside the scope (returning a denial as a `ToolResultEvent` error)
- Hard-stopping the runtime at cost caps

The runtime should not need to know about these rules — the host enforces transparently.

---

## 8. Concrete Adapter Sketches

These are not implementations — they show how each runtime's quirks map into the contract.

### 8.1 RealizeInternal (existing agents)

- **Transport**: in-process function calls
- **Streaming**: native async generator
- **Tool protocol**: native MCP
- **Skills**: existing YAML skill files in `routines/`
- **Cost**: zero monetary cost (uses configured LLM provider via LLM Router)
- **Notes**: wraps existing `realize_core/agents/` as the first runtime; zero behavior change for users

### 8.2 Hermes Agent

- **Transport**: HTTP API (Hermes exposes one)
- **Streaming**: SSE
- **Tool protocol**: MCP (Hermes is MCP-native)
- **Skills**: SKILL.md files in `~/.hermes/skills/`; can be exported via `export_skills()`
- **Cost**: Hermes reports tokens; adapter computes EUR via configured pricing
- **Cancellation**: Hermes API supports cancel; adapter forwards
- **Approval**: Hermes has its own approval flow; adapter bridges into RealizeOS approval surface
- **Notes**: install Hermes separately; adapter just talks to it

### 8.3 Claude Code CLI

- **Transport**: subprocess (`claude` command)
- **Streaming**: stdout line-by-line parsing
- **Tool protocol**: Claude Code's native tool format; adapter translates to/from MCP
- **Skills**: Claude Code doesn't maintain a skill library; `export_skills()` returns None
- **Cost**: parses Claude Code's reported token usage; computes EUR via Anthropic pricing
- **Cancellation**: SIGTERM the subprocess
- **Approval**: maps Claude Code's `--ask` patterns into ApprovalRequestEvent
- **Notes**: needs `claude` on PATH and authenticated; adapter handles install hinting

### 8.4 Codex CLI

- **Transport**: subprocess
- **Streaming**: stdout
- **Tool protocol**: Codex's native; adapter translates
- **Cost**: Codex reports tokens
- **Notes**: similar to Claude Code; differences in flags and approval semantics

### 8.5 Gemini CLI

- **Transport**: subprocess
- **Streaming**: stdout
- **Tool protocol**: native; translate
- **Cost**: Google's API pricing; report local-vs-cloud appropriately
- **Notes**: Gemini CLI has its own MCP integration; adapter chains

### 8.6 OpenClaw

- **Transport**: subprocess or HTTP depending on user's deployment
- **Streaming**: depends on transport
- **Notes**: similar pattern to Hermes adapter

### 8.7 Grok CLI

- **Transport**: subprocess
- **Cost**: xAI pricing
- **Notes**: simpler tool model than Claude Code; some capabilities (`code.debug`) lower confidence

---

## 9. Discovery & Manifest

Each runtime adapter ships with a `runtime.yaml` manifest:

```yaml
# extensions/runtimes/claude-code-cli/runtime.yaml
runtime_id: claude-code-cli
display_name: Claude Code CLI
version: 0.1.0
adapter_module: realize_core.runtimes.claude_code
entry_point: ClaudeCodeAdapter
required_env:
  - CLAUDE_API_KEY
required_binaries:
  - claude
description: |
  Adapter for the Claude Code CLI (claude command).
  Supports code editing, debugging, and review tasks.
default_capabilities:
  - code.edit
  - code.create
  - code.debug
  - code.review
  - writing.technical
  - reasoning.long
default_cost_caps:
  per_invocation_eur: 2.0
  per_day_eur: 20.0
license: Apache-2.0          # of the upstream tool
documentation_url: https://docs.anthropic.com/claude-code
```

The Runtime Registry reads these at startup, validates them against a JSON Schema (`contracts/runtime-manifest.schema.json`), and registers conforming adapters.

---

## 10. Anti-Patterns (what runtimes must NOT do)

1. **Direct FABRIC writes**: runtimes never write to the filesystem under `ventures/` directly. All knowledge writes go through `KnowledgeWriteEvent` so the host can validate, audit, and reject.

2. **Direct event log writes**: only the mission engine writes to the event log. Runtimes report progress via events.

3. **Direct user channel writes**: a runtime cannot send a Telegram message or email directly. It requests via tool invocation (`ToolCallEvent`) which routes through the Tool Registry where permissions are enforced.

4. **Hidden network calls beyond declared scope**: if a runtime needs internet for something beyond its LLM provider, it must declare it in `CapabilitySet.requires_internet: true`. Undeclared external calls are a contract violation.

5. **Persistent state outside the runtime's own directory**: a runtime can keep state in `~/.<runtime-id>/` but cannot reach into other runtimes' state or RealizeOS internal storage.

6. **Spawning sub-runtimes silently**: if a runtime spawns subagents (Hermes does), those must be reported as nested events so the cost and audit trail stays intact.

---

## 11. Versioning

- This contract follows semver
- v0.x is unstable; breaking changes allowed
- v1.0 freezes the interface for backward compatibility
- The contract version a runtime targets is declared in its manifest
- The host can refuse runtimes targeting a contract version it doesn't speak

---

## 12. Open Questions

1. **Should `ApprovalRequestEvent` be synchronous (block runtime) or asynchronous (runtime continues, approves applied retroactively)?** Recommendation: synchronous for safety; runtime can `cancel()` if waiting too long.

2. **Should `KnowledgeWriteEvent` be applied immediately or batched at the end of a step?** Recommendation: immediate so other runtimes see writes in real time; batching is a future optimization.

3. **Cross-runtime skill portability — how literal?** Hermes SKILL.md format vs RealizeOS YAML skill format. Recommendation: skills carry their source format; the host translates on import where possible, marks non-portable skills clearly.

4. **Sub-agent spawning representation in events**: should nested invocations be flat (one event stream with hierarchy tags) or nested (each subagent gets its own `invoke()`)? Recommendation: flat with `parent_call_id` tags; nested explodes the event volume.

5. **Cost estimation accuracy expectations**: should the host enforce "estimate must be within 30% of actual"? Recommendation: no enforcement; track estimate-vs-actual as a quality signal for the runtime over time.

6. **Should runtimes have read access to `mission_memory` from prior runtimes in the same mission?** Recommendation: yes, through the standard `Context.mission_memory` — this is what makes multi-runtime missions coherent.

7. **Should runtime adapters be allowed to be implemented in languages other than Python?** Recommendation: yes for v5.5.0 via the subprocess/HTTP transport pattern; native Python adapters get a richer API surface but external-process adapters work fine.

---

*End of Runtime Adapter Contract v0.1*
