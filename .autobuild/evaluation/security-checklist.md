# Security Checklist

> Detailed security review for evaluating AutoBuild output. Used by both the Security Reviewer agent and human reviewers.

## Secrets & Credentials

- [ ] No hardcoded API keys, tokens, or passwords in source code
- [ ] No `.env` files committed to version control
- [ ] No private keys or certificates in the repository
- [ ] Secrets accessed via environment variables or secret management

## Input Handling

- [ ] All user inputs are validated (type, length, format, range)
- [ ] SQL queries use parameterized statements
- [ ] File paths are sanitized (no path traversal)
- [ ] HTML output is escaped (no XSS)
- [ ] URL redirects are validated against allowlist
- [ ] JSON/XML parsing has size limits configured

## Authentication & Authorization

- [ ] New endpoints require authentication
- [ ] Sensitive operations check authorization (roles/permissions)
- [ ] Tokens are scoped to minimum necessary permissions
- [ ] Session/token timeouts are configured
- [ ] Failed auth attempts are logged

## Data Protection

- [ ] Sensitive fields are masked in logs
- [ ] Personal data is encrypted at rest
- [ ] Data in transit uses TLS
- [ ] Database credentials are not world-readable
- [ ] Backup data has the same protections as live data

## Dependencies

- [ ] No dependencies with known CRITICAL/HIGH CVEs
- [ ] Dependencies are pinned to specific versions
- [ ] No abandoned/unmaintained dependencies added

## Overall Security Assessment

- **Severity:** CLEAN / WARNINGS / CRITICAL
- **Findings:** <!-- List specific issues -->
- **Verdict:** PASS / NEEDS REMEDIATION
