# RealizeOS v5.5.0 — Development Infrastructure Setup

> Target state for branch protection, code review, testing, linting, GitHub Actions, release automation, AGENTS.md, and repository settings — calibrated for a solo-led, multi-collaborator, multi-runtime, spec-driven project under BSL 1.1.
>
> Target location: `docs/development-infrastructure.md`  
> Status: Recommendations v0.1 — diff against current `.github/`, `pyproject.toml`, `package.json`, and `AGENTS.md` to identify gaps  
> License: MIT

---

## Table of Contents

1. [Strategic Adoptions](#1-strategic-adoptions)
2. [Branch Protection & Review Policies](#2-branch-protection--review-policies)
3. [Testing Strategy](#3-testing-strategy)
4. [Linting, Formatting, Type Checking](#4-linting-formatting-type-checking)
5. [GitHub Actions — Complete Workflow Set](#5-github-actions--complete-workflow-set)
6. [Release & Publishing Automation](#6-release--publishing-automation)
7. [Updated AGENTS.md](#7-updated-agentsmd)
8. [Repository Settings Checklist](#8-repository-settings-checklist)
9. [Secrets & Credentials Management](#9-secrets--credentials-management)
10. [Migration Path](#10-migration-path)

---

## 1. Strategic Adoptions

Three tools to adopt before v5.5.0 work begins:

### 1.1 spec-kit (Mandatory)

**Adopt as the development methodology.** The Spec-Driven Development workflow mirrors what we've already been doing in design; formalizing it eliminates ad-hoc structure.

Install:
```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v0.8.11
specify init . --integration copilot --integration claude --integration codex
```

What this gives you:
- `/speckit.constitution` — promote your existing master design doc into `.specify/memory/constitution.md`
- `/speckit.specify` — convert the runtime adapter contract, semantic tags vocabulary, and entity schemas into `.specify/specs/` folders
- `/speckit.clarify` — structured question loops before planning
- `/speckit.plan` — generate technical plans against a constitution
- `/speckit.tasks` — break plans into actionable parallelizable tasks
- `/speckit.taskstoissues` — auto-convert tasks into GitHub issues
- `/speckit.analyze` — cross-artifact consistency check
- `/speckit.checklist` — generate quality validation checklists

Every AI agent you've discussed adapting as a RealizeOS Runtime — Claude Code CLI, Codex CLI, Gemini CLI, Hermes — recognizes these slash commands. Spec-kit becomes the lingua franca across runtimes during v5.5.0 development.

### 1.2 GitHub Agentic Workflows / gh-aw (Strong Recommend)

`github/gh-aw` is in technical preview. Lets you write GitHub Actions workflows as plain Markdown with AI agents handling intent. Direct fit for RealizeOS:
- Workflow Health Manager — monitors all your other agentic workflows
- Daily Testify Expert — analyzes test quality nightly
- Daily Test Improver — proposes new tests for coverage gaps
- CLI Consistency Checker — keeps CLI surface coherent
- Multi-Device Docs Tester — Playwright tests on multiple screen sizes

This is the **dreaming pattern applied to your repo's own development**, mirroring exactly what RealizeOS itself will do for its users. Eat your own dogfood from day one.

Install:
```bash
gh extension install github/gh-aw
gh aw add-wizard https://github.com/github/gh-aw/blob/v0.45.5/.github/workflows/daily-testify-uber-super-expert.md
```

Adopt 3 to start (more later):
1. Workflow Health Manager (meta-orchestrator)
2. Daily Test Improver (coverage gaps → PRs)
3. CLI Consistency Checker (your CLI surface stays coherent)

### 1.3 Conventional Commits + semantic-release

Adopt Conventional Commits format for all commit messages. This unlocks:
- Automated CHANGELOG.md generation
- Automated semver bump decisions
- Automated GitHub release creation
- Clean git history for the Dreaming subsystem to learn from

Format:
```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`, `dream` (custom: for changes proposed by the Dreaming subsystem when it lands).

---

## 2. Branch Protection & Review Policies

### 2.1 Branch Strategy

```
main         ← protected; production-ready code only
develop      ← optional integration branch (use only if multi-person team forms)
feature/*    ← active development; PRs into main (or develop)
fix/*        ← bug fixes
chore/*      ← non-functional changes
docs/*       ← documentation-only
spec/*       ← spec-kit spec development
dream/*      ← reserved for the future Dreaming subsystem's auto-applied changes
release/*    ← release-prep branches if needed
```

For solo work right now, skip `develop`. PRs go feature → main.

### 2.2 Main Branch Protection Rules

Enable in GitHub repo settings → Branches → Branch protection rules → main:

- ✅ Require a pull request before merging
- ✅ Require approvals: 1 (when collaborators join; 0 for solo with self-review discipline)
- ✅ Dismiss stale pull request approvals when new commits are pushed
- ✅ Require review from Code Owners
- ✅ Require status checks to pass before merging:
  - `lint-python`
  - `lint-typescript`
  - `type-check-python`
  - `type-check-typescript`
  - `test-python-unit`
  - `test-typescript-unit`
  - `test-integration`
  - `security-scan`
  - `license-check`
  - `contract-validation`
- ✅ Require branches to be up to date before merging
- ✅ Require conversation resolution before merging
- ✅ Require signed commits (set up GPG signing)
- ✅ Require linear history (squash or rebase only; no merge commits)
- ✅ Do not allow bypassing the above settings
- ✅ Restrict who can push to matching branches: just you for now
- ❌ Force pushes: disabled
- ❌ Deletions: disabled

### 2.3 CODEOWNERS

Create `.github/CODEOWNERS`:

```
# Global default
*                                   @SufZen

# Backend core
/realize_core/                      @SufZen
/realize_core/runtimes/             @SufZen
/realize_core/synapse/              @SufZen
/realize_core/dreaming/             @SufZen
/realize_core/heart/                @SufZen

# Frontend
/dashboard/                         @SufZen
/mobile/                            @SufZen

# Documentation & contracts
/docs/                              @SufZen
/docs/contracts/                    @SufZen
/docs/fabric-schemas/               @SufZen
/AGENTS.md                          @SufZen

# Specs (spec-kit)
/.specify/                          @SufZen
/.specify/memory/constitution.md    @SufZen

# Infrastructure
/.github/                           @SufZen
/.github/workflows/                 @SufZen

# Sensitive
/LICENSE                            @SufZen
/SECURITY.md                        @SufZen
```

When collaborators (Meirav, Miguel, Aldad, etc.) join, add them per area: `@meirav-handle` for `/docs/business/`, etc.

### 2.4 Pull Request Templates

Create `.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## Summary
<!-- One-line description of what this PR does -->

## Type
<!-- Check all that apply -->
- [ ] feat: new feature
- [ ] fix: bug fix
- [ ] docs: documentation only
- [ ] refactor: code change that neither fixes a bug nor adds a feature
- [ ] perf: performance improvement
- [ ] test: adding or fixing tests
- [ ] chore: tooling, dependencies, build
- [ ] ci: CI/CD configuration
- [ ] spec: specification document
- [ ] dream: proposed by Dreaming subsystem (after Phase 6)

## Spec Reference
<!-- Link to the relevant /speckit specification(s) -->
- Spec:
- Plan:
- Task ID(s):

## Changes
<!-- What changed, in plain language -->

## Testing
<!-- How was this validated -->
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing notes:

## Contract Impact
<!-- Does this affect any of the v0.1 contracts? -->
- [ ] Runtime Adapter Contract — version impact:
- [ ] Semantic Tag Vocabulary — version impact:
- [ ] FABRIC Schemas — version impact:
- [ ] No contract impact

## Local-First Compliance
- [ ] No new third-party-cloud dependencies added without provider tagging
- [ ] No telemetry added (or opt-in only with transparent logging)
- [ ] No credentials stored in plaintext
- [ ] FABRIC writes go through the proper API (no direct filesystem writes by runtimes)

## License Compatibility
- [ ] All new dependencies are MIT / Apache-2.0 / BSD / ISC / PostgreSQL License
- [ ] No AGPL/GPL dependencies added (or documented exception in /docs/license-exceptions.md)

## Checklist
- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review
- [ ] I have commented complex code
- [ ] I have updated documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or my feature works
- [ ] New and existing unit tests pass locally
```

### 2.5 Issue Templates

Create `.github/ISSUE_TEMPLATE/`:

- `bug_report.md` — bug reports
- `feature_request.md` — new feature requests
- `spec_proposal.md` — proposed spec changes
- `dream_review.md` — for the future Dreaming subsystem to file proposals as issues
- `security_vulnerability.md` — points to SECURITY.md

Add `.github/ISSUE_TEMPLATE/config.yml`:
```yaml
blank_issues_enabled: false
contact_links:
  - name: Security vulnerability
    url: mailto:security@suf.zen
    about: Report security issues privately (do not file as a public issue)
  - name: Discussion
    url: https://github.com/SufZen/RealizeOS-5/discussions
    about: General questions, ideas, and discussions
```

### 2.6 Auto-Labeling

Create `.github/labeler.yml`:
```yaml
backend:
  - changed-files:
    - any-glob-to-any-file:
      - 'realize_core/**'
      - 'pyproject.toml'

frontend:
  - changed-files:
    - any-glob-to-any-file:
      - 'dashboard/**'
      - 'mobile/**'

docs:
  - changed-files:
    - any-glob-to-any-file:
      - 'docs/**'
      - '*.md'

specs:
  - changed-files:
    - any-glob-to-any-file: '.specify/**'

contracts:
  - changed-files:
    - any-glob-to-any-file: 'docs/contracts/**'

ci:
  - changed-files:
    - any-glob-to-any-file:
      - '.github/**'

dreaming:
  - changed-files:
    - any-glob-to-any-file: 'realize_core/dreaming/**'

runtimes:
  - changed-files:
    - any-glob-to-any-file: 'realize_core/runtimes/**'

synapse:
  - changed-files:
    - any-glob-to-any-file: 'realize_core/synapse/**'
```

---

## 3. Testing Strategy

Five tiers of testing, scaling rigor with risk.

### 3.1 Unit Tests (foundation)

**Python: pytest + pytest-asyncio + pytest-cov**

Coverage targets:
- `realize_core/heart/` — 90%+ coverage (the kernel, mistakes are expensive)
- `realize_core/spine/` — 85%+
- `realize_core/synapse/` — 85%+
- `realize_core/runtimes/` — 75%+ (each adapter individually testable)
- `realize_core/dreaming/` — 80%+
- Other modules — 70%+ baseline

**TypeScript: Vitest** (better Vite integration than Jest, fast, native ESM)

Coverage targets:
- Component logic — 80%+
- API client and state management — 85%+
- Graph viz — 70%+ (UI heavy, supplement with E2E)

### 3.2 Integration Tests

Mark with `@pytest.mark.integration`. Cover:
- FABRIC + Synapse end-to-end (write to FABRIC, verify L1/L2 update)
- Runtime adapter contract conformance (each adapter passes a shared test suite)
- Mission engine execution (real LLM calls against mocks, then optional live in nightly)
- Sync protocol (two RealizeOS instances, federate, verify consistency)
- Channel adapters (mock external services)

Run on every PR (with mocked LLMs) + nightly (with live LLM endpoints in a sandbox).

### 3.3 Contract Conformance Tests

For each new contract version, a **shared test suite** that any implementation must pass:
- Runtime Adapter conformance: `tests/contract/test_runtime_adapter_v0_1.py`
- Tool Registry conformance: `tests/contract/test_tool_protocol.py`
- Channel adapter conformance: `tests/contract/test_channel_adapter.py`

Every new runtime adapter, channel, or tool wrapper must pass the matching contract suite before being merged.

### 3.4 Property-Based Tests

`hypothesis` library for Python. Particularly valuable for:
- FABRIC content parsing (semantic tags, edge cases)
- Entity ID generation (uniqueness, collision resistance)
- Mission state machine (no invalid transitions)
- Trust Policy decisions (no proposal escapes the policy enforcement)

### 3.5 End-to-End Tests

**Playwright** for the workspace UI. Cover critical journeys:
- New venture creation flow
- Mission inbox approval flow
- Knowledge graph navigation
- Voice capture (mocked Whisper)
- Dream Inbox review and approval

Run on every PR (smoke set, ~30s) + nightly (full suite, ~5min).

### 3.6 Test Layout

```
tests/
├── unit/
│   ├── heart/
│   ├── spine/
│   ├── synapse/
│   ├── runtimes/
│   ├── dreaming/
│   └── ...
├── integration/
│   ├── fabric_synapse/
│   ├── mission_execution/
│   ├── sync_protocol/
│   └── ...
├── contract/
│   ├── test_runtime_adapter_v0_1.py
│   ├── test_tool_protocol_v0_1.py
│   └── ...
├── property/
│   ├── test_fabric_parsing.py
│   ├── test_entity_ids.py
│   └── ...
├── e2e/
│   ├── workspace/
│   ├── mobile/
│   └── ...
├── fixtures/
│   ├── ventures/                  # sample FABRIC ventures
│   ├── missions/                  # sample missions for replay
│   └── llm_recordings/            # recorded LLM responses via VCR
└── conftest.py
```

### 3.7 LLM Test Recording (VCR pattern)

Use `vcr.py` or `pytest-recording` for Python. Record real LLM responses once, replay deterministically afterwards. Re-record monthly or on intentional model swap. Keeps tests fast and free while remaining faithful to actual provider behavior.

---

## 4. Linting, Formatting, Type Checking

### 4.1 Python

`pyproject.toml` additions:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
src = ["realize_core", "tests"]

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "B",      # bugbear
    "C4",     # comprehensions
    "UP",     # pyupgrade
    "RUF",    # ruff-specific
    "N",      # pep8-naming
    "ASYNC",  # async best practices
    "S",      # security (bandit)
    "T20",    # no print statements in library code
    "TID",    # tidy imports
    "PT",     # pytest style
    "SIM",    # simplifications
    "PL",     # pylint subset
]
ignore = ["E501", "PLR0913"]  # line length handled by formatter; argument count flexibility

[tool.ruff.lint.per-file-ignores]
"tests/**/*" = ["S101", "PLR2004", "S311"]  # allow asserts and magic values in tests

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["tests.*"]
disallow_untyped_defs = false  # tests can be looser

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "unit: unit tests (fast, isolated)",
    "integration: integration tests (slower, may use real services)",
    "contract: contract conformance tests",
    "property: property-based tests via hypothesis",
    "e2e: end-to-end browser tests",
    "slow: tests that take >5s",
    "live_llm: tests requiring real LLM API calls",
]
addopts = "--strict-markers --strict-config --cov=realize_core --cov-report=term-missing --cov-report=xml"
```

### 4.2 TypeScript

`package.json` scripts:

```json
{
  "scripts": {
    "lint": "eslint --max-warnings=0 .",
    "lint:fix": "eslint --fix .",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "type-check": "tsc --noEmit",
    "test": "vitest",
    "test:coverage": "vitest --coverage",
    "test:e2e": "playwright test"
  }
}
```

`tsconfig.json` strictness:
```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "exactOptionalPropertyTypes": true
  }
}
```

ESLint config (`eslint.config.js`, flat config):
- `@typescript-eslint/recommended-type-checked`
- `@typescript-eslint/strict-type-checked`
- `eslint-plugin-react`
- `eslint-plugin-react-hooks`
- `eslint-plugin-jsx-a11y` (accessibility)
- `eslint-plugin-import` (order, no-cycle)

### 4.3 Markdown

Adopt `markdownlint-cli2` (spec-kit uses it):

`.markdownlint-cli2.jsonc`:
```jsonc
{
  "config": {
    "default": true,
    "MD013": false,           // line length (long docs are OK)
    "MD024": { "siblings_only": true },
    "MD033": false,           // allow inline HTML (we use it for FABRIC semantic tags)
    "MD036": false,           // bold as heading (used in our docs)
    "MD041": false            // first line heading
  },
  "globs": ["**/*.md"],
  "ignores": ["node_modules", "dist", ".specify/templates"]
}
```

### 4.4 Pre-commit Hooks

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-toml
      - id: check-added-large-files
        args: ['--maxkb=1000']
      - id: check-merge-conflict
      - id: detect-private-key
      - id: mixed-line-ending

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, types-PyYAML, types-requests]

  - repo: https://github.com/igorshubovych/markdownlint-cli
    rev: v0.42.0
    hooks:
      - id: markdownlint-cli2

  - repo: local
    hooks:
      - id: typescript-check
        name: TypeScript type-check
        entry: bash -c 'cd dashboard && npm run type-check'
        language: system
        files: \.(ts|tsx)$
        pass_filenames: false

      - id: eslint
        name: ESLint
        entry: bash -c 'cd dashboard && npm run lint'
        language: system
        files: \.(ts|tsx|js|jsx)$
        pass_filenames: false

      - id: commitlint
        name: Conventional Commits
        entry: npx --no-install commitlint --edit
        language: system
        stages: [commit-msg]
```

Install: `pre-commit install && pre-commit install --hook-type commit-msg`

---

## 5. GitHub Actions — Complete Workflow Set

Eleven workflows to set up. Each is a separate file under `.github/workflows/`.

### 5.1 `ci.yml` — Main CI on every push and PR

Triggers: push to `main`, all PRs.

Jobs (run in parallel):
1. `lint-python` — ruff check
2. `format-python` — ruff format --check
3. `type-check-python` — mypy strict
4. `lint-typescript` — eslint
5. `format-typescript` — prettier --check
6. `type-check-typescript` — tsc --noEmit
7. `markdownlint` — markdownlint-cli2
8. `commitlint` — verify Conventional Commits format

### 5.2 `test.yml` — Test matrix

Triggers: push to `main`, PRs, daily cron at 4am UTC.

Jobs:
1. `test-python-unit` — pytest -m unit, matrix [3.11, 3.12]
2. `test-python-integration` — pytest -m integration (mocked LLMs)
3. `test-typescript-unit` — vitest run --coverage
4. `test-contract-conformance` — pytest -m contract
5. `test-property` — pytest -m property --hypothesis-seed=random
6. `coverage-report` — combines coverage, uploads to Codecov, comments on PR

Cron job additionally runs `test-live-llm` with real provider keys (gated to specific environments).

### 5.3 `security.yml` — Security scanning

Triggers: push, PRs, weekly schedule, dependency-update PRs.

Jobs:
1. `bandit` — Python static security analysis (covered by ruff S rules already; this is belt-and-suspenders)
2. `pip-audit` — Python dependency vulnerabilities
3. `npm-audit` — Node dependency vulnerabilities
4. `codeql` — GitHub CodeQL for Python + TypeScript
5. `gitleaks` — detect leaked secrets in commits
6. `trivy` — container image scanning (for the Docker stack)
7. `osv-scanner` — open source vulnerability scanner

### 5.4 `license-check.yml` — License compatibility

Triggers: every PR that modifies `pyproject.toml`, `package.json`, or any `requirements*.txt`.

Jobs:
1. `python-licenses` — `pip-licenses` filtered to compatible licenses (MIT, Apache-2.0, BSD, ISC, PostgreSQL, MPL-2.0). Fail on AGPL/GPL except for documented exceptions in `docs/license-exceptions.md`.
2. `node-licenses` — `license-checker` with same allow-list
3. `attribution-update` — auto-generate `THIRD_PARTY_NOTICES.md`

### 5.5 `contract-validation.yml` — Contract & schema validation

Triggers: every PR.

Jobs:
1. `validate-schemas` — JSON Schema lint on all `docs/fabric-schemas/*.json`
2. `validate-semantic-tags` — parse `docs/fabric-semantic-tags.md`, validate canonical vocabulary
3. `runtime-adapter-conformance` — verify any new/modified runtime adapter passes contract test suite
4. `manifest-validation` — verify `runtime.yaml` manifests against schema
5. `cross-artifact-consistency` — run `/speckit.analyze` programmatically; fail if specs and code drift

### 5.6 `release.yml` — Automated releases

Triggers: push to `main` (after PR merge).

Steps:
1. `semantic-release` analyzes Conventional Commits since last tag
2. Determines bump (patch/minor/major) and new version
3. Updates `CHANGELOG.md`
4. Creates git tag
5. Creates GitHub Release with auto-generated notes
6. Triggers Docker image build (if configured)
7. Publishes to PyPI (if backend is published; gated to manual approval)
8. Publishes installer scripts to GitHub Pages

Use `semantic-release` (Node.js, mature) or `python-semantic-release`.

### 5.7 `dependency-update.yml` — Renovate or Dependabot

Use **Renovate** (more configurable, supports both ecosystems in one config) over Dependabot for this project.

`renovate.json`:
```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended", ":semanticCommits"],
  "schedule": ["before 5am on Monday"],
  "labels": ["dependencies"],
  "rangeStrategy": "bump",
  "packageRules": [
    {
      "matchUpdateTypes": ["patch"],
      "automerge": true,
      "matchPackagePatterns": ["*"]
    },
    {
      "matchUpdateTypes": ["minor"],
      "automerge": false
    },
    {
      "matchUpdateTypes": ["major"],
      "automerge": false,
      "labels": ["dependencies", "major-update", "needs-review"]
    },
    {
      "matchPackageNames": ["pydantic", "fastapi", "react", "react-dom"],
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": false
    }
  ],
  "vulnerabilityAlerts": {
    "labels": ["security"],
    "automerge": true,
    "schedule": ["at any time"]
  }
}
```

### 5.8 `pr-labeler.yml` — Auto-label PRs

Uses `actions/labeler` with `.github/labeler.yml`.

### 5.9 `stale.yml` — Manage stale issues/PRs

Mark stale after 60 days inactive, close after 14 more days. Exempt issues labeled `keep-open`, `pinned`, `security`, `dreaming-proposal`.

### 5.10 `docs.yml` — Build & deploy docs

Triggers: push to `main` touching `docs/**`.

Steps:
1. Build with MkDocs Material (recommended) or similar
2. Deploy to GitHub Pages at `https://sufzen.github.io/RealizeOS-5/`
3. Validate all internal links
4. Validate external links monthly

### 5.11 `install-test.yml` — Verify the one-liner install scripts

Triggers: PRs that modify `scripts/install*` or `install.sh`.

Jobs (matrix):
- Ubuntu 22.04 + 24.04
- macOS 14 + 15 (when available)
- Windows Server 2022 (PowerShell install)
- WSL2 Ubuntu

For each: clean VM → run the install one-liner → verify `realize-os --version` succeeds → run smoke test.

### 5.12 Bonus: gh-aw workflows (after adoption)

These come from `github/gh-aw` directly:
- `workflow-health-manager.md` — monitors all other agentic workflows
- `daily-test-improver.md` — proposes new tests
- `cli-consistency-checker.md` — keeps CLI surface coherent
- `multi-device-docs-tester.md` — tests workspace UI on multiple screen sizes
- Custom: `daily-fabric-validator.md` — validates sample FABRIC fixtures stay parseable

---

## 6. Release & Publishing Automation

### 6.1 Versioning

Adopt semantic versioning strictly:
- **MAJOR** — breaking changes to one of the six contracts (Runtime Adapter, Semantic Tags, Entity Schemas, Tool Protocol, Channel Protocol, Workflow Protocol)
- **MINOR** — new features, new optional fields, new adapters
- **PATCH** — bug fixes, doc updates, dependency patches

### 6.2 Release Channels

Three channels:
1. **`latest`** — stable, recommended for production self-hosters
2. **`beta`** — pre-release with new features, opt-in
3. **`canary`** — built nightly from main; opt-in for fearless

### 6.3 What Gets Published

| Artifact | Where | Audience |
|---|---|---|
| GitHub Release | github.com/SufZen/RealizeOS-5/releases | All users |
| Source tarball | Auto-generated by GitHub | All users |
| Docker image | ghcr.io/sufzen/realizeos | Self-hosters |
| Install scripts | GitHub Pages / raw.githubusercontent.com | New installers |
| PyPI package | pypi.org/project/realize-os | Developers integrating |
| npm package | npmjs.com/package/realize-os-dashboard (if extracted) | Developers integrating |
| Documentation | sufzen.github.io/RealizeOS-5 | All users |
| Plugin registry | GitHub Pages static JSON | Extension authors |

### 6.4 PyPI Trusted Publishing

Use PyPI's Trusted Publishing (OIDC) rather than long-lived API tokens. Configure via PyPI account → publishing → add trusted publisher for GitHub Actions:
- Owner: SufZen
- Repository: RealizeOS-5
- Workflow filename: release.yml
- Environment: pypi (require manual approval)

### 6.5 Docker Image Signing

Sign images with `cosign` keyless via GitHub OIDC. Adds an attestation that the image was built from a specific commit on main in your repo.

### 6.6 Release Notes Generation

`semantic-release` auto-generates notes from Conventional Commits. Augment with:
- Highlights section (manually curated for major releases)
- Migration notes (auto-included for breaking changes)
- Contributor acknowledgements
- Dream-proposed changes section (after Phase 6) — what the Dreaming subsystem changed this release

### 6.7 Pre-release Checklist (automated)

Before any release tag is created, automated checks verify:
- [ ] All tests pass on the target commit
- [ ] CHANGELOG.md updated
- [ ] Migration guide exists (for major versions)
- [ ] Documentation updated
- [ ] Examples updated
- [ ] License attributions current
- [ ] Security scan clean
- [ ] No `dream/` quarantine branches awaiting merge

---

## 7. Updated AGENTS.md

The current AGENTS.md (if it exists) was likely written for general AI assistance. Below is the version tailored to the v5.5.0 spec-driven, multi-runtime, plug-and-play development process.

Save as `AGENTS.md` at repo root:

```markdown
# AGENTS.md — RealizeOS v5.5.0

> Guidance for AI coding agents (Claude Code CLI, Codex CLI, Gemini CLI, Hermes, Cursor, Aider, and others) working in this repository.
>
> If you are an AI agent, read this file before doing anything else.

## Project Overview

RealizeOS is a personal AI operating system. The user's knowledge (FABRIC), tasks, and preferences form the kernel. Any CLI, MCP server, API, or agent runtime plugs in as a swappable peer. The license is BSL 1.1 (self-host free; no SaaS resellers).

This codebase is currently in active development toward v5.5.0. See `docs/v5.5.0-design.md` for the canonical architecture document.

## Development Methodology

This project uses **Spec-Driven Development** via `github/spec-kit`. Specifications come first; code is generated to satisfy them. Specs live in:

- `.specify/memory/constitution.md` — project governing principles
- `.specify/specs/<NNN-feature>/` — feature specs (spec.md, plan.md, tasks.md)
- `docs/contracts/` — formal interface contracts
- `docs/fabric-schemas/` — entity schemas
- `docs/fabric-semantic-tags.md` — semantic vocabulary

**You may not implement a feature without a corresponding spec.** If a spec is missing, use `/speckit.specify` to create one first.

## Architecture (mental model)

Heart-out layering:

1. **Heart** (`realize_core/heart/`, `realize_core/synapse/`) — FABRIC, event log, SOUL, identity, Synapse indexing. Yours forever; never replaced.
2. **Spine** (`realize_core/spine/`) — Mission Engine, Smart Kanban Router.
3. **Limbs** (`realize_core/runtimes/`, `realize_core/llm/`, `realize_core/tools/`) — Runtime adapters, LLM router, MCP tool registry. All swappable.
4. **Senses** (`realize_core/channels/`) — REST, MCP, Telegram, WhatsApp, Voice, CLI.
5. **Skin** (`dashboard/`, `mobile/`) — Workspace UI, mobile companion, knowledge graph viz.
6. **Dreaming** (`realize_core/dreaming/`) — Self-evolution with Trust Policy.
7. **Distribution** (`realize_core/sync/`) — Host-satellite sync for VPS multi-user mode.

When making changes, identify which layer you're in. **Cross-layer dependencies flow inward only** (e.g., Limbs can read from Heart; Heart never imports from Limbs).

## The Six Contracts

These contracts are versioned and stable. **Breaking changes require a major version bump and a migration guide.**

1. **Runtime Adapter** (`docs/contracts/runtime-adapter.md`) — how agent runtimes plug in
2. **Semantic Tags** (`docs/fabric-semantic-tags.md`) — XML-style tags inside markdown
3. **Entity Schemas** (`docs/fabric-schemas/`) — JSON Schemas for FABRIC entity types
4. **Tool Protocol** — MCP-aligned tool descriptor format
5. **Channel Protocol** — channel adapter contract
6. **Workflow Protocol** — workflow engine integration

Before any change touching a contract, run `/speckit.analyze` to check for downstream impact.

## Coding Standards

### Python
- Python 3.11+. Use modern syntax (`X | Y` over `Union[X, Y]`, `list[T]` over `List[T]`).
- Strict typing everywhere via `mypy --strict`. No `Any` without explanation.
- `ruff` for linting and formatting. Run `ruff check` and `ruff format` before commit.
- Pydantic v2 for data models. Pydantic v1 syntax is not accepted.
- Async-first for I/O. Use `asyncio` properly; avoid `time.sleep` in async code.
- All public functions have docstrings (Google or NumPy style).

### TypeScript
- Strict mode in `tsconfig.json`, including `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`.
- ESLint with `@typescript-eslint/strict-type-checked`.
- Prettier for formatting.
- React 19 patterns: prefer server components where applicable; use the `use` hook for promises.
- Tailwind 4 utility classes; no inline styles except for dynamic values.
- shadcn/ui for accessible primitives.

### Markdown
- `markdownlint-cli2` rules in `.markdownlint-cli2.jsonc`.
- Allow inline HTML (we use it for FABRIC semantic tags).
- One sentence per line is OK; preferred for diffability.

### Conventional Commits
All commits follow Conventional Commits format:
```
<type>(<scope>): <description>
```

Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert, spec, dream.

Examples:
- `feat(runtimes): add ClaudeCodeAdapter conforming to v0.1 contract`
- `fix(synapse): handle empty embedding chunks gracefully`
- `docs(contracts): clarify approval-request semantics in runtime adapter v0.1`
- `spec(synapse): add L3 tool catalog spec for mission-context ranking`

## Testing Discipline

Every change requires tests proportional to risk:

| Layer | Coverage target | Required test types |
|---|---|---|
| Heart | 90%+ | unit + property + integration |
| Spine | 85%+ | unit + integration |
| Synapse | 85%+ | unit + property + integration |
| Runtimes | 75%+ each | unit + contract conformance |
| Dreaming | 80%+ | unit + integration + property |
| Channels | 75%+ | unit + contract |
| UI | 80%+ logic | unit + e2e |

**Contract conformance is mandatory.** Every new runtime adapter passes `tests/contract/test_runtime_adapter_v0_1.py`. Every new channel passes the channel contract tests. No exceptions.

**Property tests** (via `hypothesis`) for anything parsing user input or generating IDs. Random fuzz beats hand-crafted edge cases.

## What You Should NEVER Do

1. **Never write to FABRIC filesystem directly** if you're acting as a runtime. Use the Heart's write API which goes through validation, audit, and identity checks.
2. **Never bypass the Mission Engine** to invoke tools directly from outside it. Tools route through the engine which enforces budgets, permissions, and audit.
3. **Never store credentials in plaintext.** Use the credential vault (`keyring` library) or environment variables. Never commit `.env` files.
4. **Never add an AGPL or GPL dependency** without explicit approval in `docs/license-exceptions.md`. We are BSL 1.1; AGPL/GPL contamination is a license incident.
5. **Never auto-apply changes from the Dreaming subsystem** outside the Trust Policy system. Every dream change goes through the queue or matches an explicit AUTO category.
6. **Never break a contract without a major version bump and migration guide.** This is a hard rule.
7. **Never add telemetry without explicit opt-in.** Local-first means local-first.
8. **Never add a third-party-cloud dependency without provider tagging** (`local` / `self-hosted` / `third-party-cloud`).

## What You SHOULD Do

1. **Read the spec before coding.** Specs live in `.specify/specs/` and `docs/contracts/`. If unclear, use `/speckit.clarify`.
2. **Run the full local validation before pushing:**
   ```bash
   ruff check . && ruff format --check .
   mypy realize_core/
   cd dashboard && npm run lint && npm run type-check && cd ..
   pytest tests/unit/ -x
   markdownlint-cli2 "**/*.md"
   ```
3. **Use `/speckit.tasks` to break down work.** Don't ad-lib task decomposition; let spec-kit produce the task list, then execute.
4. **Update CHANGELOG.md unreleased section** for user-facing changes.
5. **Add an ADR** for architectural decisions in `docs/adr/NNNN-decision-title.md`.
6. **Reference the audit log philosophy.** Every meaningful action should be recordable; design for replay-ability.
7. **Test the migration path.** Any change touching FABRIC structure, the event log, or schemas requires a migration script in `migrations/` and a test that proves it works.

## Multi-Runtime Reality

If you are Claude Code CLI: you're one of several agents that may touch this codebase. Codex, Gemini CLI, and Hermes may also be invoked.

To stay coherent across runtimes:
- Always reference specs and contracts by file path; assume the next agent doesn't have your conversation context
- Leave structured comments in code that other agents can read: `# AGENT-NOTE: ...`, `# AGENT-DECISION: ...`, `# AGENT-OPEN-QUESTION: ...`
- Use `/speckit.taskstoissues` to file GitHub issues for work you can't complete; another agent or session can pick it up
- When you complete a task, link the PR back to the spec and the originating issue

## Useful Commands

```bash
# Spec-kit workflow
/speckit.constitution      # establish project principles
/speckit.specify           # define what to build
/speckit.clarify           # structured clarification of underspecified areas
/speckit.plan              # technical implementation plan
/speckit.tasks             # break into actionable tasks
/speckit.taskstoissues     # file tasks as GitHub issues
/speckit.analyze           # cross-artifact consistency check
/speckit.checklist         # generate quality checklist
/speckit.implement         # execute the plan

# Local validation
make lint
make test
make type-check
make integration-test
make e2e-test

# Spec utilities
realize-os fabric lint <venture>     # validate FABRIC content
realize-os contract validate         # validate contracts
realize-os schema validate           # validate JSON schemas
```

## License

This project is under BSL 1.1, converting to Apache 2.0 in 2030. See LICENSE for details.

You may freely contribute, fork, and self-host. You may not offer a managed service that competes with RealizeOS until the license converts.

Any AI-generated code you contribute is treated as if you wrote it: you assert it's your work to submit, free of conflicting licenses.

## When in Doubt

1. Read `docs/v5.5.0-design.md` first
2. Search existing specs in `.specify/specs/`
3. Search ADRs in `docs/adr/`
4. Open an issue with the `clarification` label

Don't guess at architecture decisions. Specs are cheap to write; reverting code is expensive.
```

---

## 8. Repository Settings Checklist

GitHub repo settings → General:
- ✅ Default branch: main
- ✅ Template repository: No (unless intentional)
- ✅ Require contributors to sign off on commits (DCO)
- ✅ Discussions: Enabled
- ✅ Issues: Enabled
- ✅ Wiki: Disabled (use docs/ and GitHub Pages instead)
- ✅ Sponsorships: Configure if appropriate
- ✅ Preserve repository: Enabled

Pull Requests:
- ✅ Allow squash merging (default)
- ✅ Allow rebase merging
- ❌ Allow merge commits (force linear history)
- ✅ Default to squash merge
- ✅ Default commit message: PR title and description
- ✅ Always suggest updating pull request branches
- ✅ Automatically delete head branches after merge

Security:
- ✅ Private vulnerability reporting: Enabled
- ✅ Dependency graph: Enabled
- ✅ Dependabot alerts: Enabled
- ✅ Dependabot security updates: Enabled
- ✅ Code scanning (CodeQL): Enabled
- ✅ Secret scanning: Enabled
- ✅ Push protection for secrets: Enabled

Code & Automation → Actions:
- ✅ Allow GitHub Actions: enabled
- ✅ Allow actions created by GitHub + verified creators + selected explicit list
- ✅ Fork pull request workflows: Require approval for first-time contributors
- ✅ Workflow permissions: Read repository contents (write only where explicitly needed)
- ✅ Allow GitHub Actions to create and approve pull requests: only for specific bots

Environments:
- ✅ `pypi` — manual approval required, used by release.yml
- ✅ `production` — manual approval required, used by deploy workflows (if any)
- ✅ `staging` — auto on develop or specific branches
- ✅ `docs-preview` — for documentation preview deployments

Pages:
- ✅ Source: Deploy from a branch → `gh-pages` (auto-generated by docs.yml)
- ✅ Custom domain: docs.realizeos.ai (if owned)

---

## 9. Secrets & Credentials Management

### 9.1 What Goes Where

| Credential | Storage | Used by |
|---|---|---|
| PyPI publishing | OIDC Trusted Publisher (no secret needed) | release.yml |
| ghcr.io publishing | `GITHUB_TOKEN` (automatic) | release.yml |
| Codecov upload | Repo secret `CODECOV_TOKEN` | test.yml |
| Test LLM API keys (sandboxed) | Org-level secrets, environment-scoped | nightly test-live-llm |
| Renovate | Repo app installation | dependency-update.yml |

### 9.2 Local Development

Developers (including you) use the `keyring` Python library for local credential storage. Never `.env` for sensitive credentials. The repo includes:
- `.env.example` — template with placeholder values, committed
- `.env` — gitignored, never committed
- `scripts/setup-credentials.py` — interactive script that walks new developers through keyring setup

### 9.3 Rotation Policy

- LLM API keys: rotate quarterly
- GitHub tokens: prefer OIDC over PATs; PATs rotate every 90 days max
- Signing keys for cosign: rotate annually
- All rotations logged in `docs/security-events.md`

---

## 10. Migration Path

### Phase A — Foundation (Week 1)

1. Adopt Conventional Commits: configure `commitlint`, add to pre-commit hooks
2. Set up `.github/CODEOWNERS`, PR template, issue templates
3. Configure main branch protection rules
4. Add `ci.yml` with the eight lint/format/type-check jobs
5. Add `test.yml` with existing tests; expand coverage targets as code grows

### Phase B — spec-kit Adoption (Week 1)

1. `uv tool install specify-cli` 
2. `specify init . --integration copilot --integration claude --integration codex`
3. Migrate `docs/v5.5.0-design.md` content into `.specify/memory/constitution.md`
4. Migrate `runtime-adapter-contract.md`, `fabric-semantic-tags.md`, `fabric-entity-schemas.md` into `.specify/specs/`
5. Run `/speckit.analyze` to verify cross-artifact consistency
6. Run `/speckit.tasks` on each spec to generate task lists
7. Run `/speckit.taskstoissues` to file tasks as GitHub issues

### Phase C — Quality Gates (Week 2)

1. Add `security.yml` with bandit, pip-audit, npm-audit, CodeQL, gitleaks
2. Add `license-check.yml` with allow-list enforcement
3. Add `contract-validation.yml` with schema and conformance tests
4. Add markdown linting via `markdownlint-cli2`
5. Set up Codecov integration

### Phase D — Release Automation (Week 2)

1. Adopt `semantic-release` (Node) or `python-semantic-release`
2. Configure `release.yml` with GitHub Release, Docker image, PyPI (manual approval)
3. Set up PyPI Trusted Publishing via OIDC
4. Configure docker image signing via cosign
5. Set up GitHub Pages for docs

### Phase E — Agentic Workflows (Week 3)

1. `gh extension install github/gh-aw`
2. Adopt Workflow Health Manager, Daily Test Improver, CLI Consistency Checker
3. Author one custom gh-aw workflow: `daily-fabric-validator.md` that validates sample FABRIC fixtures stay parseable
4. Configure agentic workflows to respect the same branch protection rules (PRs only)

### Phase F — Stable Cadence (Week 4 and ongoing)

1. Set up Renovate (or Dependabot) for dependency updates
2. Configure stale issue/PR management
3. Set up nightly e2e tests
4. Run first formal `/speckit.implement` task end-to-end to verify the workflow works
5. Document the workflow in `docs/development-workflow.md` for future collaborators

---

## Appendix A — Recommended `.gitignore` additions

```
# RealizeOS-specific
ventures/
!ventures/_templates/
!ventures/_examples/
*.local.yaml
*.local.json
.env
.env.local
.env.*.local

# spec-kit
.specify/cache/
.specify/.lock

# Credentials
*.key
*.pem
credentials.json
service-account*.json

# Build artifacts
dist/
build/
*.egg-info/
.coverage
htmlcov/
.pytest_cache/
.mypy_cache/
.ruff_cache/
node_modules/
.vite/
.next/

# IDE
.vscode/settings.json
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

## Appendix B — Recommended `SECURITY.md`

Create `SECURITY.md`:

```markdown
# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 5.5.x   | :white_check_mark: |
| 5.2.x   | :white_check_mark: (until v5.5.0 release + 90 days) |
| < 5.2   | :x:                |

## Reporting a Vulnerability

Please do NOT file public GitHub issues for security vulnerabilities.

Email: security@suf.zen
PGP key: (publish your key fingerprint)

We will acknowledge within 48 hours and provide a status update within 7 days.

Coordinated disclosure: we follow a 90-day disclosure timeline.
```

---

## Closing Notes

These recommendations form a target state. To execute them practically:

1. **Compare against current state.** Share the contents of your `.github/`, `pyproject.toml`, `package.json`, and current `AGENTS.md` and I'll produce a focused diff.
2. **Phase the rollout.** All eleven workflows in week one is overkill. Phase A through F above is realistic for solo capacity.
3. **Spec-kit before everything else.** Of all the changes here, adopting spec-kit gives the highest leverage. Even if you do nothing else from this document for a month, do that.

If you want, the next concrete deliverable I can produce is the actual content for each of the eleven `.github/workflows/*.yml` files — fully fleshed YAML you can paste in directly.

