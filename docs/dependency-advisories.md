# Dependency advisories

Status of known security advisories against RealizeOS dependencies, and why any that remain were not fixed.

**As of 2026-10-13**, branch `release/5.30` (STORY-24). Scanners: `pnpm audit` (dashboard), `npm audit` (npm CLI, root release tooling), `pip-audit` via `uvx` on Python 3.12 (backend), plus an [OSV](https://osv.dev) query for each declared minimum Python version. Advisory databases change daily, so re-run the commands below before relying on these numbers.

## Scope first

What a user actually receives matters most:

| Artifact | What ships | Audited as |
|---|---|---|
| Docker image | Python packages resolved from `requirements.txt` / `pyproject.toml`, plus the built dashboard in `static/` | `pip-audit -r requirements.txt`; dashboard runtime dependencies |
| PyPI wheel | Python packages from `pyproject.toml` (the wheel doesn't include the dashboard) | `pip-audit -r requirements.txt` |
| Built dashboard bundle (`static/`) | Browser code from `dashboard/` runtime dependencies (React, React Router, TanStack Query, etc.) | `pnpm audit --prod` |
| npm package `@realize-os/cli` | `dependencies` in `realize-os-cli/package.json` | `npm audit --omit=dev` |
| Build, test and release tooling | Vite, Vitest, ESLint, TypeScript, semantic-release, commitlint, pytest, ruff | full audits; never shipped |

Note: `pnpm audit --prod` also counts Vite, PostCSS and their helpers, because the `@tailwindcss/vite` build plugin is listed under `dependencies`. They run at build time only and are not in the bundle.

## Before and after

| Ecosystem | Scope | Before | After |
|---|---|---|---|
| Dashboard (`pnpm-lock.yaml`) | all | 54 (32 high, 20 moderate, 2 low) | **0** |
| Dashboard (`pnpm-lock.yaml`) | `--prod` | 27 (16 high, 10 moderate, 1 low); in the bundle: `react-router` (12 advisories) | **0** |
| Dashboard (`package-lock.json`, npm fallback only) | all | 12 (9 high, 2 moderate, 1 low) | **0** |
| npm CLI (`realize-os-cli/`) | all | 10 (2 critical, 5 high, 3 moderate) | **0** |
| npm CLI (`realize-os-cli/`) | `--omit=dev` (published) | 1 high (`brace-expansion` via `ejs`) | **0** |
| Root release tooling (`package-lock.json`) | all (dev only) | 24 (2 critical, 19 high, 3 moderate) | **15** (13 high, 2 moderate) |
| Python `requirements.txt` (resolved, 113 packages) | runtime | 0 | 0 |
| Python `requirements-dev.txt` (resolved) | dev | 0 | 0 |
| Python declared minimum versions (OSV, at each floor) | runtime | 30: `litellm>=1.50.0` (26), `mcp>=1.10.0` (3), `python-dotenv>=1.0.0` (1) | **0** |

## What changed

- **Dashboard:** `react-router-dom` 7.13.1 → 7.18.4 (shipped), `vite` 8.0.0 → 8.3.4, `vitest` 4.1.5 → 4.1.11, plus lockfile refreshes of transitive build/lint packages (postcss, nanoid, source-map-js, picomatch, brace-expansion, js-yaml, flatted, browserslist, baseline-browser-mapping, `@humanfs/node`, `@babel/core`). All minor or patch bumps within the existing ranges. The unused npm lockfile was resynced to the same manifest.
- **npm CLI:** lockfile refresh fixed the only published-scope advisory (`brace-expansion` under `ejs`). **Major bump (dev only):** `vitest` ^2 → ^4.1.11, the line the dashboard already uses; it cleared the critical `tinypool` and Vitest UI advisories and the Vite 5 / esbuild 0.21 dev-server chain. `tsx` updated within ^4 so esbuild resolves to 0.28.2.
- **Root tooling:** `npm audit fix` without `--force`: handlebars (critical), undici 7, fast-uri, js-yaml, sigstore, and the npm package bundled by `@semantic-release/npm` (11.15 → 11.21: tar, pacote, sigstore).
- **Python:** a fresh install (Docker, `pip install realize-os` into a clean environment) resolves to current releases and had no known advisories. But requirements are minimum versions (`>=`), and pip keeps an already-installed version that satisfies them, so an existing environment could hold a version the floors still allowed. Raised three floors to the first release without published advisories, in both `requirements.txt` and `pyproject.toml`: `litellm` 1.50.0 → 1.88.6 (26 advisories, most in the LiteLLM proxy server, which RealizeOS does not run; we use it as a library), `mcp` 1.10.0 → 1.28.1 (DNS rebinding and transport Host/Origin checks; the `<2` cap stays), `python-dotenv` 1.0.0 → 1.2.2 (symlink following in `set_key`). The full test suite passes on Python 3.12 with exactly these floor versions installed.

No packages were added in any ecosystem.

## What remains

All remaining entries are in the root release tooling (`package.json` at the repository root: semantic-release and commitlint). It runs in GitHub Actions and on developer machines, and never ships in any artifact.

| Advisory | Package | Scope | Why not fixed |
|---|---|---|---|
| GHSA-vfj7-8cjw-p6xm (high) | `braces` 3.0.3, via `micromatch` 4.0.8 | dev: semantic-release, `@semantic-release/commit-analyzer`, `@semantic-release/git` | No fixed version released (3.0.3 is the latest). npm suggests a downgrade to `@semantic-release/exec` 3.3.8 / `@semantic-release/changelog` 5.0.1, which would be a breaking regression rather than a fix. Patterns come from our own `.releaserc.json`, not untrusted input. |
| GHSA-ch52-4w7c-c8xp (high) | `http-cache-semantics` 4.2.0 | dev: bundled inside `npm` 11.21.0 | Bundled dependencies cannot be overridden. 11.21.0 is the newest npm 11, and `@semantic-release/npm` 13.2.0 (latest) requires npm ^11.6.2, so this clears when an npm 11 release bundles fixed versions or the plugin accepts npm 12. Not reachable: our `.releaserc.json` does not load `@semantic-release/npm` (verified with a dry run), so this code never runs. |
| GHSA-rfgv-xxqx-mfg5 (high), GHSA-3wwx-pv8p-q78v (moderate), GHSA-r53p-7pc4-xj5r (low) | `undici` 6.28.0 | dev: bundled inside `npm` 11.21.0 | Same as above. |
| GHSA-qhr7-859c-m2p7, GHSA-6j4f-fj2g-mc7p (high), GHSA-q2hr-2g5m-vwhr (moderate) | `brace-expansion` 5.0.9 | dev: bundled inside `npm` 11.21.0 | Same as above. |
| GHSA-rpw4-54j3-4h4q, GHSA-2vr4-cq9g-pvrc, GHSA-j6r3-76f7-8jcv, GHSA-h3mg-xc3c-68pw (moderate) | `ip-address` 10.5.0 | dev: bundled inside `npm` 11.21.0 | Same as above. |
| GHSA-rj75-hqrm-r3gf (moderate) | `postcss-selector-parser` 7.1.4 | dev: bundled inside `npm` 11.21.0 | Same as above. |

`npm audit` reports 15 entries for these 6 root causes: it also flags `semantic-release`, `micromatch` and the seven `@semantic-release/*` plugins because they depend on the packages above.

Not covered yet: CI does not fail on new advisories. It runs `safety check` (non-blocking) for Python and no audit for the JavaScript lockfiles, so this page is a point-in-time record, not a guarantee.

## Re-running the checks

When you refresh `dashboard/pnpm-lock.yaml`, keep every entry at least a day old. The Docker build installs with the latest pnpm, which rejects lockfile entries published less than a day before the build (`ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION`). Resolve with a minimum age, for example `pnpm update --depth Infinity <pkg> --config.minimum-release-age=4320` (3 days, in minutes).

From the repository root:

```bash
# Dashboard
(cd dashboard && pnpm audit && pnpm audit --prod)
# npm CLI
(cd realize-os-cli && npm audit && npm audit --omit=dev)
# Root release tooling
npm audit
# Python (pip-audit runs in an isolated environment and is not a project dependency)
uvx --python 3.12 pip-audit -r requirements.txt
uvx --python 3.12 pip-audit -r requirements-dev.txt
```
