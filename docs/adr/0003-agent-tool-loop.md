# ADR 0003 — Agents Use Tools Through One Governed Loop

- **Status:** Accepted
- **Date:** 2026-10-11
- **Branch:** `feat/story-15-tool-loop`
- **Deciders:** Asaf (owner)
- **Relates to:** ADR 0001 (governance engine), ADR 0002 (trust surfaces), spec 005, release 5.7.0 plan (STORY-14/15/16).

## Context

Before 5.7.0, chat was text-in/text-out: `base_handler.standard_llm_handling` picked a model and called
`route_to_llm`. Providers had `complete_with_tools`, but nothing called it. Tools ran only inside fixed
skill steps, and `skills/executor.py` called the Google functions directly from a private map. That
bypassed the `ToolRegistry`, its MCP servers, and the governance gate installed at the registry.

## Decision

1. **One loop.** `realize_core/agents/tool_loop.py::run_tool_loop` is the only place a model's
   `tool_use` blocks are executed. Chat, skills and missions all use it, or the registry directly
   for skill tool steps.
2. **One dispatch point.** Every tool call goes through `ToolRegistry.execute`, so the trust ladder
   and approval gate (`governance/tool_gate.py`) see every call. Integrations are registered as
   `BaseTool`s (`FunctionMapTool` for Google/Sheets/ClickUp, `MCPBridgeTool` for MCP servers).
3. **Writes need the gate.** With `features.agent_tools` on but `features.enforce_gates` off, agents
   are offered **read-only** tools only. Write actions are offered only when the gate is installed.
   Unmapped write actions default to approval (`unknown_write`). MCP tools count as writes unless the
   operator lists them as read-only; server-supplied hints are not trusted.
4. **Held ≠ failed.** When the gate holds an action, the model receives a `tool_result` saying the
   action was not performed and awaits approval (request id). It is not `is_error`, so the model
   tells the user instead of retrying.
5. **Observable.** The loop reports `tool_call` / `tool_result` / `approval_requested` / `text` events
   through an `emit` callback. Missions translate them into runtime events; the chat SSE trail
   (STORY-17) streams them.
6. **Manual loop, not the SDK tool runner.** We need registry dispatch, gate semantics and live events
   on every call, so the loop is written explicitly. It follows the API rules: parallel `tool_use`
   blocks are answered in one user message, full assistant content is appended, and `pause_turn`
   is continued.

## Consequences

- Tool use runs on providers with a native tool API (Claude). Without one, chat falls back to
  plain `route_to_llm`. LiteLLM/OpenAI tool formats are a follow-up.
- The iteration cap (default 8) ends with one wrap-up turn instructing the model to answer with
  what it has.
- Approving a held action does not execute it yet. That is STORY-16, which unifies the approval
  stores and resumes the conversation.

## References

- `realize_core/agents/tool_loop.py`, `realize_core/base_handler.py` (`agent_tool_schemas`, `_answer_with_tools`)
- `realize_core/tools/function_tool.py`, `realize_core/tools/mcp_bridge_tool.py`, `realize_core/tools/tool_registry.py`
- Tests: `tests/test_story14_tool_registry.py`, `tests/test_story15_tool_loop.py`
