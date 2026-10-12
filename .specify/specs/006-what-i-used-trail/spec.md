# Feature Specification: "What I Used" Trail

**Feature Branch**: `feat/story-17-trail`
**Created**: 2026-10-11
**Status**: Implemented (5.7.0)
**Input**: RealizeOS upgrade brief, item 3. Every answer shows what it was built from: the knowledge-base
sources it read and the tools it called, in order, live while it works and again in history.

## User Scenarios & Testing

### User Story 1 — See what an answer was built from (P1)

A developer asks "How much is left in the Tower B budget?". Under the answer they see the two documents
the agent read ([S1], [S2]) and the `sheets_read` call it made, and the figure in the answer carries a
[S1] footnote.

**Acceptance**:
1. **Given** the KB index returns hits, **when** the user asks, **then** the hits are numbered [S1…Sn] in
   the prompt and the response's `trail.sources` lists them. With `features.cite_sources: true` on the
   `api`, `dashboard` or `mcp` channel, the model is also told to cite them inline.
2. **Given** `features.agent_tools: true`, **when** the agent calls tools, **then** `trail.steps` lists
   `tool_call`, `tool_result` and `approval_requested` in the order they happened.
3. **Given** the dashboard, **when** an answer arrives, **then** [Sn] markers render as footnotes and a
   trail panel under the answer lists sources and steps.

### User Story 2 — Watch it work (P1)

**Acceptance**: `POST /api/chat/stream` streams `source`, `tool_call`, `tool_result`,
`approval_requested` and `text` events as they happen, then one `final` event with the response,
message id and trail. Errors end the stream with an `error` event that carries no internal detail.

### User Story 3 — The trail is still there tomorrow (P2)

**Acceptance**: `GET /api/conversations/{system}/{user}` returns each message's `id`, and assistant
messages that had a trail carry it. Clearing the conversation removes its trails.

### Edge cases

- No KB hits and no tools: the trail is empty and nothing is stored.
- The KB layer is dropped by prompt deduplication: no sources are reported (no citations to missing text).
- An action held for approval appears as `approval_requested` with its request id.
- The client disconnects mid-stream: processing is cancelled.
- Skill, creative-session and resumed-skill answers carry no trail yet (they don't emit events).

## Requirements

- **FR-001** KB hits are numbered `[S1]…[Sn]` in the prompt; the same list is returned as
  `trail.sources` (`id`, `title`, `path`).
- **FR-002** Trail steps come from the tool loop's events; order is preserved.
- **FR-003** The trail is stored per assistant message in `memory.db` (`chat_trail`, keyed by the
  conversation row id, cascade-deleted with it).
- **FR-004** Conversation history sent to a model contains only `role` and `content`.
- **FR-005** Tool output never enters conversation history and is never sent back to a model from the
  trail. MCP `realize_chat` returns a trail summary without tool inputs, outputs or errors.
- **FR-006** `/chat` keeps its response shape and gains `message_id` and `trail`.
- **FR-007** `features.cite_sources` (engine default `false`, `true` in `realize_lite`) adds the
  instruction to cite sources, only on channels that show footnotes (`api`, `dashboard`, `mcp`).
  Telegram, Slack and other text channels never get it.

## Success Criteria

- In the webinar storyline, every figure in the investor report answer has a [Sn] footnote or a visible
  tool call behind it.
- Reloading the chat page shows the same trail under each past answer.

## Assumptions

- The trail is stored next to the conversations in `memory.db`, which is created by `init_db()` rather
  than the migration engine (that manages `realize_data.db`). The release plan said "new migration";
  this is the same table, placed where the messages it belongs to live.
- Token-by-token streaming of the answer text is out of scope; `text` carries the full answer once.
- Deriving `user_id` from the session on the server is STORY-18. The dashboard sends the signed-in
  user's id.
