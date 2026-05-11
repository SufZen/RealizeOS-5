# Story: STORY-01 — CI green on `main`

## Epic: Workstream A — Unblock CI
## Priority: P0
## Status: done (2026-05-11, commit 610434d, run 25689952971)

## Description

Every push to `main` since 2026-05-10 12:33 UTC fails CI at `Docker Build (verify) → Validate Docker Compose files`, because `docker compose config` requires the `.env` referenced via `env_file:` to exist and CI legitimately doesn't have one. This blocks the release pipeline (which gates every job on `needs: ci`). Fix CI so all 6 jobs go green; harden gitleaks and `safety check` from advisory to blocking; optionally bump deprecated GitHub Actions to silence Node 20 warnings.

## Acceptance Criteria

- [ ] CI job `Docker Build (verify)` passes on a fresh push to `main`.
- [ ] Patch creates a CI-only `.env` from `.env.example` before `compose config`.
- [ ] `.gitleaks.toml` exists at repo root with allowlist for the 3 known false positives:
  - `docs/getting-started.md`
  - `docs/user-guide.html`
  - `tests/security/test_phase1_adversarial.py`
- [ ] `gitleaks` step's `continue-on-error: true` removed (real leaks now block CI).
- [ ] `safety check -r requirements.txt`'s trailing `|| true` removed (real vulns now block CI). If the local run discovers vulns, pin/upgrade them in the same PR.
- [ ] *(Optional, can defer):* `actions/checkout@v4`→`@v5`, `actions/setup-python@v5`→`@v6`, `actions/setup-node@v4`→`@v5`, `actions/upload-artifact@v4`→`@v5`, `pnpm/action-setup@v4`→`@v5`, `docker/setup-buildx-action@v3`→`@v4`. Silence Node 20 deprecation warnings.
- [ ] Run shows 6/6 jobs ✓ in `gh run list --limit 1`.
- [ ] No production code changed in this PR (CI-only / config-only).

## Technical Notes

- File: [.github/workflows/ci.yml](../../.github/workflows/ci.yml). Three edit sites:
  - Line ~159 — docker-build "Validate Docker Compose files": prepend `cp .env.example .env`.
  - Line ~119 — security "Check dependencies (safety)": drop `|| true`.
  - Line ~140 — security "Scan for hardcoded secrets (gitleaks)": drop `continue-on-error: true`.
- New file: [.gitleaks.toml](../../.gitleaks.toml).
- Local pre-flight (must all pass before push):
  ```bash
  ruff check realize_core/ realize_api/ tests/ cli.py
  ruff format --check realize_core/ realize_api/ tests/ cli.py
  cp .env.example .env
  docker compose -f docker-compose.yml config > /dev/null
  docker compose -f docker-compose.prod.yml config > /dev/null
  gitleaks detect --redact -v --config .gitleaks.toml
  safety check -r requirements.txt
  ```

## Dependencies

- None (Phase 0 BMAD scaffold lands first as a prereq for the development cadence, but is not a code dependency).

## Files Affected

- `.github/workflows/ci.yml` — three small edits as described above.
- `.gitleaks.toml` — new file at repo root with allowlist entries.
- (No code, doc, or test changes outside CI configuration.)
