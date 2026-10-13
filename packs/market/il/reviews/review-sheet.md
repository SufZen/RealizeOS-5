# Review sheet: Israel market pack (il@0.1.0)

Verification level 1 (drafted). 6 rule cards, 2 glossary lists and 1 defaults row. Fill in `review-sheet.csv`, or write on this printout and send it back.

## How to review (about 45 minutes)

An AI agent drafted this pack from public sources. It is labelled verification level 1 (a draft). Your review lets it be marked as reviewed (level 2), with your name on each card you review.

For each card, check:

1. Is the statement correct and current for Israel?
2. Does the source support it? A better or official source is welcome.
3. Is anything important missing, misleading or out of date?

Then fill in:

- verdict: correct, corrected or removed.
- facts corrected: how many separate facts you changed (0 if correct). facts checked is our estimate of the facts in the statement; change it if you count differently.
- corrected statement: your wording, if you corrected the card.
- reviewer note: anything else, such as a better source or an exception.

The glossary and defaults rows are optional. Your name, title and registration number are recorded on every card you review.

<div dir="rtl" lang="he">

## איך בודקים (כ-45 דקות)

*תורגם על ידי סוכן בינה מלאכותית מההנחיות באנגלית.*

סוכן בינה מלאכותית ניסח את החבילה הזו ממקורות ציבוריים. היא מסומנת ברמת אימות 1 (טיוטה). הבדיקה שלך מאפשרת לסמן אותה כנבדקת (רמה 2), עם שמך על כל כרטיס שבדקת.

בכל כרטיס, בדקו:

1. האם הקביעה נכונה ועדכנית בשוק הזה?
2. האם המקור תומך בה? מקור טוב יותר או רשמי יתקבל בברכה.
3. האם חסר משהו חשוב, או שיש משהו מטעה או לא עדכני?

אחר כך מלאו (את מילות ההכרעה כתבו באנגלית):

- verdict: correct (נכון), corrected (תוקן) או removed (הוסר).
- facts corrected: כמה עובדות נפרדות שיניתם (0 אם הכרטיס נכון). facts checked הוא ההערכה שלנו למספר העובדות בקביעה; שנו אותו אם אתם סופרים אחרת.
- corrected statement: הנוסח שלכם, אם תיקנתם את הכרטיס.
- reviewer note: כל דבר אחר, כמו מקור טוב יותר או חריג.

שורות המילון וברירות המחדל הן רשות. שמכם, התואר ומספר הרישיון נרשמים על כל כרטיס שבדקתם.

</div>

## Cards

### 1. il.planning.building-permit

**Statement:** Building works generally require a building permit under the Planning and Building Law, 1965; the licensing procedure is set by the Planning and Building (Building Licensing) Regulations, 2016, and applications are filed online.

> A State Comptroller report measured an average of about 319 days to a permit in the second half of 2019. Use it only as a historical reference, never as a forecast for a specific committee.

- Source: <https://library.mevaker.gov.il/sites/DigitalLibrary/Pages/Reports/7098-10.aspx>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: milestone: permit
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 2. il.indexation.construction-input-index

**Statement:** Residential construction contracts and new-apartment payment schedules are commonly linked to the residential construction input index, published monthly by the Central Bureau of Statistics.

> When a claim or quote is linked, check which base month the contract names and which published index month the claim uses. The index is published around the 15th of each month for the previous month.
> The contract's own linkage clause governs; this card only says that linkage to this index is common.

- Source: <https://www.cbs.gov.il/>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: money-event: payment_claim, quote, budget_line
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 3. il.contracts.form-3210

**Statement:** Government and many public building works in Israel use the standard contract form 3210 (Conditions of contract for the construction of a building by a contractor), published by the Accountant General; public bodies often adapt it.

> Under form 3210, changes are ordered in writing as a "פקודת שינויים" and priced against the bill of quantities. Check which edition and which amendments the specific contract uses.

- Source: <https://www.online.mod.gov.il/Online2016/Documents/General/Binuy/Contract3210.pdf>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: change: variation
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 4. il.contractors.registration

**Statement:** Contractors for building engineering works must be registered with the Registrar of Contractors under the Contractors Registration Law, 1969; registration is by classification, which limits the size and type of works a contractor may take.

> Before levelling quotes, check each contractor's registration and classification against the scope and value of the works.

- Source: <https://www.gov.il/he/departments/units/contractors_registrar_and_head_of_sales_laws_moch>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: contact: contractor, subcontractor
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 5. il.sale-law.buyer-funds-secured

**Statement:** Under the Sale (Apartments) (Securing Investments of Apartment Buyers) Law, 1974, a developer may not take more than 7% of the price from a buyer of a new apartment unless the money is secured, most often by a bank guarantee.

> The threshold was lowered from 15% to 7% by Amendment 4 (2008). Other permitted securities exist (for example insurance or a registered caveat); the guarantee is the common one.
> Agents flag any buyer payment schedule that collects more than 7% before a security is recorded. A lawyer confirms.

- Source: <https://boi.org.il/media/gsdkkm1q/184f.pdf>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: requirement: covenant
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 1 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 6. il.vat.standard-rate

**Statement:** Israel's standard VAT rate is 18% from 1 January 2025 (previously 17%). The applicable rate follows the date of taxation, not the invoice date.

> Agents state the VAT treatment on every amount they check or report (included or excluded, and at which rate).
> Secondary source: a law-firm summary of the Israel Tax Authority's announcement and interpretation directive 01/2025. Confirm against the Tax Authority for transactions that straddle the change date.

- Source: <https://herzoglaw.co.il/en/news-and-insights/vat-updates-for-2025-vat-rate-increase-israel-invoices-reform-and-the-economic-plan-bill/>
- As of: 2026-10-13; review by: 2027-04-13
- Applies to: money-event: payment_claim, invoice, quote
- Current verification: 1 (drafted)

**Your review**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 2 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 7. defaults

Defaults the pack sets for every venture in this market.

- country: IL
- currency: ILS
- units: metric
- locale: he-IL
- work_week: sun, mon, tue, wed, thu

**Your review (optional row)**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 5 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 8. glossary:en

Glossary (en): each local term mapped to a core family and kind. Check that each term means what its mapping says.

- Form 4 → milestone / handover
- Sale Law guarantee → requirement / covenant
- accompanying bank → contact / lender
- construction input index → money-event (field: indexation)

**Your review (optional row)**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 4 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________

### 9. glossary:he

Glossary (he): each local term mapped to a core family and kind. Check that each term means what its mapping says.

- חשבון חלקי → money-event / payment_claim
- חשבון סופי → money-event / payment_claim
- הצעת מחיר → money-event / quote
- כתב כמויות → source / contract
- מכרז → source / contract
- פקודת שינויים → change / variation
- היתר בנייה → milestone / permit
- טופס 4 → milestone / handover
- תעודת גמר → milestone / handover
- אבן דרך → milestone / construction_stage
- ערבות בנקאית → requirement / covenant
- ערבות חוק מכר → requirement / covenant
- ליווי בנקאי → contact / lender
- מפקח → contact / supervisor
- קבלן ראשי → contact / contractor
- קבלן משנה → contact / subcontractor
- ליקוי → issue / defect
- עיכוב → issue / delay
- הצמדה למדד תשומות הבנייה → money-event (field: indexation)

**Your review (optional row)**

- Verdict: ☐ correct ☐ corrected ☐ removed
- Facts checked: 19 (our estimate; change it if you count differently)
- Facts corrected: ________
- Corrected statement: ________
- Reviewer note: ________
