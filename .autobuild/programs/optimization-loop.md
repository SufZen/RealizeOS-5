# Optimization Loop Program

> Targeted metric optimization. Given a specific metric, hill-climb toward the optimal value.

## When to Use

- You have a specific, measurable metric to optimize (latency, bundle size, memory usage, test run time, token count)
- The metric can be measured programmatically
- You want to systematically improve toward a target

## Configuration

Set these in the intent:
- **Target metric:** What to optimize (e.g., "response latency", "bundle size")
- **Measurement command:** How to measure (e.g., `npm run benchmark`, `python measure.py`)
- **Direction:** `minimize` or `maximize`
- **Target value:** Optional goal (e.g., "< 100ms", "> 95% accuracy")
- **Budget:** Max iterations (default: 20)

## Workflow

### Step 1: Baseline

1. Run the measurement command
2. Record baseline value
3. Log: `[timestamp] [baseline] [value] [keep] [initial measurement]`

### Step 2: Optimization Loop

```
FOR iteration IN 1..budget:
  1. Analyze
     - What is the current bottleneck?
     - Profile/inspect to find the biggest opportunity
  
  2. Propose optimization
     - ONE change at a time
     - Low-risk: algorithmic improvement, caching, lazy loading
     - Medium-risk: data structure change, parallelization
     - High-risk: architectural change (only if lower-risk options exhausted)
  
  3. Implement the change
  
  4. Measure
     - Run measurement command
     - Also run quality pipeline (optimization must not break tests/security)
  
  5. Decision:
     IF metric_improved (strictly `<` or `>` depending on direction) AND quality score improved or held steady AND no CRITICAL security issue:
       → git commit: "autobuild-optimize: [what] — metric: [new_value] (+[delta])"
       → Log: keep
     ELSE:
       → git reset --hard HEAD && git clean -fd
       → Log: discard + reason (metric worse / lateral / quality dropped)

     Readiness bands:
       → score >= 80 = ready to deliver
       → score 60-79 = acceptable with notes
       → score < 60 = not ready yet
  
  6. Check target:
     IF target_value is set AND metric has reached target:
       → STOP — target reached
```

### Step 3: Report

```markdown
## Optimization Report — [Intent Name]

**Metric:** [name]
**Direction:** [minimize/maximize]
**Baseline:** [initial value]
**Final:** [current value]
**Improvement:** [absolute and percentage]
**Target:** [value if set] — [REACHED / NOT REACHED]

### Optimization History
| # | Change | Metric Before | Metric After | Delta | Status |
|---|--------|--------------|-------------|-------|--------|
| 1 | Added LRU cache | 145ms | 89ms | -56ms | ✅ keep |
| 2 | Switched to Map | 89ms | 91ms | +2ms | ❌ discard |
| 3 | Batch DB queries | 89ms | 42ms | -47ms | ✅ keep |

### Key Insights
1. [What had the biggest impact]
2. [What surprisingly didn't help]
3. [Remaining optimization opportunities]
```

## Rules

- Quality must not regress and CRITICAL security issues are never allowed
- Security checks must still pass
- Each optimization must be its own commit (easy to revert individually)
- If 5 consecutive iterations show no strict improvement → stop and report (diminishing returns)
