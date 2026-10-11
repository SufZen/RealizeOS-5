# Webinar Demo: Real Estate Developer (Hebrew)

A ready-made demo of RealizeOS for real-estate developers: a Hebrew venture ("מגדל B — פרויקט
הדגמה", demo data only) with a team that follows the project (tender → contractors → site and
payments → investors) and three skills with real Google Drive and Sheets steps.

## 1. Seed the demo venture

```bash
python scripts/seed_webinar_demo.py          # in the project root; creates systems/tower-b-demo
python cli.py index                          # index the demo documents
```

The venture gets `locale: he` (the dashboard turns right-to-left) and the template's Hebrew-aware
routing. Its documents are in `systems/tower-b-demo/B-brain/project/` and are labelled demo data.

## 2. Connect the sheets

Create one Google Sheet with these tabs and put its id (and the tender document's Drive id) in the
`variables:` block of each skill in `systems/tower-b-demo/R-routines/skills/`:

| Tab | Used by | Content |
|---|---|---|
| `Requirements` | `tender_requirements_register` | empty; the register is appended here |
| `Milestones` | `payment_milestone_check` | the milestone table from `milestones.md` |
| `Payment requests` | `payment_milestone_check` | empty; checked requests are appended here |
| `Summary` | `investor_report` | the budget table from `budget.md` |

## 3. Turn on the features

In `realize-os.yaml`:

```yaml
features:
  agent_tools: true     # agents read Drive and Sheets while answering
  enforce_gates: true   # sheet writes wait for an approval; approving runs them
  cite_sources: true    # answers cite the demo documents as [S1]
```

Give the presenter account `role: operator` and `ventures: [tower-b-demo]` in `users.yaml` for the
locked, single-venture view.

## 4. The storyline

| Case | Message to send (Hebrew) | What to show |
|---|---|---|
| Tender | `תבנה רשימת דרישות מתיק המכרז` | Requirements extracted with their source; the register write waits in Approvals; approve → rows appear in the sheet |
| Payment | `קיבלנו דרישת תשלום 4: 360,000 € על סיום השלד` | Verdict against milestone 4 (no signed supervisor approval yet); the payment row waits for approval; the system never pays |
| Investors | `תכין דוח רבעוני למשקיעים` | A reviewed draft where every figure names its source |
| Live question | `כמה נשאר לנו נטו בתקציב?` | The answer with [S1] footnotes and the "What I used" trail |

## Rehearsal checklist

- Run each case once before the session; keep screenshots as a fallback.
- The demo data is fictional; say so on screen.
- Approvals: open the Approvals page next to the chat to show the decision step.
