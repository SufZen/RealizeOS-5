# Story: STORY-08 — CLI MCP integration + REPL + formatters

## Epic: Workstream C — First-class operator CLI
## Priority: P1
## Status: todo

## Description

Round out the CLI with the MCP integration commands (`mcp serve`, `mcp status`, `mcp token`), the interactive REPL, and the polished output formatters used by every list/get command.

## Acceptance Criteria

- [ ] `realize-os mcp serve [--port PORT] [--allow-admin]` starts uvicorn with `MCP_ENABLED=true` (and `MCP_ALLOW_ADMIN=true` if flag set). Logs MCP endpoint URL on startup.
- [ ] `realize-os mcp status` shows enabled tool families, recent tool-call counts (from audit log), bearer-token TTL.
- [ ] `realize-os mcp token [--user USER] [--role ROLE] [--ttl SECONDS]` issues a JWT and prints it. Useful for plugging Claude Desktop / cloud routines.
- [ ] `realize-os repl [--system KEY]` opens an interactive `prompt-toolkit` session:
  - Multi-line input (Esc+Enter)
  - Line history (`~/.realize-os/repl-history`)
  - Slash commands: `/system NAME`, `/agent NAME`, `/clear`, `/exit`, `/help`
  - Streaming responses rendered live
  - Respects `NO_COLOR` and falls back to plain text when stdout is not a TTY
- [ ] Output formatters (`--format json|yaml|table`, default `table`) work on every list/get command from Stories 6–7. Verify on `venture list`, `kb search`, `workflow list`, `skill list`, `evolution suggestions`.
- [ ] `realize-os --install-completion` registers shell completion for bash, zsh, fish, PowerShell.
- [ ] Tests cover `mcp token` (asserts a valid JWT), `mcp status` (renders without a server when MCP disabled), formatter switching (same data → 3 different shapes).

## Technical Notes

- Pin `prompt-toolkit>=3.0` and `pyyaml>=6` (already in tree) in `pyproject.toml` / `requirements.txt`.
- REPL streaming uses the existing SSE path from `realize_api/routes/chat.py` — same wire format the dashboard uses.
- `mcp token` calls `POST /api/auth/token` with the operator's API key (from the active profile).
- `mcp serve` execs into uvicorn via `os.execvp` to keep PID 1 sensible in Docker — don't subprocess-and-wait.

## Dependencies

- STORY-06, STORY-07 merged.
- STORY-02 (MCP server) merged — `mcp serve` is meaningless otherwise.

## Files Affected

- `realize_core/cli/commands/mcp.py` — new.
- `realize_core/cli/commands/repl.py` — new.
- `realize_core/cli/repl.py` — prompt-toolkit session + slash command parser.
- `realize_core/cli/formatters.py` — extend (already created in Story 6).
- `pyproject.toml` / `requirements.txt` — pin `prompt-toolkit`.
- `tests/test_cli_commands.py` — extend.
- `docs/cli-reference.md` — extend.
