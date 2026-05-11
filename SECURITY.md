# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 5.1.x   | ✅ Active |
| 5.0.x   | ⚠️ Critical fixes only |
| < 5.0   | ❌ End of life |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Instead, report vulnerabilities by emailing:

📧 **security@realization.co.il**

Include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Any suggested fix (optional)

### What to expect

- **Acknowledgment** within 48 hours
- **Assessment** within 7 days
- **Fix timeline** communicated once severity is assessed
- **Credit** in the release notes (unless you prefer to stay anonymous)

## Security Architecture

RealizeOS employs a 5-layer security middleware stack:

1. **Security Headers** — HSTS, CSP, X-Frame-Options
2. **Audit Logging** — JSONL persistent logs with SSE streaming
3. **Rate Limiting** — Configurable per-endpoint rate limits
4. **Injection Guard** — Pattern + heuristic + Unicode normalization prompt injection scanner
5. **JWT Authentication** — HMAC-SHA256 tokens with refresh flow and RBAC (6 roles)

Additional protections:

- Secret redaction in error responses and logs
- SSRF protection on web tools
- Tool gating with per-agent allowlists/denylists
- Human-in-the-loop approval gates for consequential actions
- Built-in security scanner (`realize-os doctor`)

## Dependencies

Dependencies are pinned in `requirements.txt` and scanned for known vulnerabilities in CI using [Safety](https://pypi.org/project/safety/) and [Bandit](https://bandit.readthedocs.io/). Secrets are scanned with [Gitleaks](https://github.com/gitleaks/gitleaks).
