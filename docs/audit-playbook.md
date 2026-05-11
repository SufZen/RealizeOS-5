# RealizeOS Audit Playbook

This guide turns the RealizeOS audit plan into a repeatable operating workflow.

## Run the Audit

```bash
realize-os audit
```

For a faster pass that skips the dashboard build probe:

```bash
realize-os audit --quick
```

For machine-readable output:

```bash
realize-os audit --format json
```

## Audit Order

1. Deployment, Configuration, and Startup Foundation
2. Security, Governance, and Trust Controls
3. Data, Knowledge, Memory, and Storage
4. Core Orchestration and Workflow Runtime
5. LLM Routing and Agent Intelligence
6. Tools, Integrations, Extensions, and Plugins
7. API and Channel Surface
8. Operator Experience: Dashboard and CLI

## Session Template

Use the same output structure for every building block:

1. Purpose in plain language
2. Dependency map
3. Current failures and likely breakpoints
4. Hidden bugs to probe
5. Top fixes ranked by risk and effort
6. Regression checks to add
7. Done criteria

## Public Contracts

Treat these interfaces as first-class contracts during audits:

- REST API routes and response/error shapes
- SSE activity stream behavior
- MCP server tool surface (24 tools, 4 families)
- CLI commands and output formatting
- FABRIC directory structure under `systems/`
- Extension and plugin entry points
- Dashboard-to-API client expectations

## Operator Guidance

- Start with foundation issues first. A noisy startup environment invalidates later findings.
- Use `realize-os status` before deeper debugging to confirm whether the workspace is partially initialized.
- If the dashboard lints but does not build, treat that as a release blocker for operator-facing work.
- Re-run `realize-os audit` after each block closes so the next session starts from current repo truth.
