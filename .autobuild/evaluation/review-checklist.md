# Review Checklist

> Used during Phase 5 (EVALUATE) for structured human review.

## Code Quality

- [ ] **Correctness** — Does the code do what the intent specified?
- [ ] **Completeness** — Are all acceptance criteria met?
- [ ] **Edge cases** — Are boundary conditions handled?
- [ ] **Error handling** — Are errors caught and handled meaningfully?
- [ ] **Readability** — Can another developer understand this in 5 minutes?
- [ ] **Maintainability** — Is the code easy to modify later?
- [ ] **No dead code** — No unused variables, functions, or imports?

## Consistency

- [ ] **Naming** — Follows project conventions from project-context.md?
- [ ] **Patterns** — Matches existing patterns in the codebase?
- [ ] **Style** — Formatted according to project standards?
- [ ] **Documentation** — Non-obvious logic has comments/docstrings?

## Security

- [ ] **No secrets** — No hardcoded API keys, passwords, tokens?
- [ ] **Input validation** — All user inputs validated?
- [ ] **Auth/Authz** — New endpoints properly protected?
- [ ] **Dependencies** — No known vulnerabilities in new/updated deps?

## Testing

- [ ] **Coverage** — New/changed code has tests?
- [ ] **Meaningful** — Tests verify behavior, not just execution?
- [ ] **Isolation** — Tests don't depend on external services or order?
- [ ] **Green** — All tests passing?

## Architecture

- [ ] **Boundaries** — Respects module/layer boundaries?
- [ ] **No anti-patterns** — Avoids patterns listed in project-context.md?
- [ ] **Consistency** — Uses the same abstractions as similar code?
- [ ] **No scope creep** — Only changes what the intent specified?

## Performance

- [ ] **No N+1** — No unintentional N+1 query patterns?
- [ ] **No blocking** — No blocking calls in async contexts?
- [ ] **Efficient** — No obviously wasteful algorithms or data structures?

## Overall Assessment

- **Quality Score:** ___/100
- **Verdict:** APPROVE / REQUEST CHANGES / NEEDS DISCUSSION
- **Summary:** <!-- brief human assessment -->
