# Decision log

Every approval a person decides is written to the venture's decision log in `systems/<venture>/B-brain/decisions/`, as a `decision` entity (spec 002 and 010). Each entry records:

- the approval it came from
- who decided, and through which channel
- the outcome
- the sources it relied on
- the objects it affects

Writes are idempotent on the approval id, so retries never add a second entry.

## Decisions made elsewhere

Many decisions happen in a site meeting, on a call or in a WhatsApp thread. An agent can propose one with the MCP tool `log_decision`, including where it is recorded (`source`) and the exact place (`locator`: page, timestamp, message time). The proposal waits in the approval queue, and only a person's approval records it. A decision without a located source is stored with `verified: false`.

## In the weekly review

The weekly review has a line per venture: decisions recorded this week, and how many have no source. The numbers come from the decision files that exist, never from estimates.

## Export

`realize_core.governance.decision_log.export_markdown(venture_dir, language="he" | "en" | "pt")` returns the log as a table, ready to render as a finished document.

Inputs and credentials (answers to skill questions, credentials an agent asked for) are not decisions and are never logged.
