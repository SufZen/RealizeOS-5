# Review sheet: United States market pack (us@0.1.0)

Verification level 1 (drafted). 10 rule cards, 1 glossary lists and 1 defaults row. Fill in `review-sheet.csv`, or write on this printout and send it back.

## How to review (about 60 minutes)

An AI agent drafted this pack from public sources. It is labelled verification level 1 (a draft). Your review lets it be marked as reviewed (level 2), with your name on each card you review.

For each card, check:

1. Is the statement correct and current for United States?
2. Does the source support it? A better or official source is welcome.
3. Is anything important missing, misleading or out of date?

Then fill in:

- verdict: correct, corrected or removed.
- facts corrected: how many separate facts you changed (0 if correct). facts checked is our estimate of the facts in the statement; change it if you count differently.
- corrected statement: your wording, if you corrected the card.
- reviewer note: anything else, such as a better source or an exception.

The glossary and defaults rows are optional. Your name, title and registration number are recorded on every card you review.

## Cards

### 1. us.payments.aia-g702

**Statement:** US pay applications commonly use AIA Document G702 (Application and Certificate for Payment) with G703 (Continuation Sheet), which lists each line of the schedule of values, work completed, stored materials and the balance to finish.

> Check each G703 line against the schedule of values and the milestone before certifying. AIA forms are copyrighted; use licensed copies.

- Source: <https://oasas.ny.gov/aia-document-g703>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: money-event: payment_claim
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 2. us.permits.local

**Statement:** Building permits and certificates of occupancy are issued by the local building department under the building code the state or locality has adopted; occupancy normally needs a certificate of occupancy.

> Procedures and timelines are local; record the jurisdiction on the project.
>
> Source note: the cited page covers energy codes only; the permit and occupancy statement is general knowledge to verify with the local building department.

- Source: <https://www.energycodes.gov/status/states/new-york>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: milestone: permit, handover
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 3. us.contractors.state-licensing

**Statement:** Contractor licensing is set by each state (thresholds, classifications, exams, bonding and insurance), and many localities add their own registration or business licence.

> Training-provider source. Verify each bidder's licence with the state board before award.

- Source: <https://contractortrainingcenter.com/blogs/news/nascla-or-icc-exam-which-should-i-take>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: contact: contractor, subcontractor
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 4. us.codes.energy-code-by-state

**Statement:** Each state adopts its own energy code, usually an edition of the IECC (residential) and ASHRAE 90.1 (commercial), sometimes with amendments; editions differ widely between states.

> Look up the project state's profile on energycodes.gov at the design stage.

- Source: <https://www.energycodes.gov/status/states/new-york>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: requirement: code_rule
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 5. us.federal.subcontractor-payment

**Statement:** Federal prime contractors must pay subcontractors within 7 days of receiving payment from the Government, or owe interest, under the Prompt Payment for Construction Contracts clause.

> Federal Register notice from 2001; confirm against the current clause.

- Source: <https://www.govinfo.gov/content/pkg/FR-2001-08-07/pdf/01-19662.pdf>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: money-event: payment_claim
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 6. us.federal.prompt-payment

**Statement:** On federal construction contracts, the Prompt Payment clause (FAR 52.232-27) sets 14 days for progress payments after a proper request, which the contracting officer may not shorten below 7 days.

> Private and state work follow state prompt-payment laws, which differ.

- Source: <https://www.acquisition.gov/far/32.908>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: money-event: payment_claim
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 7. us.liens.state-deadlines

**Statement:** Mechanics lien rights are state law: most states require a preliminary notice to preserve them, and lien filing deadlines are usually 3 months to a year after the work is completed, depending on the state and the claimant's role.

> For example, California requires preliminary notice within 20 days of first furnishing. Always check the project state's statute; collect lien waivers with each payment.

- Source: <https://www.levelset.com/blog/lien-and-notice-deadlines-in-all-50-states/>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: requirement: code_rule
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 8. us.federal.miller-act-claims

**Statement:** Second-tier claimants on a Miller Act payment bond must give notice within 90 days of last furnishing labour or materials, and suits must be filed within one year.

> Credit-services source; confirm against 40 U.S.C. 3133.

- Source: <https://www.ncscredit.com/education-center/blog/payment-bond-information-federal-project>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: requirement: covenant
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 9. us.federal.miller-act-bonds

**Statement:** Federal construction contracts over $150,000 require performance and payment bonds under the Miller Act as implemented by FAR 28.102-1; the statute's own threshold is $100,000.

> Between $35,000 and $150,000 the contracting officer must require alternative payment protections. Many states have 'Little Miller Acts' for state projects.

- Source: <https://www.acquisition.gov/far/28.102-1>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: requirement: covenant
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 10. us.payments.retainage

**Statement:** Retainage of 5–10% of each progress payment is common in the US and is regulated by state law; California caps it at 5% for contracts entered into from 1 January 2026, with residential exceptions.

> Check the project state's cap and release deadline (California: release within 45 days of completion).

- Source: <https://www.levelset.com/retainage/california-retainage-law/>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: money-event: payment_claim
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 11. defaults

Defaults the pack sets for every venture in this market.

- country: US
- currency: USD
- units: imperial
- locale: en-US
- work_week: mon, tue, wed, thu, fri

**Your review (optional row)**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 5 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 12. glossary:en

Glossary (en): each local term mapped to a core family and kind. Check that each term means what its mapping says.

- pay application → money-event / payment_claim
- pay app → money-event / payment_claim
- schedule of values → money-event / budget_line
- change order → change / variation
- construction change directive → change / variation
- retainage → money-event
- substantial completion → milestone / handover
- certificate of occupancy → milestone / handover
- building permit → milestone / permit
- punch list → issue / defect
- lien waiver → requirement / covenant
- mechanics lien → requirement / covenant
- preliminary notice → requirement / code_rule
- payment bond → requirement / covenant
- performance bond → requirement / covenant
- general contractor → contact / contractor
- subcontractor → contact / subcontractor
- owner → contact / client

**Your review (optional row)**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 18 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________
