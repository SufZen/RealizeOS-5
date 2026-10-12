# Feature Specification: Venture-Scoped Users and Views

**Feature Branch**: `feat/story-18-venture-scope`
**Created**: 2026-10-11
**Status**: Implemented (5.7.0)
**Input**: RealizeOS upgrade brief, item 4. A client's people work in their venture only, and a
read-only role is really read-only.

## User Scenarios & Testing

### User Story 1 — A client's project manager sees their venture only (P1)

Dana manages Tower B for a client. She signs in and sees Tower B everywhere: venture lists, the
dashboard, agents, approvals, activity, missions, chat. Another client's venture is not there.

**Acceptance**:
1. **Given** `ventures: [tower-b]` for Dana in `users.yaml`, **when** she lists ventures, systems,
   agents, approvals, missions, dream proposals or activity, **then** only Tower B items appear.
2. **Given** a path, query or JSON write body naming another venture, **then** the API returns 403.
   Another venture's approval, mission or agent is "not found".
3. **Given** she is limited to one venture, **then** the dashboard's venture switcher is locked to it.

### User Story 2 — Roles mean what they say (P1)

**Acceptance**: a `viewer` gets 403 on every write, including chat. Approving needs `operator` or
higher. Settings, integrations, agent definitions and other writes shared by every venture need an
`owner` or `admin` who is not limited to some ventures.

### User Story 3 — Agents get the same limits (P2)

**Acceptance**: an MCP caller limited to some ventures can use only the tools that name one of them
(or an approval in one); listings are filtered; cross-venture tools return `MCP_FORBIDDEN`.

### Edge cases

- A malformed `ventures` entry skips that user (fail closed), never "every venture".
- A JWT `venture:<key>` scope narrows a user's list; it never widens it.
- System-wide data (no venture) is hidden from venture-limited callers; global skill templates stay
  visible.
- FABRIC endpoints span every venture unless one is named, so a venture-limited caller must name one.
- Edits addressed by item id alone (FABRIC entities, workflows) are refused for venture-limited
  callers, because the item's venture can't be checked.
- Auth off (dev mode), API-key callers and users without `ventures`: unchanged.

## Requirements

- **FR-001** `users.yaml` users may list `ventures`; roles `owner`, `admin`, `operator`, `user`,
  `viewer` are accepted (the RBAC built-ins).
- **FR-002** One app-wide dependency (`realize_api.dependencies.enforce_access`) checks venture scope
  on path, query and JSON-body venture keys, and an RBAC permission on every write, chosen in
  `realize_core.security.venture_scope.required_permission`. Unknown writes need `system:write`.
- **FR-003** Listings use `visible_systems()` / `visible_to()`; nothing iterates every venture for a
  venture-limited caller.
- **FR-004** `/api/auth/session` and `/api/auth/login` return the user's `ventures` (null = all).
- **FR-005** The dashboard keeps one selected venture (`VentureProvider`) for chat, pipelines,
  skills and the knowledge map, with a switcher in the sidebar.
- **FR-006** MCP applies the same scope in its dispatcher (`mcp_server/venture_guard.py`).
- **FR-007** Venture keys are found the way FastAPI reads them: any JSON body (whatever the
  content type), nested objects and lists, every repeated query value; a non-text venture value is
  refused. Items fetched by id are checked against their own venture (FABRIC entities and their
  neighbours, workflows, approvals, missions, MCP skills by name).
- **FR-009** Resources are checked where they are resolved: KB files must live in the venture's
  own directory; FABRIC reads must name `venture` (the parameter the handlers filter by); dashboard
  sessions are re-checked against `users.yaml` on every request (removed user → 401, current role
  applies); MCP tools use the same RBAC permissions as the REST routes. (Independent review F1–F5.)
- **FR-008** System-wide areas (settings, security, setup, integrations, storage, devmode,
  extensions, shared files, trust, tools, evolution, pipelines) are closed to
  venture-limited callers, reads included.

## Success Criteria

- A webinar demo user scoped to the demo venture cannot see or change anything outside it.
- A viewer account cannot change anything.

## Assumptions

- Scope is resolved from `users.yaml` on each request, so changing a user's ventures takes effect
  without signing out.
- Recording who decided an approval (`decided_by`) is not part of this story.
