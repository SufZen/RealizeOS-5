# Story: STORY-10 — Release prep + tag v5.1.0

## Epic: Workstream D — Production-ready release
## Priority: P0
## Status: todo

## Description

Final pre-release housekeeping: bump VERSION, re-run the full audit playbook, write release notes, update the sprint retrospective, and tag `v5.1.0` to trigger the release pipeline. After tag, run smoke tests against the published artifacts.

## Acceptance Criteria

- [ ] [VERSION](../../VERSION) bumped to `5.1.0`.
- [ ] [pyproject.toml](../../pyproject.toml) `version = "5.1.0"` (release workflow rewrites from tag, but file should match for local installs).
- [ ] [realize-os-cli/package.json](../../realize-os-cli/package.json) `"version": "5.1.0"`.
- [ ] Full audit playbook ([docs/audit-playbook.md](../../docs/audit-playbook.md)) re-run; [AUDIT-REPORT.md](../../AUDIT-REPORT.md) regenerated. Target: ≥ 1,800 tests passing including new MCP/CLI suites.
- [ ] Release notes drafted under `docs/release-notes/5.1.0.md` (or appended to `CHANGELOG.md` from Story 9). Sections: Highlights, MCP server, Operator CLI, CI hardening, Migration, Breaking changes (none expected), Acknowledgements.
- [ ] [`_bmad/sprint-status.yaml`](../sprint-status.yaml) — every story `status: done`.
- [ ] [`_bmad/retro-5.1.0.md`](../retro-5.1.0.md) — sprint retrospective per MTH-38: went well, improve, action items.
- [ ] CI green on `main` (verified one last time before tag).
- [ ] Tag pushed: `git tag v5.1.0 && git push --tags`.
- [ ] Release pipeline ([release.yml](../../.github/workflows/release.yml)) completes with all 5 jobs ✓: `ci`, `docker-release`, `npm-publish`, `pypi-publish`, `github-release`.
- [ ] GitHub Release page shows `RealizeOS-Lite-5.1.0.zip` + `.sha256` attached, with the drafted release notes as body.
- [ ] Smoke tests pass (post-publish):
  - `docker pull ghcr.io/sufzen/realizeos-5:5.1.0 && docker run --rm ghcr.io/sufzen/realizeos-5:5.1.0 realize-os --version` → `5.1.0`
  - `npx @realize-os/cli@5.1.0 --version` → `5.1.0`
  - `pip install realize-os==5.1.0 && realize-os --version` → `5.1.0`

## Technical Notes

- Don't tag from a branch other than `main`.
- Use an annotated tag (`git tag -a v5.1.0 -m "..."`) so the release page picks up a body.
- If `npm-publish` or `pypi-publish` fails, the tag can stay — re-run the failing job from the Actions UI. Only delete the tag if Docker fails *and* you need a different SHA.
- Rollback procedure documented in [`PRD.md`](../PRD.md) and the plan file.

## Dependencies

- All Stories 1–9 merged.

## Files Affected

- `VERSION`, `pyproject.toml`, `realize-os-cli/package.json` — version bump.
- `AUDIT-REPORT.md` — regenerated.
- `_bmad/sprint-status.yaml`, `_bmad/retro-5.1.0.md` — closeout.
- (Optional) `docs/release-notes/5.1.0.md` — new.
- Git: tag `v5.1.0`.
