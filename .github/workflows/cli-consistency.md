---
on:
  schedule: weekly
  workflow_dispatch:
permissions:
  contents: read
  issues: read
safe-outputs:
  create-issue:
    title-prefix: "[cli-check] "
tools:
  github:
---

# CLI Consistency Checker

Audit the RealizeOS CLI for consistency, completeness, and adherence to the project conventions. Covers both the Python CLI (`realize_core/cli_app/`) and the Node CLI (`realize-os-cli/`).

## Steps

1. **Python CLI audit:**
   - Read all files in `realize_core/cli_app/` and `cli.py`
   - Check that every Typer command group has a docstring
   - Verify `--format table|json|yaml` is available on list/get commands
   - Check that error handling uses `rich.console.Console.print_exception()` or `typer.echo` (no raw `print()` — enforced by T20 ruff rule)
   - Verify help text is present for all commands and options

2. **Node CLI audit:**
   - Read `realize-os-cli/src/` files
   - Check that every command has a description in the CLI help
   - Verify the CLI version matches the root package version

3. **Cross-CLI consistency:**
   - Compare command names between Python and Node CLIs
   - Flag any commands that exist in one but not the other (expected divergence is documented; unexpected is flagged)

4. **Output:**
   - If inconsistencies found, create an issue titled "[cli-check] CLI Consistency Report — {date}" with findings
   - If both CLIs are consistent, do not create an issue
