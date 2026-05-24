---
on:
  schedule: weekly
  workflow_dispatch:
permissions:
  contents: read
  actions: read
  issues: read
safe-outputs:
  create-issue:
    title-prefix: "[workflow-health] "
tools:
  github:
---

# Workflow Health Manager

Analyze the health of all GitHub Actions workflows in this repository and produce a weekly health report.

## Steps

1. List all workflow files in `.github/workflows/`.
2. For each workflow, check the last 10 runs. Note: success rate, average duration, and any persistent failures.
3. Identify workflows that:
   - Have failed more than 3 times in the last 7 days
   - Have runs taking longer than 15 minutes (performance regression)
   - Have been disabled or not run in over 30 days
4. Check if any workflow YAML files have syntax issues or use deprecated actions (major version behind latest).
5. Create a summary issue titled "[workflow-health] Weekly Report — {date}" with:
   - A table of all workflows with status, success rate, avg duration
   - A section for "Action Required" listing any failing or degraded workflows
   - Recommendations for optimization if any runs exceed 10 minutes
