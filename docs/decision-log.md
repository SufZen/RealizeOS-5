# Decision log

Every approval a person decides is written to the venture's decision log in `<venture folder>/B-brain/decisions/`, as a `decision` entity (spec 002 and 010). Each entry records:

- the approval it came from
- who decided, and through which channel
- the outcome
- the sources it relied on
- the objects it affects

Writes are idempotent on the approval id, so retries never add a second entry. An entry is dated when the decision was made, even when it is written later.

## Which folder

The venture folder is the `directory` of the venture's entry in `realize-os.yaml`, the same one the rest of RealizeOS reads. It can differ from the key:

```yaml
systems:
  - key: acme
    directory: systems/acme-office   # decisions go to systems/acme-office/B-brain/decisions/
```

Without a `directory`, the folder is `systems/<key>` (or the older `ventures/<key>`). A `directory` that isn't a folder directly inside `systems/` or `ventures/` is refused: nothing is written, and the approval result says why.

## When a write fails

The decision is logged as soon as it is made, before the approved action runs. If the file can't be written (disk full, a read-only mount, the venture folder isn't there yet), the decision still stands and the write is kept in a queue (`decision_writes` in the operational database) instead of being lost. The queue entry is stored in the same database transaction as the decision itself, so even if the server stops right after a decision, before anything else happens, the entry is written when it starts again. Queued writes are retried:

- when the server starts;
- after the next decision that is logged;
- when the owner runs `realize-os decisions retry` (or `python cli.py decisions retry`) on the server.

The server's own retries stop after 5 failed attempts for one decision, so a venture whose folder is gone doesn't slow every approval; `realize-os decisions retry` still tries every queued write and lists the ones still waiting, with the reason. A retry rebuilds the entry from the approval, so it is the same entry the first attempt would have written, and a decision already on disk is never written twice.

The approval result says what happened. `POST /api/approvals/{id}/approve` and `/reject` return `decision_log`:

```json
{"logged": false, "pending": true, "error": "No space left on device", "decision_id": null}
```

`logged` is true once the entry is on disk (`decision_id` names it); `pending` means it is queued for a retry. For inputs and credentials (below) both are false and `error` is null. The MCP tools `approve_request` and `reject_request` report `decision_logged` and `decision_log_pending`.

## Decisions made elsewhere

Many decisions happen in a site meeting, on a call or in a WhatsApp thread. An agent can propose one with the MCP tool `log_decision`, including where it is recorded (`source`) and the exact place (`locator`: page, timestamp, message time). The proposal waits in the approval queue, and only a person's approval records it. A decision without a located source is stored with `verified: false`.

## In the weekly review

The weekly review has a line per venture: decisions recorded this week, and how many have no source. The numbers come from the decision files that exist, never from estimates.

## Export

`realize_core.governance.decision_log.export_markdown(venture_dir, language="he" | "en" | "pt")` returns the log as a table, ready to render as a finished document.

Inputs and credentials (answers to skill questions, credentials an agent asked for) are not decisions and are never logged.
