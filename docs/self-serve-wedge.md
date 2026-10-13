# Self-serve tender register (pilot)

A free workflow that anyone can run from their own AI agent, in any market, with no consultant involved. It is the first value RealizeOS gives a new user (ADR 0005, Play W). Everything after it (the firm's own brain, governance, verified market packs) is delivered by the practice or a local partner.

## How it works

1. The user connects their agent (Claude, ChatGPT or another MCP client) to a RealizeOS server with the pilot on.
2. The agent calls `tender_register_method` with the project's market, if known. It gets:
   - the steps
   - the register format
   - the market's local terms and sourced rule cards, with their verification level
3. The agent reads the tender PDF itself and builds the register.
4. The agent calls `tender_register_submit`. RealizeOS then:
   - checks the register: duplicates, categories, items without a page
   - returns it as a finished document in English, Hebrew or Portuguese, stating its verification level and limits
   - offers a hand-off: book an Audit Sprint, or a local partner where one exists
5. If the user wants to talk, the agent calls `request_audit_call` with a contact the user chose to share.

Without a market pack, the document says plainly that local rules are unverified general knowledge (level 0).

## Turn it on

```yaml
features:
  wedge: true
wedge:
  booking_url: https://example.com/audit-sprint
  partners:
    pt: {name: "Partner name", url: "https://partner.example"}
```

## Limits

- Up to 300 register items per run (about a 50-page tender), and 10 runs per user per day.
- No document text is stored, only counts, market and verification level.
- Runs are deleted after 30 days unless the user asked to be contacted. Call `realize_core.wedge.purge_expired()` from a scheduled job.

## Measuring it

`realize_core.wedge.funnel(days=30)` returns runs, users and call requests per market, from recorded runs only. The pilot passes if 30% of users who run it request a call, and at least one comes from outside Israel.

Connection guides for each agent are part of STORY-37 (`docs/connect-your-agent.md`).
