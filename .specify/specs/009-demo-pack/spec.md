# Feature Specification: Demo Pack v0 — Real Estate Developer

**Feature Branch**: `feat/story-20-demo-pack`
**Created**: 2026-10-11
**Status**: Implemented (5.7.0)
**Input**: Release plan STORY-20. The webinar storyline (tender → payment → investor report) works
end to end on a Hebrew demo venture, with real tool steps and approvals.

## User Scenarios & Testing

### User Story 1 — A developer's team, ready to use (P1)

**Acceptance**: `realize-os venture create --template real-estate-developer` (or the seed script)
creates a venture whose agents are tenders, procurement, site_payments, finance_investors,
reviewer and orchestrator, with domain knowledge, company rules and three working skills.

### User Story 2 — The webinar storyline (P1)

**Acceptance**:
1. Hebrew requests trigger the right skill.
2. Tender: the tender document is read from Drive, requirements are extracted as rows, and the
   register write is held for approval; approving appends the rows once.
3. Payment: the request is checked against the milestone sheet; the payment row is held for
   approval; approving appends it once; nothing is paid or sent.
4. Investor report: figures from the budget sheet, a reviewer step, a final draft that says it was
   not sent.

### Edge cases

- An agent step returns JSON in code fences or with prose around it: the rows are still read.
- No JSON at all, or JSON of the wrong shape (a flat list where rows are expected): the tool
  step fails before writing.
- Any tool step fails (unknown tool, policy block, tool error): the workflow stops at that step,
  says which step and why, and runs nothing after it.
- Skill YAML with Hebrew triggers loads on Windows (UTF-8).

## Requirements

- **FR-001** `templates/real-estate-developer/` FABRIC with the storyline agents.
- **FR-002** Skills: `tender_requirements_register`, `payment_milestone_check`, `investor_report`.
- **FR-003** Executor: skill `variables:` for per-venture ids; step `json_params` for structured
  tool input.
- **FR-004** `realize_core.demo_seed.seed_webinar_demo` + `scripts/seed_webinar_demo.py`: the
  Hebrew demo venture with labelled demo documents, `locale: he` and the template routing.
- **FR-005** `tests/e2e/test_webinar_flow.py` scripts the storyline with a mocked LLM and Google tools.
- **FR-006** Skill tool steps emit trail events (`tool_call`, `approval_requested`,
  `tool_result`) and the skill answer is stored with its trail, so `/api/chat` and the
  conversation history show what the skill read and which write is waiting for approval.
  Covered through the real API, as a venture-scoped operator, in the storyline test.

## Assumptions

- Demo figures are fictional. Real Drive and Sheets ids are set by the presenter (see
  `docs/webinar-demo.md`).
- Agent steps in skills answer without tools; tool access in skills is through tool steps.
