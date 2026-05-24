# RealizeOS v5.5.0 — Handoff Setup Plan (Tasks 1–3)

## Context

This plan is the deliverable for **Tasks 1–3** of the handoff prompt. The prior planning session produced five design documents but couldn't see the repo; this plan reconciles those targets against the real state of `SufZen/RealizeOS-5` at v5.2.1 and proposes the order of operations for the Phase A–F infrastructure rollout, **before any feature implementation begins**.

No spec-kit install, no infra changes, no implementation are part of this plan — only relocating the five design docs into `docs/v5.5.0/` (a `docs/` subfolder that is already excluded from the Python product package) plus producing the analysis. Asaf's approval gates the next step.

---

## 1. What I Read

**Design docs** (all five, in `C:\Users\USER\Downloads\New folder\`):

- `realizeos-v5.5.0-master-design.md` — 17-section canonical architecture, May 2026, Draft v3
- `runtime-adapter-contract.md` — v0.1 Python Protocol + data types + lifecycle + 7 adapter sketches
- `fabric-semantic-tags.md` — v0.1 vocabulary of 13 canonical XML tags inside markdown
- `fabric-entity-schemas.md` — JSON Schemas (Draft 2020-12) for decision, mission, contact, commitment, insight
- `development-infrastructure-setup.md` — 11 GH workflows, 5-tier testing, Phase A–F migration

**Repo surface** (read directly):

- [pyproject.toml](pyproject.toml) — v5.2.1, ruff (light config), bandit, pytest, **no mypy, coverage `fail_under = 50`**
- [dashboard/package.json](dashboard/package.json) — React 19 / Vite 8 / Tailwind 4 / TanStack Query 5 / Lucide / pnpm; Prettier in devDeps but no `format` / `format:check` / `type-check` scripts; no Playwright, Zod, shadcn/ui
- [.github/workflows/ci.yml](.github/workflows/ci.yml) — 6 jobs: lint, test, security (safety + bandit + gitleaks), docker-build, dashboard-check (pnpm), cli-check (npm)
- [.github/workflows/release.yml](.github/workflows/release.yml) — CI → multi-arch docker to GHCR → npm publish (`@realize-os/cli`) → **PyPI Trusted Publishing already wired via OIDC** → GitHub Release
- [.gitignore](.gitignore) — `AGENTS.md`, `CLAUDE.md`, `_bmad/`, `developer_resources/`, `systems/`, `AUDIT-REPORT.md` already excluded as "Internal development (not shipped to end users)"
- Existing top-level files: `CHANGELOG.md`, `CONTRIBUTING.md`, `QUICKSTART.md`, `SECURITY.md`, `.gitleaks.toml`, `.env.example`, `requirements.txt`, `requirements-dev.txt`, Windows `*.bat` installers, `Dockerfile`, `docker-compose.{yml,prod.yml}`
- `realize_core/` — 30+ subdirs already present incl. `agents/`, `channels/`, `evolution/`, `extensions/`, `kb/`, `llm/`, `mcp_server/`, `memory/`, `optimizer/`, `skills/`, `storage/`, `tools/`, `workflows/`, plus `base_handler.py`, `cli_app/`, `setup_wizard.py`, `scaffold.py`
- `realize_api/` — separate FastAPI layer (`main.py`, `routes/`, `middleware.py`, `security_middleware.py`) — **not mentioned in v5.5.0 design doc**
- `realize_lite/` — packaged template systems (CLAUDE.md, systems/, shared/) — product code, not user data
- `realize-os-cli/` — separate TypeScript Node CLI package, published as `@realize-os/cli`
- `ventures/` — only `_templates/` present
- `systems/` — gitignored; this is where actual user venture data currently lives
- `tests/` — 90+ test files; subdirs `integration/`, `performance/`, `security/`, `data_integrity/`; **no `contract/`, `property/`, or `e2e/` yet**
- `docs/` — substantial set (PRODUCTION.md, api-reference.md, architecture.md, audit-playbook.md, cli-reference.md, concepts.md, configuration.md, full-guide.md, getting-started.md, guides/, lite-guide.md, mcp-server.md, self-hosting-guide.md, skill-authoring.md, upgrade-from-v03.md, upgrade-from-v50.md); **NOT shipped in the pip dist** (setuptools.find only includes `realize_core*`, `realize_api*`, `realize_lite*`, `templates*`)

---

## 2. Gap Analysis (Target vs. Current)

Format: **STATUS · LEVERAGE · EFFORT** — STATUS = ✅ present / ⚠ exists-needs-upgrade / ❌ missing; LEVERAGE = how much it unblocks; EFFORT = relative work.

### 2.1 Foundations (Phase A territory)

| Item | Status | Leverage | Effort |
|---|---|---|---|
| `CONTRIBUTING.md` | ✅ present | — | — |
| `SECURITY.md` | ✅ present (1.7KB) | — | — |
| `CHANGELOG.md` | ✅ present | — | — |
| Issue templates (bug, feature, config) | ✅ present | — | — |
| `.gitleaks.toml` | ✅ present | — | — |
| `.env.example` | ✅ present | — | — |
| Conventional Commits enforcement (commitlint) | ❌ missing | high (unlocks semantic-release, dream feedback signal) | low |
| `.github/PULL_REQUEST_TEMPLATE.md` | ❌ missing | medium | trivial |
| `.github/CODEOWNERS` | ❌ missing | medium (signals review surfaces; required by branch protection) | trivial |
| `.github/ISSUE_TEMPLATE/spec_proposal.md`, `dream_review.md` | ❌ missing | low (until spec-kit adopted) | trivial |
| `.github/labeler.yml` + labeler workflow | ❌ missing | low | trivial |
| `.pre-commit-config.yaml` | ❌ missing | high (catches most CI failures locally) | low |
| Branch protection rules on `main` | ⚠ unknown (settings, not in repo) — assume not configured to spec | medium | trivial |

### 2.2 Spec-Driven Methodology (Phase B)

| Item | Status | Leverage | Effort |
|---|---|---|---|
| `specify-cli` installed (uv tool) | ❌ missing | **highest** | trivial install, medium content migration |
| `.specify/memory/constitution.md` (from master design) | ❌ missing | highest | medium (one-time content migration) |
| `.specify/specs/` (contracts → specs) | ❌ missing | highest | medium |
| `/speckit.analyze` cross-artifact check | ❌ missing | high | trivial once specs exist |
| `/speckit.tasks` → `/speckit.taskstoissues` | ❌ missing | high | low |
| **Five design docs landed in repo** | ❌ still in Downloads folder | blocking | trivial |

### 2.3 Linting / Formatting / Type Checking (Phase C — Python)

| Item | Status | Leverage | Effort |
|---|---|---|---|
| ruff `lint` config | ⚠ present but minimal (`E F W I N UP`) vs target (`+ B C4 RUF ASYNC S T20 TID PT SIM PL`) | high | low |
| ruff `format` | ✅ configured | — | — |
| mypy strict | ❌ missing entirely | **high** (would surface real bugs across 30+ subdirs) | high (real failures expected; needs phased rollout) |
| pytest markers `unit / contract / property / e2e / live_llm` | ⚠ only `slow / integration` declared | medium | low |
| Coverage `fail_under = 50` | ⚠ way below target (70–90% per layer) | medium | high (measure first, then ratchet) |
| `hypothesis` (property tests) | ❌ missing | medium | medium |
| `pytest-recording` / `vcr.py` for LLM tests | ❌ missing | medium | medium |
| Bandit (via ruff `S` rules + standalone) | ✅ separate `bandit[toml]` in dev deps + standalone CI job | — | — |
| `safety` for dep vulns | ✅ present in CI (target says `pip-audit`; comparable, can swap) | — | — |

### 2.4 Linting / Formatting / Type Checking (Phase C — TypeScript)

| Item | Status | Leverage | Effort |
|---|---|---|---|
| ESLint | ✅ present (flat config, `eslint-plugin-react-hooks`) | — | — |
| Prettier in devDeps | ✅ present | — | — |
| `format` / `format:check` scripts | ❌ missing in `package.json` | medium | trivial |
| `type-check` script (`tsc --noEmit`) | ❌ missing | medium | trivial |
| Strict tsconfig (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`) | ⚠ not yet verified — likely not set | high | medium (real errors expected) |
| `eslint-plugin-jsx-a11y` | ❌ missing | medium | trivial |
| `eslint-plugin-import` | ❌ missing | low | trivial |
| Vitest coverage script | ❌ no `test:coverage` script | low | trivial |
| Playwright E2E | ❌ missing | medium (until Workspace UI work) | medium |

### 2.5 Markdown / Misc Linting

| Item | Status | Leverage | Effort |
|---|---|---|---|
| `markdownlint-cli2` + `.markdownlint-cli2.jsonc` | ❌ missing | low | trivial |
| Allow inline HTML rule (for FABRIC semantic tags) | ❌ N/A yet | low | trivial |

### 2.6 GitHub Actions Workflows (Phase C/D)

| Target workflow | Current | Gap |
|---|---|---|
| `ci.yml` (lint/format/type-check, 8 jobs) | ⚠ exists with 6 jobs covering lint/test/security/docker/dashboard/cli | needs: format check (ruff format --check is there ✅), mypy job, prettier check, tsc --noEmit job, markdownlint, commitlint |
| `test.yml` (unit/integration/contract/property/coverage matrix) | ⚠ folded into ci.yml `test` job; no matrix | split into dedicated `test.yml`, add contract/property markers, add coverage upload (Codecov) |
| `security.yml` (bandit/pip-audit/npm-audit/CodeQL/gitleaks/trivy/osv) | ⚠ partial: `safety + bandit + gitleaks` already in ci.yml | add: CodeQL, trivy (container scan), osv-scanner; consider swapping `safety` → `pip-audit` |
| `license-check.yml` (pip-licenses + node license-checker + allow-list) | ❌ missing | **important for BSL hygiene** |
| `contract-validation.yml` (JSON Schema lint, runtime-adapter conformance, manifest validation, speckit.analyze) | ❌ missing (no contracts yet to validate) | low priority until contracts land |
| `release.yml` (semantic-release, multi-arch docker, PyPI OIDC, GHCR, GH Release) | ✅ mature — multi-arch docker, npm `@realize-os/cli`, PyPI OIDC, GHCR all working | add: `semantic-release` for automated version bump + changelog from Conventional Commits |
| `dependency-update.yml` (Renovate or Dependabot) | ❌ missing | medium |
| `pr-labeler.yml` | ❌ missing | low |
| `stale.yml` | ❌ missing | low |
| `docs.yml` (MkDocs Material → GH Pages) | ❌ missing | low |
| `install-test.yml` (verify one-liner installs across OSes) | ❌ missing — but Windows `.bat` installers exist | medium |
| `gh-aw` agentic workflows | ❌ not adopted | medium (after spec-kit settles) |

### 2.7 AGENTS.md and Dev-only Documentation

| Item | Current | Notes |
|---|---|---|
| `AGENTS.md` at repo root | ❌ does not exist AND **explicitly gitignored** as "internal development, not shipped to end users" | The infrastructure doc writes AGENTS.md as if it should be tracked at root. Asaf's convention currently treats AGENTS.md / CLAUDE.md / `_bmad/` / `developer_resources/` as gitignored dev material. **Decision needed** (see §4). |
| Five design docs in repo | ❌ currently in `C:\Users\USER\Downloads\New folder\` | Recommended landing: `docs/v5.5.0/` (tracked, but NOT in pip dist because setuptools.find excludes `docs/`). |

### 2.8 Naming/Convention Drift Between Design and Reality

These need surfacing as ADRs before code starts moving:

1. **`ventures/<key>/` vs `systems/<key>/`** — design says `ventures/`, repo has `systems/` (gitignored). Either the design changes terminology or v5.5.0 introduces a directory rename + migration script. Calling this out as **ADR-0001 candidate**.
2. **`realize_api/` exists** but isn't in the design doc's file layout. Either fold into the design (likely it's "the REST channel adapter implementation") or formally separate as a "Senses-layer Limb." **ADR-0002 candidate**.
3. **`realize_lite/` packaged template systems** — fits the design's "templates/" notion but should be documented explicitly so spec-kit specs don't accidentally re-invent.

---

## 3. Proposed Setup Sequence (Phases A–F adapted)

Concrete order of operations, scoped to my one-session reach. Each step is small, reversible, and ends at a checkpoint where Asaf can stop, redirect, or merge.

### Phase 0 — Land the design docs (this session, after approval)

1. Create `docs/v5.5.0/` in the repo
2. Copy the five design docs verbatim from `C:\Users\USER\Downloads\New folder\` into `docs/v5.5.0/`
3. Add a one-page `docs/v5.5.0/README.md` index pointing at the five docs and noting "pre-spec-kit staging location; will migrate to `.specify/` in Phase B"
4. Confirm `docs/` is still excluded from the Python source dist by inspecting `MANIFEST.in` (if any) and the existing `setuptools.find` config — no change needed
5. Commit on a `chore/v5.5.0-design-docs` branch with a single Conventional Commit (`docs(v5.5.0): land master design + contracts + schemas + infra spec`)
6. Open PR; merge on Asaf's approval

**Why now, not after Phase B:** the spec-kit migration in Phase B will move three of these docs into `.specify/`. But until spec-kit is set up, having them in the repo first means every other Phase A action can reference stable paths, not files on a Downloads folder.

### Phase A — Foundation hygiene (1–2 sessions)

1. **Conventional Commits**: add `commitlint.config.js` + npm dev dep, wire into pre-commit + `ci.yml`
2. **`.github/PULL_REQUEST_TEMPLATE.md`**: paste the template from the infrastructure doc
3. **`.github/CODEOWNERS`**: per-area ownership, just `@SufZen` for now
4. **`.github/labeler.yml`** + `pr-labeler.yml` workflow
5. **Add issue templates**: `spec_proposal.md`, `dream_review.md`
6. **Pre-commit hooks** (`.pre-commit-config.yaml`): ruff, ruff-format, mypy (initial scope: a few clean modules only), markdownlint, commitlint
7. **Branch protection rules** on `main` (Asaf does this in GitHub UI; I produce the checklist)

**Checkpoint:** every new commit goes through commitlint + pre-commit; PRs use the template; status checks are codified.

### Phase B — spec-kit adoption (1 session)

1. `uv tool install --from git+https://github.com/github/spec-kit.git@v0.8.11 specify-cli`
2. `specify init . --integration claude --integration copilot --integration codex`
3. Migrate `docs/v5.5.0/realizeos-v5.5.0-master-design.md` → `.specify/memory/constitution.md` (with light editorial pass to fit constitution format)
4. Migrate the three contract/vocabulary docs into `.specify/specs/000-runtime-adapter/`, `001-fabric-semantic-tags/`, `002-fabric-entity-schemas/`
5. Run `/speckit.analyze` to surface cross-artifact inconsistencies (we already know two: `ventures/` vs `systems/`, undocumented `realize_api/`)
6. Run `/speckit.tasks` against each spec to generate task lists
7. **Defer `/speckit.taskstoissues` until after Asaf reviews** — we don't want to spam the issue tracker prematurely
8. Decide AGENTS.md handling (see §4 below) and either un-gitignore + write fresh, or place at `.specify/AGENTS.md`

**Checkpoint:** specs are the source of truth; any feature work has a referenceable spec ID.

### Phase C — Quality gates (1–2 sessions)

1. **Python**:
   - Expand `[tool.ruff.lint] select` to the full target set
   - Add `[tool.mypy]` strict config (start with `disallow_untyped_defs = false`, ratchet up)
   - Add `mypy` to `ci.yml` as a separate job (initial scope: `realize_core/storage/` and `realize_core/llm/` — clean modules — and expand)
   - Add pytest markers: `unit`, `contract`, `property`, `e2e`, `live_llm`
   - Add `hypothesis`, `pytest-recording` to dev deps (deferred use until tests need them)
   - Measure current coverage, set `fail_under` to current minus 5%, ratchet per PR
2. **TypeScript**:
   - Add `format`, `format:check`, `type-check`, `test:coverage` scripts to `dashboard/package.json`
   - Add `eslint-plugin-jsx-a11y` + `eslint-plugin-import`
   - Tighten `tsconfig.json` toward `noUncheckedIndexedAccess` (expect failures; fix or stage)
   - Add explicit `type-check-typescript` + `format-typescript` jobs to `ci.yml`
3. **Markdown**:
   - Add `markdownlint-cli2` + `.markdownlint-cli2.jsonc` with the FABRIC-aware rule set (allow inline HTML, allow long lines)
   - Wire into pre-commit and CI
4. **License hygiene**:
   - Add `license-check.yml` workflow with `pip-licenses` + `license-checker` (Node) + allow-list (MIT/Apache-2.0/BSD/ISC/PostgreSQL/MPL-2.0)
   - Document the `pygit2` GPL-2.0-with-linking-exception in `docs/license-exceptions.md` (deferred until we actually pull pygit2 in Phase 1)
5. **CodeQL**: add `security.yml` (or extend ci.yml `security` job) with `codeql-action`

**Checkpoint:** PRs fail loudly on type errors, format drift, markdown issues, license incompatibilities, and security findings.

### Phase D — Release automation refinement (1 session)

- The existing `release.yml` is **already mature** (multi-arch docker, PyPI OIDC, npm publish, GH Release). The gap is automated version-bump-from-commits.
- Adopt `semantic-release` (Node) or `python-semantic-release`. Pick one based on which fits cleanly into the existing release.yml.
- Generate `CHANGELOG.md` automatically from Conventional Commits since last tag.
- Add cosign signing step for docker images (keyless via GitHub OIDC).

**Checkpoint:** tagging a release is "merge a Conventional Commit to main" — version bump, changelog, tag, docker, npm, PyPI, GH Release all chain automatically.

### Phase E — Agentic workflows (1 session)

1. `gh extension install github/gh-aw`
2. Adopt: Workflow Health Manager, Daily Test Improver, CLI Consistency Checker (3 starters from the infrastructure doc)
3. Author one custom: `daily-fabric-validator.md` once we have FABRIC fixtures to validate (deferred until Phase 1 of the v5.5.0 migration)

**Checkpoint:** the repo now does its own development dreaming — coverage gaps file PRs, CLI inconsistencies file PRs, workflow health is monitored.

### Phase F — Stable cadence (ongoing)

1. Set up Renovate (preferred over Dependabot per the infrastructure doc) with `renovate.json`
2. Add `stale.yml`
3. Add nightly `e2e` slot in `test.yml` (no-op until Workspace UI exists; the slot is reserved)
4. Run one full `/speckit.implement` end-to-end to validate the loop (suggested first target: wrap existing internal agents as the first Runtime Adapter — the kill-switch milestone for Phase 2 of the v5.5.0 migration)

**Checkpoint:** infrastructure is done. Implementation begins.

---

## 4. Locked Decisions (Asaf 2026-05-24)

1. **AGENTS.md handling — hybrid.** Tracked content at `docs/development/AGENTS.md` (already excluded from the pip dist via `docs/` not being in `setuptools.find`). The root `AGENTS.md` line in `.gitignore` stays as-is — Asaf's private root copy is undisturbed. Setup script (Phase A) optionally symlinks or copies `docs/development/AGENTS.md` to a root `AGENTS.md` for local dev convenience, but the canonical tracked location is `docs/development/AGENTS.md`. Spec-kit will additionally create whatever it creates under `.specify/`.
2. **Design docs landing — `docs/v5.5.0/`.** Tracked, available to developers and AI agents, NOT shipped in the pip dist. After Phase B migration, the three contract docs move into `.specify/specs/`; the master design moves to `.specify/memory/constitution.md`; the infrastructure doc stays at `docs/development/infrastructure.md` (it's a target-state operations doc, not a spec).
3. **`ventures/` vs `systems/` — defer to v5.5.0 Phase 1.** The rename happens as part of the FABRIC git-ification phase with a one-time migration script that touches install/uninstall/migrate. No code change in Phases A–F of this infra rollout.

### Still-open (lower-stakes) calls — my recommendations, will not block proceeding

- **`realize_api/` status.** Stay separate as the REST channel implementation, with a clean import boundary documented in Phase B's spec migration. Don't fold into `realize_core/channels/` yet.
- **First post-infra implementation target.** Wrap the existing internal agents as the first Runtime Adapter — the Phase 2 kill-switch milestone from the master design. Proves the abstraction without touching the Heart.

---

## 5. Critical Files (paths for the next executor)

These are the surfaces every subsequent phase touches:

- [pyproject.toml](pyproject.toml) — ruff, mypy, pytest, coverage config; package list
- [dashboard/package.json](dashboard/package.json) — scripts, deps
- [dashboard/tsconfig.json](dashboard/tsconfig.json) — TS strictness knobs
- [.github/workflows/ci.yml](.github/workflows/ci.yml) — primary CI surface to extend
- [.github/workflows/release.yml](.github/workflows/release.yml) — already mature; light additions only
- [.gitignore](.gitignore) — needs the `AGENTS.md` line removed (pending §4 decision)
- `requirements.txt` + `requirements-dev.txt` — Python deps (separate from pyproject)
- `.gitleaks.toml` — already present, may need new allowlist entries as fixtures change
- `realize_core/` — 30+ subdirs to keep stable while the Heart-out reorg lands
- `docs/v5.5.0/` — proposed staging location for the five design docs

Functions/utilities worth reusing (no need to re-derive):

- [realize_core/base_handler.py](realize_core/base_handler.py) — extended by the Mission Engine per design
- [realize_core/llm/](realize_core/llm/) — Claude/Gemini/OpenAI/Ollama auto-discovery; extend with provider tagging
- [realize_core/mcp_server/](realize_core/mcp_server/) — existing 24-tool MCP role; extend with L3 catalog
- [realize_core/extensions/](realize_core/extensions/) — existing tool/channel/integration/hook plugin system; Runtime adapters fit here
- [realize_core/agents/](realize_core/agents/) — wrapped as the first `RealizeInternal` Runtime adapter
- [realize_core/skills/](realize_core/skills/) — feeds `export_skills()`
- [realize_core/storage/](realize_core/storage/) — pygit2 integration target
- [realize_api/](realize_api/) — REST channel implementation; reuse, document, don't merge

---

## 6. Verification

Each phase has its own verification, but all share one principle: **CI must remain green after every checkpoint.** If a phase turns CI red and can't be made green in a single follow-up commit, roll the phase back.

Per-phase tests:

- **Phase 0**: `git ls-files docs/v5.5.0/` shows the five .md files; `python -m build` produces a wheel that does NOT include them (verifies docs/ exclusion).
- **Phase A**: `git commit -m "test: invalid format"` fails at commit-msg hook; `pre-commit run --all-files` succeeds on the clean tree.
- **Phase B**: `specify --version` succeeds; `/speckit.analyze` runs and reports the two known drift items (`ventures/` vs `systems/`, undocumented `realize_api/`).
- **Phase C**: `ruff check`, `mypy realize_core/storage/ realize_core/llm/`, `pnpm -C dashboard type-check`, `markdownlint-cli2 "**/*.md"` all green; CI workflow runs the same.
- **Phase D**: a chore-only PR merged to `main` automatically tags `v5.2.2`, updates CHANGELOG, builds & signs docker, publishes npm and PyPI.
- **Phase E**: `gh aw status` lists the three adopted workflows; each runs once on schedule without failure.
- **Phase F**: Renovate opens its first PR; one full spec → plan → tasks → implementation loop completes for the `RealizeInternal` runtime adapter.

---

## 7. What Comes Next, In One Sentence

Once Asaf confirms §4 decisions (especially the AGENTS.md handling and the `docs/v5.5.0/` landing location), Phase 0 begins: relocate the five design docs into the repo as a single PR, then proceed phase-by-phase with a checkpoint after each.
