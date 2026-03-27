# RealizeOS Dashboard

React 19 + Vite 8 + TypeScript dashboard for operating RealizeOS.

## Purpose

The dashboard is the operator surface for:

- venture management
- chat and activity monitoring
- approvals and security posture
- routing, workflows, tools, and settings

## Commands

The frontend lockfile is `pnpm-lock.yaml`, so `pnpm` is the primary package manager.

```bash
pnpm install
pnpm lint
pnpm build
pnpm dev
```

If `pnpm` is not installed locally, use Corepack:

```bash
corepack pnpm install
corepack pnpm lint
corepack pnpm build
corepack pnpm dev
```

## Audit Notes

When auditing the dashboard, verify all of the following:

- lint passes
- production build succeeds
- loading, empty, and error states render clearly
- API failures do not leave blank screens
- navigation still works after query refreshes or SSE reconnects

The repo-level audit command also checks the dashboard build path:

```bash
python cli.py audit
```
