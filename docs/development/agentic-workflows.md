# Agentic Workflows (gh-aw) Setup

> Phase E of the v5.5.0 infrastructure rollout

## What Are Agentic Workflows?

[GitHub Agentic Workflows](https://github.com/github/gh-aw) lets you define CI/CD automation
using natural language in Markdown files. An AI agent reads your instructions and executes them
within a sandboxed GitHub Actions environment.

## Setup

### 1. Install gh-aw

```bash
gh extension install github/gh-aw
```

### 2. Initialize (one-time)

```bash
gh aw init
```

### 3. Compile workflows

After creating or editing any `.md` workflow file, compile to generate the `.lock.yml`:

```bash
gh aw compile
```

This creates corresponding `.lock.yml` files that are the actual GitHub Actions workflows.
**Both the `.md` source and `.lock.yml` compiled output must be committed.**

### 4. Run manually (optional)

```bash
gh aw run .github/workflows/workflow-health.md
```

## Installed Workflows

| Workflow | Schedule | Purpose |
|---|---|---|
| `workflow-health.md` | Weekly | CI health report — failures, slow runs, deprecated actions |
| `daily-test-improver.md` | Daily | Test coverage gaps, anti-patterns, quality issues |
| `cli-consistency.md` | Weekly | Python + Node CLI consistency and completeness audit |

## Deferred Workflows

| Workflow | Deferred Until | Purpose |
|---|---|---|
| `daily-fabric-validator.md` | Phase 1 (FABRIC fixtures exist) | Validate FABRIC entity schemas, references, and Synapse index consistency |

## Notes

- All workflows use `safe-outputs` to control write permissions (e.g., issue creation)
- Workflows are read-only by default — they analyze and report, never modify code
- The `.lock.yml` files are auto-generated; edit the `.md` source files only
- Run `gh aw audit <run-id>` to inspect results after execution
