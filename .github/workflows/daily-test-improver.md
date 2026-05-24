---
on:
  schedule: daily
  workflow_dispatch:
permissions:
  contents: read
  issues: read
  pull-requests: read
safe-outputs:
  create-issue:
    title-prefix: "[test-improve] "
tools:
  github:
---

# Daily Test Improver

Analyze the test suite and identify opportunities for improvement. Run daily to catch coverage gaps and test quality issues.

## Steps

1. Read `pyproject.toml` to understand the test configuration, coverage settings, and markers.
2. Examine the latest CI test run artifacts (if available) — look at the `coverage.xml` report.
3. Identify:
   - Source files in `realize_core/` with less than 50% test coverage
   - Test files that have been modified in the last 7 days (look for regressions)
   - Any test files that import from modules not in `realize_core/` or `realize_api/` (test isolation issue)
   - Tests marked as `@pytest.mark.slow` that consistently take more than 10 seconds (optimization candidates)
4. Check for common test anti-patterns:
   - Tests with no assertions (empty test bodies)
   - Tests that catch exceptions too broadly (`except Exception`)
   - Tests that use `time.sleep()` instead of proper async waiting
5. If there are actionable findings (3+ items), create an issue titled "[test-improve] Coverage & Quality Report — {date}" with:
   - Coverage gaps table (file, current %, recommended target)
   - Anti-pattern findings with file:line references
   - Suggested test additions (module + what to test)
6. If the test suite is healthy (fewer than 3 findings), do not create an issue.
