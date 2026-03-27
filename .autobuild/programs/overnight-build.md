# Overnight Build Program

> Autonomous long-running loop. Set it up, go to sleep, review results in the morning. Inspired by Karpathy's Autoresearch.

## When to Use

- Large optimization space worth exploring
- You want the AI to work while you're away
- You're comfortable reviewing results batch-style afterward
- The quality pipeline can run automatically (tests, linter, etc. are all configured)

## Critical Rules

1. **STAY AUTONOMOUS.** Keep iterating until the human interrupts you or the plateau rules tell you to stop.
2. **NEVER ASK.** Do not prompt the human for input during the loop. Make autonomous decisions.
3. **ALWAYS LOG.** Every iteration must be recorded in `results/results.tsv`.
4. **ALWAYS BRANCH.** Never push to main. All work stays on `autobuild/[intent-name]`.
5. **ALWAYS REVERT FAILURES.** If quality regresses or a CRITICAL security issue appears, `git reset` to the last good state.

## Workflow

### Setup (Before Starting the Loop)

1. Read all context (Phase 0 of `program.md`)
2. Create branch: `autobuild/[intent-name]`
3. Run initial quality pipeline → record baseline score
4. Parse the intent for:
   - **Optimization target:** What are we trying to improve?
   - **Constraints:** What must NOT change?
   - **Scope:** Which files can we modify?

### The Loop

```
REPEAT FOREVER:
  1. Analyze current state
     - What is the current quality score?
     - What are the weakest areas?
     - What hasn't been tried yet?

  2. Propose one improvement
     - ONE change at a time (small, testable, reversible)
     - Focus on the weakest quality area
     - Or try a new approach to the optimization target

  3. Implement the change
     - Follow project conventions
     - Keep changes small and focused

  4. Run quality pipeline
     - Execute all checks
     - Compute new quality score

  5. Decision:
     IF new_score > best_score AND no CRITICAL security issue:
        → git commit with message: "autobuild-overnight: [what changed] — score: [new_score]"
        → Update best_score
        → Log: [timestamp] [score] [keep] [description]
     ELSE IF new_score == best_score AND no CRITICAL security issue:
        → git commit with message: "autobuild-overnight: [lateral change] — score: [new_score]"
        → Log: [timestamp] [score] [lateral] [description]
     ELSE:
        → git reset --hard HEAD && git clean -fd
        → Log: [timestamp] [score] [discard] [description]

     IF best_score == 100:
        → Log "perfect score reached" and stop

     Delivery readiness bands:
       → score >= 80 = ready to deliver
       → score 60-79 = acceptable with notes
       → score < 60 = not ready yet

  6. Check plateau:
     IF last 5 iterations were not strictly improving (discarded or lateral):
        → Try a fundamentally different approach
        → If 10 consecutive non-improving iterations, log "plateau reached" and stop

  7. CONTINUE (go back to step 1)
```

### Morning Review

When the human returns:

1. Generate summary of all iterations:
   ```markdown
   ## Overnight Run Summary — [Intent Name]
   
   **Duration:** [start time] → [end time]
   **Iterations:** [total count]
   **Kept:** [count] | **Discarded:** [count]
   **Starting score:** [X] → **Final score:** [Y] (+[delta])
   
   ### Top Improvements
   1. [Biggest score jump: what changed]
   2. [Second biggest: what changed]
   3. [Third: what changed]
   
   ### Approaches That Didn't Work
   1. [What was tried and why it was discarded]
   
   ### Full Log
   See results/results.tsv
   ```

2. Run full sub-agent reviews on the final state
3. Present `evaluation/latest-review.md` to human

## Git Safety

- All work on `autobuild/[intent-name]` branch
- Each kept improvement is a separate commit (easy to cherry-pick or revert individually)
- If something goes catastrophically wrong, the branch can be deleted without affecting main
- Commit messages include the quality score: `autobuild-overnight: [desc] — score: [N]`
