# Reviewing a market pack

This page is for the lawyer, engineer, surveyor or accountant who has been asked to check a RealizeOS market pack. It takes about an hour.

## What you are checking

RealizeOS helps property developers, architects and construction teams with their paperwork: payment claims, changes, permits and contracts. For each country it uses a **market pack**: a short set of local facts such as tax rates, contract rules, permits and licences.

An AI agent drafted this pack from public sources. Each fact is written as a **card**. Until a professional checks it, every answer that uses a card says it is an unverified draft (verification level 1). Your review is what lets the cards be marked as reviewed (level 2), with your name on them.

## What a card looks like

| Part | What it is |
|---|---|
| Statement | The fact, in one or two sentences. This is what you check. |
| Details | How the system uses the fact, and any caveats. |
| Source | The link the agent drafted from. |
| As of / review by | When it was drafted, and when it must be checked again. |
| Applies to | The kind of record it is used for, such as a payment claim, a change or a permit. |

## What to check on each card

1. Is the statement correct and current in this country?
2. Does the source support it? If there is a better or official source, note it.
3. Is anything important missing, misleading or out of date?

You are not asked to give advice on a particular project, or to say whether the pack covers everything. The pack already says it does not replace a professional.

## How to fill in the sheet

You will receive two files: `review-sheet.csv` (a spreadsheet to fill in) and `review-sheet.md` (the same cards, for printing). Use whichever suits you; if you write on the printout, the person who sent it will type your answers in.

**Opening the spreadsheet.** Excel and Google Sheets both open it. If Excel shows everything in one column, open Excel first, then use Data > From Text/CSV and pick the file. In Google Sheets use File > Import > Upload, with the separator set to "Detect automatically".

**Fill in these columns for every card:**

| Column | What to write |
|---|---|
| `verdict` | `correct`, `corrected` or `removed` (in English, as written here). |
| `facts_corrected` | How many separate facts you changed: 0 if correct. |
| `corrected_statement` | Your wording, if you corrected the card. |
| `reviewer_note` | Anything else: a better source, an exception, why you removed it. |

**Verdicts:**

- `correct`: the statement is right as written. Leave `facts_corrected` empty or 0.
- `corrected`: something was wrong. Write how many facts you fixed and your corrected statement (or explain in the note).
- `removed`: the card should not exist (wrong beyond repair, or not relevant). A short note helps.

**Counting facts.** A fact is one separate claim: a rate, a date, a deadline, a threshold, a law or article number, or a named authority. The column `facts_checked` is our estimate of how many facts the statement makes; change it if you count differently. For example, "Stamp duty of 0.8% applies to property purchases, on the same base as IMT; both are paid before the deed" makes two or three facts. If the rate were wrong, `facts_corrected` is 1.

**Optional rows.** The last rows cover the pack's defaults (currency, units, work week) and its glossary (local terms and what they mean). Check them if you can; leave them empty if not.

Please don't change the `id` column or the column names.

**Saving.** In Excel use File > Save As > "CSV UTF-8 (Comma delimited)", so Greek, Hebrew and accented letters survive. In Google Sheets use File > Download > Comma-separated values. Send the file back to the person who asked you.

## How long it takes

About five minutes per card. The printable sheet gives an estimate at the top: about an hour for ten cards plus the optional rows.

## What happens after

1. The person who sent the sheet records it in RealizeOS. Your name, title and registration number, the date, your verdict on each card and the number of facts you corrected are stored in a review record inside the pack.
2. Your corrected statements are written into the cards, and removed cards are taken out.
3. The owner approves the change in RealizeOS. Nothing is marked as reviewed before that approval.
4. The cards you reviewed then show level 2 ("reviewed"), with your name and the date. Each card drops back to level 1 on its review-by date unless someone reviews it again.

We also count how many drafted facts needed correcting. That number measures how well the agent drafted the pack, not your work.

## Your name on the cards

Your name, title and registration number are recorded in the pack's review record, a plain file that ships with the pack, so anyone who has the pack can read it. When the owner approves the review, your name is also recorded with each card you reviewed in that RealizeOS installation, and is shown with the card's level. If you'd rather not be named, say so before you start: a card can only be raised to "reviewed" with a named reviewer.
