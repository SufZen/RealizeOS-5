# Branch Protection Rules — Checklist for GitHub UI

> Apply these settings in: GitHub → Settings → Branches → Branch protection rules → `main`

## Required Settings

- [ ] **Require a pull request before merging**
  - [ ] Require approvals: `1` (set to `0` while solo with self-review discipline)
  - [ ] Dismiss stale pull request approvals when new commits are pushed
  - [ ] Require review from Code Owners

- [ ] **Require status checks to pass before merging**
  - [ ] `Lint & Format (Python)` (ruff check + format)
  - [ ] `Type Check (mypy)` (mypy on realize_core/storage/ + llm/)
  - [ ] `Test (pytest)` (pytest with coverage)
  - [ ] `Security Scan` (safety + bandit + gitleaks)
  - [ ] `Dashboard Check` (lint + format:check + type-check + test + build)
  - [ ] `CLI Build Check` (lint + build + test)
  - [ ] `Markdown Lint` (markdownlint-cli2)
  - [ ] Require branches to be up to date before merging

- [ ] **Require conversation resolution before merging**

- [ ] **Require linear history** (squash or rebase only; no merge commits)

- [ ] **Restrict who can push to matching branches**: `@SufZen`

## Recommended (enable when ready)

- [ ] Require signed commits (GPG signing)
- [ ] Do not allow bypassing the above settings

## Explicitly Disabled

- ❌ Force pushes: disabled
- ❌ Deletions: disabled

## Notes

- Status check names above match the Phase C `ci.yml` job names
- Phase C added: `type-check-python`, `markdownlint`, `format:check` and `type-check` in dashboard
- When Phase D adds semantic-release, it will need push access to main (configure as app)
