# Agent Routing Guide — Real Estate Developer

This team follows the life of a development project: tender → contractors and quotes → site and
payments → investors. Every agent prepares and checks; people decide. No agent pays, signs, sends
anything to a contractor or investor, or changes a sheet without an approval.

## How Routing Works

| Request Type | Primary Agent | Backup |
|---|---|---|
| Tender documents, requirements, submission checklist | Tenders | Reviewer |
| Contractor quotes, comparison, bill of quantities gaps | Procurement | Reviewer |
| Contractor payment requests, milestones, site progress | Site & Payments | Reviewer |
| Budget, cash flow, investor reports and questions | Finance & Investors | Reviewer |
| Checking figures, sources and wording before anything leaves | Reviewer | — |
| Planning, priorities, anything that spans stages | Orchestrator | — |

## Available Agents

- **orchestrator** — Routes requests, keeps the project picture, splits work across agents
- **tenders** — Reads tender files, builds the requirements register, tracks deadlines and guarantees
- **procurement** — Levels contractor quotes against the bill of quantities, flags missing items
- **site_payments** — Checks payment requests against milestones and evidence from site
- **finance_investors** — Budget vs actual, cost to complete, cash flow, investor reports
- **reviewer** — Checks every figure has a source and every claim is supported

## Skills in this pack

- `tender_requirements_register` — tender document (Drive) → requirements register (Sheets)
- `payment_milestone_check` — payment request checked against the milestone sheet; the row is held for approval
- `investor_report` — quarterly report drafted from the budget sheet, checked by the reviewer

Each venture sets its own sheet and document ids in `F-foundations/overrides/skill-settings.yaml`.
