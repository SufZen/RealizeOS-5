# Quality Pipeline

The Quality Pipeline produces a composite score (0-100) that drives both branch retention and delivery readiness.

## How to Run

After every implementation iteration:

1. Read `quality-config.md` for project-specific commands and weights
2. Run each check in order
3. Score each check (pass = full points, partial = proportional)
4. Sum weighted scores → composite Quality Score
5. Decide branch retention and delivery readiness
6. Log to `results/results.tsv`

## Default Checks & Weights

| # | Check | What It Measures | Default Weight | Default Command |
| --- | --- | --- | --- | --- |
| 1 | **Tests** | Do all tests pass? | 35% | `[from quality-config]` |
| 2 | **Lint / Format** | Is code clean and formatted? | 15% | `[from quality-config]` |
| 3 | **Security** | No secrets, no vulnerable deps, no injection? | 15% | `[from quality-config]` |
| 4 | **Type Safety** | Does code pass type checking? | 10% | `[from quality-config]` |
| 5 | **Complexity** | Is code maintainable? | 10% | Count functions, LOC-per-function, nesting depth |
| 6 | **Coverage** | Are new lines tested? | 5% | `[from quality-config]` |
| 7 | **Architecture** | Does code follow project conventions? | 10% | Manual check against `project-context.md` |

## Scoring Rules

### Binary Checks (pass/fail)

Tests, Lint, Type Safety:
- **Pass** → full weight as points (e.g., Tests pass → 35 points)
- **Fail** → 0 points

### Graduated Checks

Security:
- **Clean** → 15 points
- **Warnings only** → 10 points
- **Critical findings** → 0 points AND automatic DISCARD

Coverage:
- Score = `(coverage% / 100) × 5`
- Example: 80% coverage = 4.0 points

Complexity:
- **Low complexity** (avg < 10 LOC/function, no deep nesting) → 10 points
- **Medium** → 6 points
- **High** (functions > 50 LOC, nesting > 4 levels) → 2 points

Architecture:
- **Fully compliant** with project-context.md → 10 points
- **Minor deviations** → 6 points
- **Violations** → 0 points

## Composite Score Calculation

```
Quality Score = tests_score + lint_score + security_score + types_score 
             + complexity_score + coverage_score + architecture_score

Range: 0 - 100
```

## Retention vs Readiness

AutoBuild uses one score for two different decisions.

### Branch Retention

- Improved or maintained score and no CRITICAL security finding → keep the branch state
- Lower score or CRITICAL security finding → discard the branch state

### Delivery Readiness

| Threshold | Action |
| --- | --- |
| Score ≥ 80 | ✅ Ready to deliver |
| Score 60-79 | ⚠️ Acceptable with notes |
| Score < 60 | ❌ Not ready for delivery |
| Security CRITICAL | 🚫 Never ready for delivery |

## Results Logging

Append to `results/results.tsv` after every iteration:

```tsv
timestamp	branch	intent	approach	quality_score	tests	lint	security	types	complexity	coverage	architecture	status	description
```

Fields:
- `timestamp`: ISO 8601 format
- `branch`: git branch name
- `intent`: intent file name
- `approach`: approach identifier (for iterative mode)
- `quality_score`: composite score (0-100)
- `tests` through `architecture`: individual check results
- `status`: branch action only — `keep` or `discard`
- `description`: brief notes on what was attempted

## Adapting Weights

Projects can customize weights in `quality-config.md`. Common adjustments:

- **Security-critical apps** → Security: 25%, Tests: 30%, others reduced
- **High-performance apps** → Add Performance check at 15%, reduce others
- **Prototypes/MVPs** → Tests: 40%, Lint: 20%, others minimal
