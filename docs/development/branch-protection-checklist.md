# Branch Protection Rules — Checklist for GitHub UI

> Apply these settings in: GitHub → Settings → Branches → Branch protection rules → `main`

## Required Settings

- [ ] **Require a pull request before merging**
  - [ ] Require approvals: `1` (set to `0` while solo with self-review discipline)
  - [ ] Dismiss stale pull request approvals when new commits are pushed
  - [ ] Require review from Code Owners

- [ ] **Require status checks to pass before merging**
  - [ ] `lint` (ruff check + format)
  - [ ] `test` (pytest)
  - [ ] `security` (safety + bandit + gitleaks)
  - [ ] `dashboard-check` (pnpm lint + test + build)
  - [ ] `cli-check` (npm lint + build + test)
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

- Status check names above match the current `ci.yml` job names
- When Phase C adds mypy, prettier, and tsc jobs, add them as required checks
- When Phase D adds semantic-release, it will need push access to main (configure as app)
