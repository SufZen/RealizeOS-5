# Security Checklist

> Detailed, objective security delivery gate for evaluating AutoBuild output. Used by AI Security Reviewers to deterministicly grade artifact safety. 1 Failed Check = Automatic Reject.

## Secrets & Credentials Protection

- [ ] **No Hardcoded Secrets**: 0 string literals exist matching high-entropy regexes (e.g., `AKIA[0-9A-Z]{16}`, `ghp_[a-zA-Z0-9]{36}`, `ey...`).
- [ ] **Version Control Hygiene**: `.env`, `.pem`, and `*.key` files explicitly excluded via `.gitignore`.
- [ ] **Environment Delegation**: 100% of external service authentications rely on typed environment variables (e.g., `process.env.DB_PASSWORD`) or vault fetching.

## Input Handling & Defense-in-Depth

- [ ] **Prompt Injection Defense**: All user-supplied text fed to LLMs undergoes delimiter sanitization (e.g., stripping `<|im_start|>`) AND enforces a strict maximum token/character truncation limit.
- [ ] **Unicode Safe-Parsing**: User inputs are explicitly passed through Unicode normalizers (e.g., `.normalize('NFC')`) before reaching security gates or LLM contexts.
- [ ] **Type & Range Validation**: 100% of API endpoints implement strict schema parsers (e.g., Zod) dropping all undocumented JSON fields.
- [ ] **Context Segregation**: LLM system instructions are strictly segregated into independent roles/arrays and NEVER concatenated directly with unescaped user string variables.
- [ ] **SQL/NoSQL Injection Prevention**: 0 dynamically concatenated query strings. 100% of queries use parameterized prepared statements or validated ORM abstractions.
- [ ] **XSS & Path Traversal Guards**: HTML outputs are processed through explicit tag sanitizers; file paths rely exclusively on `path.join` standard libraries preventing `../` escapes.

## Authentication & Authorization Gates

- [ ] **Algorithm Confusion Prevention**: JWT verification functions explicitly hardcode allowed `algorithms` (e.g., `['RS256']`), preventing `none` or HMAC semantic confusion bypassed by attackers.
- [ ] **Endpoint Coverage**: 100% of newly added endpoints strictly implement the system's global authentication middleware barrier unless explicitly annotated as a public route.
- [ ] **RBAC Verification**: Privileged actions (e.g., DELETE, UPDATE) implement explicit user role assertions against the target resource ID before actioning.
- [ ] **Timeouts & Revocation**: Tokens have a hardcoded `exp` claim < 24 hours. Rate-limiting middleware is present on all authentication endpoints.

## Data Protection

- [ ] **PII Redaction**: Application logger pipes sensitive fields (`password`, `ssn`, `credit_card`) through explicit masking algorithms (`***`).
- [ ] **Encryption In Transit**: Cookies enforce `Secure`, `HttpOnly`, and `SameSite=Strict` attributes for 100% of user sessions.
- [ ] **Storage Security**: Database passwords or tokens are stored with PBKDF2, Argon2, or bcrypt saltings; 0 unhashed passwords persisted.

## Dependency Integrity

- [ ] **Vulnerability Scans**: `npm audit`, `pip check`, or equivalent package manifest scanners return 0 CRITICAL or HIGH vulnerabilities.
- [ ] **Pinning**: 100% of added dependencies are pinned to exact versions in the package manifest, averting malicious minor-version supply-chain poisoning.

## Overall Security Assessment

- **Severity Check:** Any single unchecked box sets Severity to `CRITICAL`.
- **Verdict Flagging:** If Severity == `CRITICAL` or Score < 80, VERDICT = `REJECTED` strictly.
- **Findings:** <!-- List explicit failed objective binary checks -->
- **Verdict:** PASS / REJECTED
