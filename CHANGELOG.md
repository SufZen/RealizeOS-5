# Changelog

All notable changes to RealizeOS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.1.0] - 2026-05-11

### Added

- **Built-in MCP server** — 24 tools across 4 families (Chat & Status, KB Read, Ops, Admin) exposed via HTTP+SSE at `/mcp/sse`. Gated access with independent toggles for KB, ops, and admin tools. Same JWT/API-key auth as the REST API. ([docs/mcp-server.md](docs/mcp-server.md))
- **First-class operator CLI** — Typer-based `realize-os` entry point with 19 command groups: `chat`, `ask`, `repl`, `kb`, `workflow`, `skill`, `evolution`, `mcp`, `config`, `venture`, `devmode`, `version`, and all legacy deploy commands. ([docs/cli-reference.md](docs/cli-reference.md))
- **Interactive REPL** — `realize-os repl` with prompt-toolkit, file history, slash commands (`/system`, `/agent`, `/session`, `/clear`, `/help`, `/exit`).
- **Multi-instance profiles** — `realize-os config profile add/list/set-default/show` with TOML-backed persistence in `~/.realize-os/config.toml`.
- **Config management** — `realize-os config show/set/unset` for reading and writing `realize-os.yaml` with dotted-key navigation and auto-casting.
- **Output formatters** — `--format table|json|yaml` on every list/get command.
- **Shell autocomplete** — `realize-os --install-completion` for bash/zsh/fish/PowerShell.
- **BMAD project scaffolding** — `_bmad/` directory with project context, PRD, architecture, stories, sprint status, and readiness check.
- **AGENTS.md** — Top-level agent instructions for AI coding assistants working in this repo.
- **Gitleaks allowlist** — `.gitleaks.toml` for known false positives; gitleaks step now blocks on real leaks.

### Changed

- **CI hardened** — Docker Compose validation creates `.env` from `.env.example`; gitleaks and safety checks promoted to blocking.
- **CLI migrated** — `cli.py` refactored from argparse to a lightweight Typer shim. `python cli.py <verb>` still works identically.
- **Dependencies** — Added `typer>=0.12`, `rich>=13.0`, `tomli_w>=1.0`, `prompt-toolkit>=3.0`, `httpx>=0.27`.
- **Test suite** — 1,904 tests passing (up from 1,709 baseline).

### Fixed

- **CI env-file bug** — `docker compose config` no longer fails when `.env` is missing in CI environments.

## [5.0.6] - 2026-03-29

- Last published release on Docker/npm/PyPI before the 5.1.0 development cycle.
