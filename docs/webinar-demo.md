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

## 2. Connect Google

Use a separate Google account for the demo, with demo data only.

1. **Google sign-in.** In Google Cloud, create an OAuth client of type "Desktop app" with the
   Drive and Sheets APIs enabled, and add the demo account as a test user. Save the client JSON
   as `.credentials/client_secrets.json`, then run:

   ```bash
   python scripts/google_signin.py      # opens the browser; saves .credentials/tokens.json
   ```

   Google warns that the app isn't verified: it is your own client, so continue. The consent
   covers all the Google tools RealizeOS has (Gmail, Calendar, Drive, Sheets); the demo only
   reads Drive and reads and appends to the sheet.

2. **The project sheet.** Create one Google Sheet. Import each file from
   `templates/demos/tower-b-he-google/` as its own tab (File → Import → Upload → "Insert new
   sheet(s)") and name the tabs exactly:

   | Tab | File | Used by | Content |
   |---|---|---|---|
   | `Requirements` | `Requirements.csv` | `tender_requirements_register` | header only; the register is appended here |
   | `Milestones` | `Milestones.csv` | `payment_milestone_check` | the 8 milestones of the main contract |
   | `Payments` | `Payments.csv` | `payment_milestone_check` | header only; checked requests are appended here |
   | `Summary` | `Summary.csv` | `investor_report` | the budget at the end of Q3 |

3. **The tender document.** Upload `templates/demos/tower-b-he-google/tender-document.txt` to
   Drive and open it as a Google Doc. It contains one deliberate contradiction (performance
   guarantee 10% in conditions 6.5 vs 5% in contract 18) for the register to flag.

4. **Set the ids** (the long ids in the sheet's and the document's URLs):

   ```bash
   python scripts/rehearse_webinar_demo.py set-ids --sheet <sheet id> --tender-doc <doc id>
   ```

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

Before every rehearsal and on the day, run the read-only check. It never writes to Google:

```bash
python scripts/rehearse_webinar_demo.py check
```

It checks the feature flags, an LLM key, the Google sign-in, every tab and the tender document,
that each storyline message triggers the right skill, and a presenter account limited to the demo
venture. Each failing line says how to fix it. Then:

- Run each case once before the session; keep screenshots as a fallback.
- The demo data is fictional; say so on screen.
- Approvals: open the Approvals page next to the chat to show the decision step.
