# Story: STORY-05 — MCP admin tools (gated) + adversarial tests

## Epic: Workstream B — Built-in MCP server
## Priority: P1
## Status: todo

## Description

Add the **admin / write** tool family to the MCP server, hard-gated by both `mcp.allow_admin: true` AND `role = owner` JWT scope. In `REALIZE_ENV=production`, admin tools refuse to load unless `REALIZE_JWT_ENABLED=true` and a strong `REALIZE_JWT_SECRET` is set. Add a security-test suite covering the new MCP attack surface.

## Acceptance Criteria

- [ ] New `realize_core/mcp_server/tools/admin_tools.py` with: `create_venture`, `delete_venture`, `update_setting`, `reload_agents`, `refresh_tools`, `trigger_webhook`, `create_skill_suggestion`.
- [ ] Default config: `mcp.allow_admin: false`. With this off, admin tools never appear in `tools/list` and direct `tools/call` returns the structured error `MCP_ADMIN_DISABLED`.
- [ ] In `REALIZE_ENV=production`, even with `mcp.allow_admin: true`, the server **refuses to start** if JWT is not enabled or `REALIZE_JWT_SECRET` is empty/weak — log a clear error.
- [ ] Scope check: admin tools require `role = owner`. Editor / viewer calls return 403 with `MCP_INSUFFICIENT_SCOPE`.
- [ ] New `tests/security/test_mcp_adversarial.py`:
  - `test_admin_blocked_when_disabled`
  - `test_admin_blocked_for_non_owner`
  - `test_admin_requires_jwt_in_production`
  - `test_oversized_payload_rejected` (≥ 1 MB)
  - `test_session_id_mismatch_rejected`
  - `test_replay_protection` (same nonce twice ⇒ second rejected if applicable)
  - `test_injection_guard_runs_on_mcp_messages`
- [ ] All adversarial tests pass; existing 1709 tests still pass.

## Technical Notes

- Reuse the existing `InjectionGuardMiddleware` — extend its scope to the `/mcp/messages/*` path if not already covered.
- `create_venture` and `delete_venture` already require explicit confirmation in the REST handlers — surface that confirmation requirement in the MCP tool description so the calling agent knows.
- Audit log: admin calls always log full args regardless of `audit_full_payload` setting.

## Dependencies

- STORY-02, STORY-03, STORY-04 merged (the admin family closes the surface).

## Files Affected

- `realize_core/mcp_server/tools/admin_tools.py` — new.
- `realize_core/mcp_server/tools/__init__.py` — register.
- `realize_core/mcp_server/schemas.py` — admin schemas.
- `realize_core/mcp_server/server.py` — production-mode startup check.
- `tests/security/test_mcp_adversarial.py` — new.
- `docs/mcp-server.md` — append admin reference + security model section.
