# Review sheet: United Kingdom market pack (uk@0.1.0)

Verification level 1 (drafted). 10 rule cards, 1 glossary lists and 1 defaults row. Fill in `review-sheet.csv`, or write on this printout and send it back.

## How to review (about 60 minutes)

An AI agent drafted this pack from public sources. It is labelled verification level 1 (a draft). Your review lets it be marked as reviewed (level 2), with your name on each card you review.

For each card, check:

1. Is the statement correct and current for United Kingdom?
2. Does the source support it? A better or official source is welcome.
3. Is anything important missing, misleading or out of date?

Then fill in:

- verdict: correct, corrected or removed.
- facts corrected: how many separate facts you changed (0 if correct). facts checked is our estimate of the facts in the statement; change it if you count differently.
- corrected statement: your wording, if you corrected the card.
- reviewer note: anything else, such as a better source or an exception.

The glossary and defaults rows are optional. Your name, title and registration number are recorded on every card you review.

## Cards

### 1. uk.planning.two-approvals

**Statement:** Building in England usually needs both planning permission from the local planning authority and building regulations approval from a building control body; they are separate regimes.

> Track them as two separate milestones.
>
> Source note: the cited page covers building control for higher-risk buildings; the two-regime statement is general knowledge to verify on planningportal.co.uk.

- Source: <https://buildingsafety.campaign.gov.uk/making-buildings-safer/building-safety-regulator-news/building-safety-regulator-is-now-the-building-control-authority/>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: milestone: permit
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 2. uk.tax.construction-industry-scheme

**Statement:** Under the Construction Industry Scheme, contractors deduct 20% from the labour part of payments to registered subcontractors, 30% for unregistered ones and 0% for those with gross payment status, and pay it to HMRC.

> Materials and VAT are excluded from the deduction. Verify each subcontractor's status with HMRC before the first payment.

- Source: <https://gov.uk/what-you-must-do-as-a-cis-contractor/make-deductions-and-pay-subcontractors>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: money-event: payment_claim
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 3. uk.construction-act.payment-notices

**Statement:** Under the Housing Grants, Construction and Regeneration Act 1996 (as amended in 2011), construction contracts must provide stage payments, a payment notice for each due sum, and a pay less notice with its basis if the payer intends to pay less; without a pay less notice the notified sum must be paid.

> If the payer issues no payment notice, the payee can issue a default notice. Contracts that don't comply fall back on the Scheme for Construction Contracts. Track every due date, notice and final date for payment.

- Source: <https://www.legislation.gov.uk/ukpga/1996/53>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: money-event: payment_claim
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 4. uk.contracts.standard-forms

**Statement:** UK construction mostly uses the JCT and NEC families of standard contracts; JCT calls changes 'variations' and NEC calls them 'compensation events', with their own notice and timing rules.

> Read the specific form and amendments: NEC compensation events have time bars that can remove entitlement.
>
> Source note: the cited summary covers the Construction Act, not JCT or NEC; the forms' terminology here is general knowledge to verify against jctltd.co.uk and neccontract.com.

- Source: <https://www.fenwickelliott.com/sites/default/files/h_hgcra.pdf>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: change: variation
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 5. uk.liability.defective-premises-act

**Statement:** The Building Safety Act 2022 extended the Defective Premises Act limitation period to 15 years for dwelling works completed after 28 June 2022, and to 30 years retrospectively for earlier works.

> Keep project records accordingly. Law-firm source; confirm the transitional provisions on legislation.gov.uk.

- Source: <https://www.hsfkramer.com/notes/construction/2022-06/building-safety-act-2022-dont-throw-away-those-old-records-just-yet>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: issue: defect
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 6. uk.sales.energy-performance-certificate

**Statement:** An Energy Performance Certificate is needed before marketing a property for sale or rent and when a building is constructed; it is valid for 10 years, and fines apply when one is missing.

> Rented homes must meet a minimum EPC rating; check gov.uk for the current minimum.

- Source: <https://gov.uk/buy-sell-your-home/energy-performance-certificates>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: milestone: handover
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 7. uk.building-safety.hrb-gateways

**Statement:** In England, higher-risk buildings (at least 18 m or 7 storeys with at least two residential units, and hospitals and care homes) go through three gateways; the Building Safety Regulator is their building control authority and must approve work before construction and before occupation.

> Plan the programme around gateway 2 (before construction) and gateway 3 (completion certificate before occupation).

- Source: <https://buildingsafety.campaign.gov.uk/making-buildings-safer/building-safety-regulator-news/building-safety-regulator-is-now-the-building-control-authority/>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: milestone: permit, handover
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 8. uk.construction-act.no-pay-when-paid

**Statement:** Pay-when-paid clauses are generally ineffective in UK construction contracts (section 113 of the Construction Act), and either party may refer a dispute to adjudication at any time (section 108).

> Law-firm summary; the Act's text is at legislation.gov.uk/ukpga/1996/53.

- Source: <https://www.fenwickelliott.com/sites/default/files/h_hgcra.pdf>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: requirement: code_rule
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 9. uk.taxes.stamp-duty-land-tax

**Statement:** Residential purchases in England and Northern Ireland pay Stamp Duty Land Tax on bands of the price, with a 5% surcharge on top when the buyer already owns a residential property and reliefs for first-time buyers.

> Bands change; take them from the current gov.uk page or calculator, never from memory. Scotland and Wales have their own taxes.

- Source: <https://www.gov.uk/stamp-duty-land-tax/residential-property-rates>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: money-event: budget_line
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 10. uk.vat.construction

**Statement:** UK building work is normally standard-rated at 20% VAT; constructing new qualifying dwellings is zero-rated, and some conversions to dwellings are reduced-rated at 5% (HMRC VAT Notice 708).

> Some zero rating needs a certificate (relevant residential or charitable use). Check the notice for each package; subcontractors on a zero-rated new dwelling can also zero-rate.

- Source: <https://www.gov.uk/guidance/buildings-and-construction-vat-notice-708>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: money-event: invoice, quote
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 11. defaults

Defaults the pack sets for every venture in this market.

- country: GB
- currency: GBP
- units: metric
- locale: en-GB
- work_week: mon, tue, wed, thu, fri

**Your review (optional row)**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 5 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 12. glossary:en

Glossary (en): each local term mapped to a core family and kind. Check that each term means what its mapping says.

- interim payment application → money-event / payment_claim
- interim valuation → money-event / payment_claim
- payment notice → money-event / payment_claim
- pay less notice → money-event / payment_claim
- variation → change / variation
- compensation event → change / variation
- practical completion → milestone / handover
- completion certificate → milestone / handover
- planning permission → milestone / permit
- building regulations approval → milestone / permit
- defects liability period → milestone / handover
- snagging → issue / defect
- retention → money-event
- main contractor → contact / contractor
- subcontractor → contact / subcontractor
- employer → contact / client
- contract administrator → contact / supervisor
- adjudication → issue / compliance

**Your review (optional row)**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 18 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________
