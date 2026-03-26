# Project Learnings

This file accumulates knowledge from every AutoBuild intent executed on this project. The orchestrator (`.autobuild/program.md` after installation) reads this file before every new intent to avoid repeating mistakes and to leverage proven patterns.

---

<!-- Append entries below this line. Newest first. -->

## Intent 1.1 — Security Audit for Public Repository (2026-03-26)

### Findings

- **No actual API keys or passwords were hardcoded** in the Python codebase. The team consistently used `os.getenv()` for all sensitive values. This is excellent discipline.
- **The main risk was `developer_resources/AUTOMATION-SETUP.md`**, which contained real Stripe payment URLs, a VPS IP address, n8n webhook endpoints, Google Drive file IDs, Google Sheets IDs, and a Stripe webhook endpoint ID. All were sanitized to `<PLACEHOLDER>` values.
- **JWT fallback secret** (`realize-os-dev-secret-NOT-FOR-PRODUCTION`) in `jwt_auth.py` is acceptable for dev but is clearly labeled. The scanner check already warns about weak secrets.
- **`.gitignore` was missing** patterns for `*.key`, `*.pem`, `*.cert`, `*.p12`, `*.pfx`, and other credential file types.
- **No CI secret scanning** existed. Added `gitleaks` to the security job.

### Patterns Discovered

1. **AUTOMATION-SETUP.md is the highest-risk file** — it documents real production infrastructure. When making a repo public, docs that reference real payment links, server IPs, and webhook URLs are more dangerous than code.
2. **The existing security scanner** (`realize_core/security/scanner.py`) already checks for `sk-ant-`, `AIza`, `sk-proj-` patterns in config files. This is a good baseline for runtime checks.
3. **All 1271 tests pass** after security changes — confirming the changes were non-breaking.

### What Worked

- Grep-based scanning across all file types caught everything
- The codebase's use of `os.getenv()` with empty string defaults is the right pattern
- The existing `.gitignore` was already good for Python/Node — just needed credential file extensions

### What to Watch

- `realize_lite/setup-guide.md` and `developer_resources/setup-guide.md` contain the support email `realizeos@realization.co.il` — this is intentional public contact info, not a secret
- When adding new tools or integrations, always use `os.getenv()` with documented entries in `.env.example`
