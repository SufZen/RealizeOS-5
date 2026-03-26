# Fix Intent

> Use this template when fixing a bug or resolving an issue.

## Goal

<!-- What is broken? Be specific. e.g., "API returns 500 error when user has no profile photo" -->

## Context

<!-- How to reproduce? When did it start? Any relevant error logs? -->

### Reproduction Steps

1. <!-- Step 1 -->
2. <!-- Step 2 -->
3. <!-- Observe: [what happens] instead of [what should happen] -->

### Error Details

<!-- Paste error messages, stack traces, logs here -->

## Scope

### IN

- <!-- Fix the bug -->
- <!-- Add regression test for this bug -->

### OUT

- <!-- Don't refactor surrounding code (use refactor intent) -->
- <!-- Don't add features while fixing -->

## Acceptance Criteria

- [ ] <!-- Bug no longer reproducible with the steps above -->
- [ ] <!-- Regression test added that catches this specific bug -->
- [ ] <!-- No other tests broken by the fix -->
- [ ] <!-- Root cause documented in the commit message -->

## Constraints

- <!-- Minimal change — fix the bug, nothing more -->
- <!-- Must not introduce new dependencies for a bug fix -->

## Build Mode

**Mode:** `standard`
