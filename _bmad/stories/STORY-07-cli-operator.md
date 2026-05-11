# Story: STORY-07 — CLI operator commands

## Epic: Workstream C — First-class operator CLI
## Priority: P0
## Status: todo

## Description

Add the operator-facing subcommands that talk to a running RealizeOS over its REST API: `chat`, `ask`, `kb`, `workflow`, `skill`, `evolution`, plus the new `venture run / show`. Each command supports `--format json|yaml|table` for shell-pipeline use.

## Acceptance Criteria

- [ ] `realize-os chat "..."` posts to `/api/chat`, prints the response.
- [ ] `realize-os chat --system KEY --agent KEY "..."` routes to a specific system / agent.
- [ ] `realize-os ask "..."` is an alias for `chat` with smart routing (no system/agent flags required).
- [ ] `realize-os venture run KEY [--input TEXT]` invokes a venture's default agent.
- [ ] `realize-os venture show KEY` prints config / agents / skills snapshot.
- [ ] `realize-os kb search QUERY [--venture KEY] [--format json|yaml|table]` returns ranked results.
- [ ] `realize-os kb get DOC_ID` returns full document.
- [ ] `realize-os kb reindex [--venture KEY]` triggers indexer; prints summary.
- [ ] `realize-os workflow {list,run NAME [--input JSON]}`.
- [ ] `realize-os skill {list,trigger NAME}`.
- [ ] `realize-os evolution {run,suggestions [--status STATE],approve ID,dismiss ID}`.
- [ ] All commands respect the active profile + `--profile` override.
- [ ] HTTP errors surface with stable exit codes (`2` = auth, `3` = not found, `4` = validation, `1` = generic).
- [ ] Tests cover one happy-path + one error-path per command (CliRunner + responses mocked).

## Technical Notes

- Use `httpx` (async-capable, already a transitive dep through FastAPI's `TestClient`) — pin explicitly in `pyproject.toml` if it isn't already.
- The CLI must work standalone (without the REST server running locally) by hitting whatever endpoint the active profile says.
- Streaming: `chat` should support SSE streaming when the server returns it; print tokens as they arrive.
- Don't catch generic `Exception` in command handlers — let Typer print structured errors.

## Dependencies

- STORY-06 (CLI foundation) merged.

## Files Affected

- `realize_core/cli/commands/{chat,ask,venture,kb,workflow,skill,evolution}.py` — new (`venture` extends the existing module from Story 6).
- `realize_core/cli/http.py` — new shared httpx client builder (profile-aware).
- `pyproject.toml` / `requirements.txt` — pin `httpx>=0.27`.
- `tests/test_cli_commands.py` — extend.
- `docs/cli-reference.md` — extend with each command's flags and examples.
