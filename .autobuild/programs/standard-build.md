# Standard Build Program

> Single-pass build with quality gates. Use for simple, well-understood tasks.

## When to Use

- Complexity is SIMPLE or MEDIUM
- There is one clear, obvious implementation approach
- The acceptance criteria are specific and verifiable

## Workflow

### Step 0: Setup

1. Create and checkout the working branch: `git checkout -b autobuild/[intent-name]`

### Step 1: Implement

Invoke the **Builder Agent** (`agents/builder.md`):
- Implement the plan step by step
- Follow `project-context.md` conventions
- Commit after each logical step
- Message format: `autobuild: [intent-name] — [step description]`

### Step 2: Quality Gate

Invoke the **Quality Scorer** (`agents/quality-scorer.md`):
- Run the full quality pipeline
- Keep the branch state only if the iteration improves or holds steady and has no CRITICAL security issue
- Treat delivery readiness separately: `>= 80` ready to deliver, `60-79` acceptable with notes, `< 60` not ready

**If the result is not ready for delivery:**
- Review the failing checks
- Have the Builder Agent fix the issues
- Re-run the quality pipeline
- Repeat up to 3 times
- If still failing after 3 attempts → `git reset --hard` to the last known good state and escalate to human. Do not leave the branch in a broken state.

### Step 3: Sub-Agent Reviews

Run all sub-agent reviews (Phase 4 of `program.md`):
- Security Reviewer → any CRITICAL blocks delivery
- Architecture Reviewer → any violation blocks delivery
- Test Writer → add missing tests

### Step 4: Final Score

Invoke **Quality Scorer** one final time (post-reviews, post-test-writing):
- This is the definitive readiness report
- Log to `results/results.tsv`

### Step 5: Present

Generate `evaluation/latest-review.md` and present to human.

## Completion

A standard build is complete when:
- All acceptance criteria are met
- The final result is at least acceptable with notes
- No CRITICAL security findings
- No architecture violations
- Human has reviewed and approved
