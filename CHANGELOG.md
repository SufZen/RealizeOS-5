# Changelog

All notable changes to RealizeOS are documented in this file.
This changelog is automatically generated from [Conventional Commits](https://conventionalcommits.org).


## [5.16.0](https://github.com/SufZen/RealizeOS-5/compare/v5.15.6...v5.16.0) (2026-10-13)

### Features

* **dashboard:** design system v2 "Drawing Set" — tokens, motion, primitives, /design ([b7d86f5](https://github.com/SufZen/RealizeOS-5/commit/b7d86f5b18f9d607a83a9389f10aa01cc5cced91))

## [5.15.6](https://github.com/SufZen/RealizeOS-5/compare/v5.15.5...v5.15.6) (2026-10-12)

### Bug Fixes

* **dashboard:** skip the onboarding wizard on a server that is already set up ([5074c72](https://github.com/SufZen/RealizeOS-5/commit/5074c72cce3c4673fdb05d60d3e106dc3308e57b))
* **fabric:** reindex skips a venture with no folder instead of 404ing ([69b4070](https://github.com/SufZen/RealizeOS-5/commit/69b407047cd015952a7fd960058e78bf31c389f3))
* **skills:** add get_skills_for_system, which the skills endpoint and MCP tool import ([e29e124](https://github.com/SufZen/RealizeOS-5/commit/e29e124739f34a4c70b764d03fc4306b3636a185))
* **skills:** the venture skills endpoint checks the venture itself ([7002342](https://github.com/SufZen/RealizeOS-5/commit/7002342dd0b91f77d0f727a4bb2a9af4b7dc7004))

## [5.15.5](https://github.com/SufZen/RealizeOS-5/compare/v5.15.4...v5.15.5) (2026-10-12)

### Bug Fixes

* **api:** unknown /api and /mcp paths return a JSON 404, not the dashboard ([bb18287](https://github.com/SufZen/RealizeOS-5/commit/bb1828745732b6027babf849089133e494f1fe31))
* **auth:** session introspection re-checks the configured user ([9a2fd5b](https://github.com/SufZen/RealizeOS-5/commit/9a2fd5bc5cb9a74e4fff220a35ab7890472531b6))
* **chat:** the agent you pick is the agent that runs, and the reply says who did ([1b55e3e](https://github.com/SufZen/RealizeOS-5/commit/1b55e3e1589c1dc42e36351987c0e800fc927064))
* **dashboard:** the first-visit tour waits for the signed-in app ([9ab7d7d](https://github.com/SufZen/RealizeOS-5/commit/9ab7d7dad1bfd5bf6d9a3841911bc2ab3e018666))
* **missions:** validate plans before storing; say the page only follows missions ([906c46e](https://github.com/SufZen/RealizeOS-5/commit/906c46e6e8dbda573463a6ae4043137220d0e1a4))
* **release:** the image and MCP server report the real release version ([834a91f](https://github.com/SufZen/RealizeOS-5/commit/834a91f4ffd2aa925ee6f364e7351d11a63ea622))
* **routing:** Routing Analytics shows real routing decisions, in the page's shape ([377ffeb](https://github.com/SufZen/RealizeOS-5/commit/377ffebfd8b0c9ce449960ce6466de8c17ce5d52))
* **storage:** a real export download, and saved storage settings take effect ([70ac096](https://github.com/SufZen/RealizeOS-5/commit/70ac096a4311a0b026393d40bde6d47433d7f197))
* **webhooks:** report matched triggers as matched, not fired ([7f9231d](https://github.com/SufZen/RealizeOS-5/commit/7f9231d3957bb74f549c77ec778e54d636a1dc6a))

## [5.15.4](https://github.com/SufZen/RealizeOS-5/compare/v5.15.3...v5.15.4) (2026-10-12)

### Bug Fixes

* **integrations:** stop claiming connections the page never makes ([3ea82be](https://github.com/SufZen/RealizeOS-5/commit/3ea82be53c711d125623a250157c845500390e3c))
* **pipelines:** label pipeline runs as simulated ([397332b](https://github.com/SufZen/RealizeOS-5/commit/397332bd72725aa081407b4d9ab36f5d6516de5c))
* **workflows:** editor no longer crashes or fakes saves; API refuses empty workflows ([65b1821](https://github.com/SufZen/RealizeOS-5/commit/65b1821a98aa0130ae4f7f9859c8945df090a453))

## [5.15.3](https://github.com/SufZen/RealizeOS-5/compare/v5.15.2...v5.15.3) (2026-10-12)

### Bug Fixes

* **approvals:** agent approval requests reach the dashboard queue ([ff64d99](https://github.com/SufZen/RealizeOS-5/commit/ff64d99d748dac9b0c120d636b255773cec794f8))
* **missions:** a held action holds the mission instead of completing it ([f5e184c](https://github.com/SufZen/RealizeOS-5/commit/f5e184cef305e3df884a22905bb6944e639a0216))
* **skills:** a held tool step pauses the skill; paused runs are durable ([4f72f31](https://github.com/SufZen/RealizeOS-5/commit/4f72f31aa74c3197a29c2a3a7cd865de9fb5ba76))
* **skills:** don't relay third-party tool text when resuming after approval ([bebcb05](https://github.com/SufZen/RealizeOS-5/commit/bebcb05cf6fdba685c213aa844fa1d09c82b5633))

## [5.15.2](https://github.com/SufZen/RealizeOS-5/compare/v5.15.1...v5.15.2) (2026-10-12)

### Bug Fixes

* **governance:** apply Settings policy changes to the live tool gate ([26b5289](https://github.com/SufZen/RealizeOS-5/commit/26b52891262a62004e0075f5521d98a38f5cd239))
* **governance:** fail closed when the tool gate can't be applied ([47fe6c0](https://github.com/SufZen/RealizeOS-5/commit/47fe6c0b9c4a2da2cc8daf18fec0789c24a80b94))
* **setup:** provider keys saved in Setup apply without a restart ([4ac2032](https://github.com/SufZen/RealizeOS-5/commit/4ac203247784ab05b063f804056ac620f50865b2))
* **storage:** keep every durable store on persisted storage; report a failed one ([fcec8f0](https://github.com/SufZen/RealizeOS-5/commit/fcec8f02a852acfada553ac54a187aec634c838a))

## [5.15.1](https://github.com/SufZen/RealizeOS-5/compare/v5.15.0...v5.15.1) (2026-10-12)

### Bug Fixes

* **dashboard:** never show one user's cached data to the next ([6791626](https://github.com/SufZen/RealizeOS-5/commit/679162683fa5e9ebf0eb86f79669186a78b4ba47))
* **security:** keep venture-limited callers out of other ventures' diagnostics ([3ac5bfb](https://github.com/SufZen/RealizeOS-5/commit/3ac5bfb5f7f808e70d146f49d54c8ce146dd18cd))

## [5.15.0](https://github.com/SufZen/RealizeOS-5/compare/v5.14.0...v5.15.0) (2026-10-12)

### Features

* **llm:** default to the newest Claude models (Sonnet 5.5, Opus 5.5) ([2d9b023](https://github.com/SufZen/RealizeOS-5/commit/2d9b023679c2044ebdae731d305e423e2828e497))

### Bug Fixes

* **llm:** recover from a dead Claude model on the native tool path ([0de7215](https://github.com/SufZen/RealizeOS-5/commit/0de72158716f1418f8beffa7d4b30f173cd1064f))
* **llm:** treat a model refusal as final, never retry it on another provider ([a0a9796](https://github.com/SufZen/RealizeOS-5/commit/a0a9796f7bc2416d72c1623575240c1b9293d9c7))
* **llm:** use live Claude model IDs and fall through to the next provider ([2e2eb26](https://github.com/SufZen/RealizeOS-5/commit/2e2eb263a385a3aefa02c87ffc830d929facf7ec))
* **ventures:** make venture delete and create all-or-nothing ([4efe3bc](https://github.com/SufZen/RealizeOS-5/commit/4efe3bced4ffbad26290c2ec39fdb9d5879c27fd))

## [5.14.0](https://github.com/SufZen/RealizeOS-5/compare/v5.13.0...v5.14.0) (2026-10-12)

### Features

* **mcp:** Streamable HTTP on /mcp + OAuth 2.1 for Claude.ai connectors ([b08ad29](https://github.com/SufZen/RealizeOS-5/commit/b08ad29ae8610845baa1f5bf42b34dd76ae2d030)), closes [#21](https://github.com/SufZen/RealizeOS-5/issues/21)

### Bug Fixes

* **security:** MCP OAuth redirect allowlist and per-account sign-in limit ([44aaed8](https://github.com/SufZen/RealizeOS-5/commit/44aaed872739fce5fec02d5bb5060370fd058d30))
* **security:** one IP can't lock an MCP OAuth account ([adc1299](https://github.com/SufZen/RealizeOS-5/commit/adc1299955df5686b15ab32cfd60e73f9f24f7ef))

## [5.13.0](https://github.com/SufZen/RealizeOS-5/compare/v5.12.0...v5.13.0) (2026-10-12)

### Features

* **demo:** rehearsal kit — Google sign-in, sheet import files, read-only preflight ([d867396](https://github.com/SufZen/RealizeOS-5/commit/d867396c3b2867d1ca3a48a0d32c9f5aa4a861d6))
* **templates:** real-estate developer demo pack (STORY-20) ([7761caa](https://github.com/SufZen/RealizeOS-5/commit/7761caa314c69e546fb8fbb777fe9620ebb77364))

### Bug Fixes

* **security:** save the Google token owner-only ([d4eb040](https://github.com/SufZen/RealizeOS-5/commit/d4eb0403a98fbfe76b663537a0d3984b527f2405))
* **skills:** failed tool steps stop the workflow; skill steps leave a trail ([d64701f](https://github.com/SufZen/RealizeOS-5/commit/d64701fc79f5c9b49b5e6759da36fbee2fc51ac4))

## [5.12.0](https://github.com/SufZen/RealizeOS-5/compare/v5.11.0...v5.12.0) (2026-10-12)

### Features

* **dashboard:** Hebrew right-to-left support (brief item 5) ([fe33307](https://github.com/SufZen/RealizeOS-5/commit/fe3330705d257d16e7cce818831594637ceef2f1))

### Bug Fixes

* **dashboard:** no deployment onboarding for venture-limited users ([c9dd85b](https://github.com/SufZen/RealizeOS-5/commit/c9dd85b35fa2ccde1d23168835ba0a9fa4894c6e))

## [5.11.0](https://github.com/SufZen/RealizeOS-5/compare/v5.10.0...v5.11.0) (2026-10-12)

### Features

* **security:** venture-scoped users and real roles (brief item 4) ([0767de9](https://github.com/SufZen/RealizeOS-5/commit/0767de98ea4e20d771af907f26020e30ce11754b))

### Bug Fixes

* **auth:** let operator and user roles sign in (migration 008) ([ad72d9c](https://github.com/SufZen/RealizeOS-5/commit/ad72d9c2b4287a37de7dbfe9d9c6f5a4735f4bd6))
* **security:** check skills by owning venture; scope MCP chat context ([fcff94c](https://github.com/SufZen/RealizeOS-5/commit/fcff94ca25e8ff713c8f2c600e83311179db8602))
* **security:** check venture ownership where resources are resolved ([b748840](https://github.com/SufZen/RealizeOS-5/commit/b748840319f19131d9093da9b73ced388a997591))
* **security:** close venture-scope bypasses found in review ([48f843d](https://github.com/SufZen/RealizeOS-5/commit/48f843d5006f49b5a95e2ded1db47031fa750e39))

## [5.10.0](https://github.com/SufZen/RealizeOS-5/compare/v5.9.0...v5.10.0) (2026-10-12)

### Features

* **chat:** show what each answer used (brief item 3) ([c10ead5](https://github.com/SufZen/RealizeOS-5/commit/c10ead5d1dc5685803eaf2cb6f5346467dda014a))

### Bug Fixes

* **security:** chat and history act only for the signed-in user ([6e1a606](https://github.com/SufZen/RealizeOS-5/commit/6e1a606f338e24ba988f2827a1e7a1f913c6ea0f))
* **security:** same conversation access rule for MCP chat tools ([fd7cb4a](https://github.com/SufZen/RealizeOS-5/commit/fd7cb4ac1420bf1714f0815a282a2d9bb2bc13f7))

## [5.9.0](https://github.com/SufZen/RealizeOS-5/compare/v5.8.0...v5.9.0) (2026-10-12)

### Features

* **governance:** approvals hold, then execute (brief item 2) ([123d237](https://github.com/SufZen/RealizeOS-5/commit/123d237c19bb8c4541e96d812fa8b6b5d78dbe86))

### Bug Fixes

* **governance:** atomic decisions, expiry, decider, fail-closed writes ([8996005](https://github.com/SufZen/RealizeOS-5/commit/8996005d05c09daf3da475f3c27ab7a52a518f7d))
* **security:** keep tool output out of conversations and MCP responses ([9a3a2fb](https://github.com/SufZen/RealizeOS-5/commit/9a3a2fbde3b1123b292e2bdede0a34a8cba84243))

## [5.8.0](https://github.com/SufZen/RealizeOS-5/compare/v5.7.0...v5.8.0) (2026-10-10)

### Features

* **agents:** agents use tools while they answer (governed tool loop) ([b0fc8c3](https://github.com/SufZen/RealizeOS-5/commit/b0fc8c3532d3d5d78bed6b23690e268382d391fd))

### Bug Fixes

* **security:** only execute tools that were offered to the model ([eb3f0c8](https://github.com/SufZen/RealizeOS-5/commit/eb3f0c83047a5aaefee4f8f14ea95afb9d4b5239))

## [5.7.0](https://github.com/SufZen/RealizeOS-5/compare/v5.6.3...v5.7.0) (2026-10-10)

### Features

* **tools:** register Google, Sheets, ClickUp and MCP tools in the registry ([2dcc256](https://github.com/SufZen/RealizeOS-5/commit/2dcc2562f93baeaf43d8d7795e038189cd169ffa))

### Bug Fixes

* **security:** confine agent Drive paths; don't trust MCP read-only hints ([7768fe1](https://github.com/SufZen/RealizeOS-5/commit/7768fe15abfbc4c8fc4a67ec2cc85c35516422a1))
* **security:** sanitize Drive file names before writing downloads ([a04107f](https://github.com/SufZen/RealizeOS-5/commit/a04107f328ad0f24430a32d52f5c545cc900afea))

## [5.6.3](https://github.com/SufZen/RealizeOS-5/compare/v5.6.2...v5.6.3) (2026-10-10)

### Bug Fixes

* repair code paths that referenced missing modules and columns ([c734b4f](https://github.com/SufZen/RealizeOS-5/commit/c734b4ff865c5164673a5aa763bb7c69785e896d))

## [5.6.2](https://github.com/SufZen/RealizeOS-5/compare/v5.6.1...v5.6.2) (2026-10-10)

### Bug Fixes

* **security:** close CodeQL path-traversal, SSRF and info-exposure findings ([9414b90](https://github.com/SufZen/RealizeOS-5/commit/9414b90b308f1220c6f1439f85db3d228cccad50))
* **security:** pin guarded requests to the vetted IP (DNS rebinding) ([32a38a7](https://github.com/SufZen/RealizeOS-5/commit/32a38a77b8a8f0dfd1100ce7d801d6823747fec1))

## [5.6.1](https://github.com/SufZen/RealizeOS-5/compare/v5.6.0...v5.6.1) (2026-10-10)

### Bug Fixes

* **ci:** restore green CI — pin ruff, cap mcp<2, FastAPI/Typer compat ([4c516c9](https://github.com/SufZen/RealizeOS-5/commit/4c516c98f509c5a14b4005a3592f298cadf69d60))

## [5.6.0](https://github.com/SufZen/RealizeOS-5/compare/v5.5.3...v5.6.0) (2026-06-14)

### Features

* **channels:** add email Dream-Inbox digest channel (spec 003) ([9e50b6a](https://github.com/SufZen/RealizeOS-5/commit/9e50b6aeb3dd8d5b566ca87b78caac4c3020df29))
* **dreaming:** close the loop — apply-loop + scheduled Curator (spec 004) ([cfd97d2](https://github.com/SufZen/RealizeOS-5/commit/cfd97d2621a23a84eac95404cd2c9d0fa9494ce5))
* **dreaming:** per-venture trust policy ([ef0f2f0](https://github.com/SufZen/RealizeOS-5/commit/ef0f2f04783d7b9ce7e9a6dae7f431bf82bcec9d))
* **dreaming:** scheduled Reflex enrichment pass ([a810e8a](https://github.com/SufZen/RealizeOS-5/commit/a810e8ad22181289eee915ef96df62d85d261818))
* **dreaming:** unified wall-clock scheduler for digest + curator ([4973d49](https://github.com/SufZen/RealizeOS-5/commit/4973d49e3ee20e122758ec5bbebf49cc75abcf4c))
* **dreaming:** urgent email alert on blocked forbidden-write (spec 003 US2) ([f0b8a15](https://github.com/SufZen/RealizeOS-5/commit/f0b8a15799707a9435e2f1b5d4d75a77621231e6))
* **governance:** enforce trust ladder at the tool-dispatch chokepoint ([a8430e2](https://github.com/SufZen/RealizeOS-5/commit/a8430e2d949853082c8e95bbf633bd3d51411734))
* **runtimes:** add HermesAdapter + register adapters at startup ([4bc1d1f](https://github.com/SufZen/RealizeOS-5/commit/4bc1d1fcbd269321068e7f27cd5fe45da90a670b))

### Bug Fixes

* **security:** confine venture_key in load_for_venture (path-injection) ([7d53174](https://github.com/SufZen/RealizeOS-5/commit/7d531745cf186b74773f0708f21b82ec3e8a1303))
* **security:** match venture_key against real dirs (no path expr) ([f1da630](https://github.com/SufZen/RealizeOS-5/commit/f1da6300cacb8ffbcf305828e1ca7ebf30b9bca7))

## [5.5.3](https://github.com/SufZen/RealizeOS-5/compare/v5.5.2...v5.5.3) (2026-06-14)

### Bug Fixes

* **mcp:** make built-in MCP SSE transport actually work ([c964b9f](https://github.com/SufZen/RealizeOS-5/commit/c964b9f3cde52207e93be16b8b94cb42719c191a))

## [5.5.2](https://github.com/SufZen/RealizeOS-5/compare/v5.5.1...v5.5.2) (2026-05-27)

### Bug Fixes

* **lint:** exclude auto-generated CHANGELOG.md from markdownlint ([5e03ea0](https://github.com/SufZen/RealizeOS-5/commit/5e03ea0f3e28a0d9a17389aeae4af7a6f18456ed))

## [5.5.1](https://github.com/SufZen/RealizeOS-5/compare/v5.5.0...v5.5.1) (2026-05-27)

### Bug Fixes

* **release:** add workflow_dispatch trigger + Node 22 for release pipeline ([1ccd248](https://github.com/SufZen/RealizeOS-5/commit/1ccd24843319b6ecbe7d6ac4841e098c4b58ebdc))

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
