# Iterative Build Program

> Try multiple approaches, score each, keep the best. Use when there are multiple valid implementations.

## When to Use

- Multiple valid implementation approaches exist
- You want to find the optimal solution, not just a working one
- The problem space benefits from comparison (caching strategies, algorithm choices, architectural patterns)

## Configuration

- **Max approaches:** 3 (default, override in intent)
- **Branch pattern:** `autobuild/[intent-name]/approach-[N]`
- **Each approach runs the full quality pipeline independently**

## Workflow

### Step 1: Generate Approaches

Before implementing, think through distinct approaches:

```markdown
APPROACHES:
1. [Approach A] — [one sentence description] — rationale: [why this might be best]
2. [Approach B] — [one sentence description] — rationale: [why this might be best]
3. [Approach C] — [one sentence description] — rationale: [why this might be best]
```

Present approaches to human for selection (unless overnight mode).

### Step 2: Implement Each Approach

Ensure the base branch is explicitly created and locked: `git checkout -b autobuild/[intent-name] main` (if it does not exist) or `git checkout autobuild/[intent-name]` (if it does).

For each approach:

1. Create approach branch from base: `git checkout -b autobuild/[intent-name]/approach-[N] autobuild/[intent-name]`
2. Invoke **Builder Agent** — implement the approach
3. Invoke **Quality Scorer** — run full pipeline
4. Invoke **Security Reviewer** — check for vulnerabilities
5. Keep the branch state only if the approach improves or matches the current best and has no CRITICAL security issue
6. Log score and branch action to `results/results.tsv`

**Important:** Start each approach from the same base (branch from `autobuild/[intent-name]`, not from a previous approach). 

### Step 3: Compare

Build comparison table:

```markdown
COMPARISON:
| Approach | Quality Score | Tests | Security | Complexity | Key Tradeoff |
|----------|--------------|-------|----------|------------|-------------|
| A: [name] | 78 | pass | clean | medium | [tradeoff] |
| B: [name] | 85 | pass | clean | low | [tradeoff] |
| C: [name] | 72 | pass | 1 warn | high | [tradeoff] |

WINNER: Approach B — [reason]
```

Winner selection should consider both:
- Branch retention history: which approach produced the best kept branch state
- Delivery readiness: whether the final result is ready to deliver, acceptable with notes, or still not ready

### Step 4: Polish Winner

On the winning branch:
1. Invoke **Architecture Reviewer**
2. Invoke **Test Writer**
3. Invoke **Quality Scorer** (final)
4. Checkout base branch: `git checkout autobuild/[intent-name]`
5. Merge winning branch deterministically: `git merge --ff-only autobuild/[intent-name]/approach-[WINNER]`
6. Clean up approach branches

### Step 5: Present

Generate `evaluation/latest-review.md` with full comparison data and present to human.

## Completion

An iterative build is complete when:
- All approaches have been tried and scored
- The winner has been polished through sub-agent reviews
- Comparison data is logged in `results/results.tsv`
- The winning result is at least acceptable with notes
- Human has reviewed the comparison and approved the winner
