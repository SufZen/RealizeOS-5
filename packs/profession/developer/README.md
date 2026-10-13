# Developer profession pack

For residential, commercial and mixed-use developers. Market-neutral: currency, terms, contract forms and local rules come from the market pack.

**Contents:**

- **The team** (`A-agents/`): orchestrator, tenders, procurement, site and payments, finance and investors, and a reviewer, with their routing guide (`_README.md`).
- **Three skills** (`R-routines/skills/`): tender requirements register, payment claim vs milestone, and investor report. Writes to Sheets wait for an approval; nothing is sent or paid.
- An English glossary mapped to core families, `payment-claim` and `tender-item` schema extensions, value-report measures, an investor-report template, and trust defaults that hold Sheets, Drive and Gmail writes for approval (they only ever tighten a venture's trust settings).

**How a venture uses it** (with `features.packs` on): list `developer` under `profession` in the venture's `packs.yaml`. The team and the skills then come from this pack at run time; nothing is copied into the venture. Set the venture's own sheet and document ids in `F-foundations/overrides/skill-settings.yaml` (a venture created from the `real-estate-developer` template gets a starter file). A market pack adds local terms, rules and triggers in the local language for the three skills.

A venture's own copy always wins: a venture created before packs, or with packs off, has the agents and skills copied from `templates/real-estate-developer/` and keeps using them. To change a skill's steps for one venture, copy it into the venture's `R-routines/skills/`.

**Limits:** see `pack.yaml`. This pack prepares checks and drafts. People decide.
