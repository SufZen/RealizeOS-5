# Story: STORY-06 — CLI foundation (Typer migration + profiles + entry point)

## Epic: Workstream C — First-class operator CLI
## Priority: P0
## Status: todo

## Description

Migrate `cli.py` from argparse to Typer, splitting the implementation into `realize_core/cli/` so subsequent stories can add subcommands cleanly. Add the `realize-os` entry point, the profile system, the formatter helpers, and a thin slim shim at `cli.py` so all existing `python cli.py …` paths keep working unchanged.

## Acceptance Criteria

- [ ] New package `realize_core/cli/` with `__init__.py` (Typer app), `commands/` (one module per group), `profiles.py`, `formatters.py`.
- [ ] `cli.py` becomes a < 30-line shim that calls `realize_core.cli:main`.
- [ ] `pyproject.toml` declares `[project.scripts] realize-os = "realize_core.cli:main"`.
- [ ] `pip install -e .` produces a working `realize-os` binary.
- [ ] Existing commands all migrated and verified working: `init`, `serve`, `bot`, `status`, `audit`, `index`, `venture {list,create,delete}`. Behavior unchanged.
- [ ] Backwards compat: `python cli.py status` still works (exits 0, prints same output as `realize-os status`).
- [ ] Profiles: `realize-os config profile {list,add,set-default,show}` reads/writes `~/.realize-os/config.toml`.
- [ ] `--profile NAME` global option overrides the default for one call.
- [ ] First-run `realize-os` (no profile yet) prompts to create one and offers a sensible default (`http://localhost:8080`).
- [ ] `realize-os --version` prints `5.1.0` (or whatever VERSION says).
- [ ] Autocomplete: `realize-os --install-completion` succeeds for at least bash and PowerShell.
- [ ] Tests in `tests/test_cli_commands.py` using Typer's `CliRunner`. Cover migrated commands + profile CRUD.

## Technical Notes

- Use Typer's `Typer(no_args_is_help=True)` so plain `realize-os` shows the help.
- Output formatters with `rich` — `to_table` / `to_json` / `to_yaml`. Default `table`.
- Profile file format: TOML, schema in `architecture.md`. Use stdlib `tomllib` for read, `tomli_w` for write (add to deps).
- Don't introduce a hard dep on `prompt-toolkit` here — it lands with REPL in Story 8.
- Logging: keep `logging.getLogger("realize")` for non-user-facing diagnostics; `rich.console.Console` for user output.

## Dependencies

- STORY-01 (CI green) merged so the new deps don't fight CI.

## Files Affected

- `cli.py` — slim shim.
- `realize_core/cli/__init__.py` — new.
- `realize_core/cli/commands/{init,serve,bot,status,audit,index,venture,config,version}.py` — new.
- `realize_core/cli/profiles.py` — new.
- `realize_core/cli/formatters.py` — new.
- `pyproject.toml` — entry point + new deps (`typer>=0.12`, `rich>=13`, `tomli_w>=1`).
- `requirements.txt` — pin same.
- `tests/test_cli_commands.py` — new.
- `docs/cli-reference.md` — new (skeleton; expanded by Story 9).
