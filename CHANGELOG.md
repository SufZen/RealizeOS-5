# Changelog

All notable changes to RealizeOS are documented in this file.
This changelog is automatically generated from [Conventional Commits](https://conventionalcommits.org).


## [5.3.0](https://github.com/SufZen/RealizeOS-5/compare/v5.2.1...v5.3.0) (2026-05-27)

### Features

* **core:** add Event Log, SOUL identity, Mission Engine — Sprints 3 + 5 ([b9adb26](https://github.com/SufZen/RealizeOS-5/commit/b9adb266126bafbcb6e94abb4314f699bf3e1712))
* **dashboard:** add Missions, Knowledge Map, and Dream Inbox pages ([3be5715](https://github.com/SufZen/RealizeOS-5/commit/3be5715b9cf7b3d289a28f741ce4170c32afc77e))
* **dreaming:** add Dreaming subsystem + FABRIC CLI + version bump to v5.5.0 ([4596be3](https://github.com/SufZen/RealizeOS-5/commit/4596be31ddfd4134d970c62dabb7de78570a7993))
* **fabric:** add FABRIC Entity System — the Heart of RealizeOS ([de15472](https://github.com/SufZen/RealizeOS-5/commit/de15472d7aea5d3c25d50e6b14436e5a0d80ce20))
* **runtimes:** add Runtime Adapter Contract + Registry + FABRIC REST API ([d71e500](https://github.com/SufZen/RealizeOS-5/commit/d71e5008476586e8c46500ad4fc60c42667afe92))
* **synapse:** add Synapse knowledge indexer — L1 TOC, L2 FTS search, graph queries, L4 mission memory ([8d2e6a4](https://github.com/SufZen/RealizeOS-5/commit/8d2e6a4e7c707f5d5e950eb81ee24202431cd39f))
* v5.5.0 production hardening and site-alignment ([#5](https://github.com/SufZen/RealizeOS-5/issues/5)) ([cf9e8fa](https://github.com/SufZen/RealizeOS-5/commit/cf9e8fa138b4fa21d297454a1ff2bca89b0ca6a6))

### Bug Fixes

* **ci:** allowlist tests/test_auth_middleware.py in .gitleaks.toml ([fd4ab77](https://github.com/SufZen/RealizeOS-5/commit/fd4ab771d322976ef52c36aafda686e146722aff))
* **fabric:** audit fixes — unused import, round-trip fidelity, FTS cleanup, const validation ([9fd2089](https://github.com/SufZen/RealizeOS-5/commit/9fd2089787c68a7ed6ff212fe5cf189af6afb788))

> **Note:** Starting after v5.2.1, versions are automatically determined from
> Conventional Commits via [semantic-release](https://github.com/semantic-release/semantic-release).
> Entries below v5.2.1 were manually authored.

## [5.2.1] - 2026-05-14

### Fixed

- **CI lint pipeline** — 11 ruff issues in v5.2.0 files (unused imports, import ordering, `datetime.UTC` alias) auto-corrected. The CI lint job was failing on the v5.2.0 tag and blocking the release pipeline; v5.2.0 therefore never published to GHCR/npm/PyPI. v5.2.1 is the first published release of the v5.2 line.
- **Dashboard `lib/api.ts::readCookie`** — guarded with `typeof document === 'undefined'` so the module is safe to import from non-DOM contexts (vitest's default node runner, future SSR). Browser behavior is unchanged.
- **Dashboard vitest assertions** — updated `api.test.ts` to assert `credentials: 'include'` on fetches and `withCredentials: true` on `EventSource` so future regressions of the v5.2.0 cookie-session contract fail loudly.

### Changed

- No functional changes from v5.2.0 — this is a release-hygiene patch.

## [5.2.0] - 2026-05-14

### Added

- **Cookie-session dashboard auth** — Browser dashboard now has a real login flow at `/login`. Sessions are server-side opaque IDs stored in a new `user_sessions` SQLite table (migration 006), with 24h default TTL or 30 days for "Remember me". Logout revokes the row immediately. ([docs/PRODUCTION.md](docs/PRODUCTION.md))
- **`users.yaml`** — Multi-user support with `owner` / `admin` / `viewer` roles, bcrypt-hashed passwords. Single-owner fallback via `REALIZE_ADMIN_USER` + `REALIZE_ADMIN_PASSWORD_HASH` env vars when `users.yaml` is absent. ([users.yaml.example](users.yaml.example))
- **`scripts/hash_password.py`** — Helper CLI for generating bcrypt hashes (interactive or one-shot).
- **Unified `AuthMiddleware`** — One middleware that accepts session cookie OR `X-API-Key` OR Bearer JWT. Replaces the v5.1.x `APIKeyMiddleware` + `JWTAuthMiddleware` stack. Programmatic callers (CLI, Telegram bot) continue using `X-API-Key` with no change.
- **CSRF double-submit protection** — Mutating cookie-authenticated requests must echo the `realize_csrf` cookie in an `X-Realize-CSRF` header. SPA does this automatically. API-key and JWT callers are exempt.
- **`docs/PRODUCTION.md`** — Migration checklist for moving a deployment from development to production.
- **`tests/test_auth_middleware.py`** — 12 regression tests covering every credential path and CSRF behavior.

### Changed

- **Production validator collects all errors** — `_validate_production_security()` now reports every misconfiguration in one error instead of failing on the first. The dev → production migration is now a single round-trip. (Bug #8 / #9)
- **`requirements.txt`** — `python-telegram-bot>=21.0`, `pdfplumber>=0.11.0`, and `bcrypt>=4.0` are now required (no longer commented-out optionals). (Bug #4)
- **`.env.example`** — Clear "Production Security (all required)" block with explicit examples for every variable.
- **Dashboard `api.ts`** — Every `fetch`/`EventSource` now sends `credentials: 'include'`; 401 responses dispatch `realize:session-expired` so the AuthProvider can redirect to `/login`.
- **`docker-compose.yml`** — Comment on the `ports:` block explaining `${REALIZE_PORT}` resolution. (Bug #5)

### Fixed

- **Bug #1** — `cli.py bot` now constructs `TelegramChannel` with the correct kwargs (`bot_token`, `system_key`, `authorized_users`) instead of a stray `config=` dict.
- **Bug #2** — The bot command now blocks on `asyncio.Event().wait()` after `channel.start()`, preventing the "exit 0 → restart loop" on Docker.
- **Bug #3** — `cli.py index` now passes `force=True` (the actual parameter name on `index_kb_files`), not `force_reindex=True`.
- **Bug #6 / #7 / #11 / #12 / #13** — Dashboard pages and SPA routes no longer return 401. Resolved by the new `AuthMiddleware` (cookie sessions for the browser, API keys for programmatic callers), making the v5.1.1 prefix-whitelist hack obsolete.
- **Bug #10** — Chat page no longer crashes on plain HTTP. `crypto.randomUUID()` is now wrapped by `lib/uuid.ts::safeRandomUUID()` which falls back to `crypto.getRandomValues()` when the Secure Context API is unavailable.
- **Bug #14** — Old `JWTAuthMiddleware` removed; cookie + JWT + API-key checks all live in one place, eliminating the "first 401 wins" interaction.
- **Bug #15** — SPA catch-all returns 404 for dotfile paths (`/.env`, `/.git/*`) instead of silently serving `index.html` with 200.

### Removed

- **`JWTAuthMiddleware` class** in `realize_api/security_middleware.py` — folded into `AuthMiddleware`.
- **Standalone `APIKeyMiddleware` registration** in `realize_api/main.py` — replaced by `AuthMiddleware`. The `APIKeyMiddleware` name is kept as a thin compatibility alias for any external code that still imports it.

### Migration notes

Upgrading from 5.1.x to 5.2.0 in production:

1. `cp users.yaml.example users.yaml` and add at least one user — see [docs/PRODUCTION.md](docs/PRODUCTION.md).
2. Add `bcrypt`, `python-telegram-bot`, `pdfplumber` to your venv (or rebuild your Docker image).
3. Run the API once with `REALIZE_ENV=production` — it will list every missing variable in one error and refuse to start.
4. After login, every dashboard page that returned 401 in 5.1.0 should now load. Programmatic API key access (Telegram bot, CLI) is unchanged.

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
