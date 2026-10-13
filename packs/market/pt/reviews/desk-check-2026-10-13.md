# Agent desk check: Portugal market pack (pt@0.1.0)

**Agent desk check — not a professional review.** An AI agent opened each card's cited source on 2026-10-13 and compared it with the card. It did not change any card or any verification level. Nothing here counts toward the STORY-45 pass signal or raises a level; only a named Portuguese professional's review does (see `docs/reviewing-a-market-pack.md`). Use this as a list of things for the reviewer to look at first.

Mechanical check (`python cli.py packs desk-check pt`): 0 errors, 0 warnings, and 5 notes for cards whose body says the source is secondary (press, opinion or a summary). Every card has an https source, an as-of date, a review-by date that has not passed, a statement and a valid `applies_to`.

## Headline

| Result | Cards |
|---|---|
| Source supports the card | 1 |
| Doubtful: the source supports part of the card, or contradicts it | 5 |
| Source unreachable by the agent (blocked or rendered by script) | 4 |

## Cards

### pt.contracts.complementary-works: doubtful

- Source: ECO / Advocatus opinion article by Nelma Pires (Miranda & Associados), 27 May 2024. Secondary, as the card says.
- Supported: the definition in Article 370(1) of the Public Contracts Code (works of a kind or quantity not in the contract, whose performance is needed to carry it out).
- Not in the source: that the owner approves them "usually by an addendum". The article mentions addenda only as documents sent to the Court of Auditors.
- Not in the source: the card body's claim that the Court of Auditors ruled complementary works cannot be offset against works not done.
- Worth adding if correct: the source gives a cumulative cap of 50% of the initial contract price and cumulative conditions in Article 370(2).

### pt.contractors.alvara: unreachable

- Source: Diário da República page for Lei 41/2015. The page is rendered by script and returned no text to the agent.
- For the reviewer: confirm that IMPIC issues the alvará under Lei 41/2015, that the class caps the value of works, and which portaria currently sets the class thresholds (the card body names Portaria 212/2022 from secondary sources).

### pt.sales.energy-certificate: unreachable

- Source: idealista news article. The site refused the agent's request (HTTP 403).
- For the reviewer: confirm the requirement under Decree-Law 101-D/2020, the exemptions, and that certificates are issued by experts registered with ADENE.

### pt.taxes.imt-current-table: doubtful

- Source: Portal das Finanças, "Compra da casa" (official).
- Supported: "A liquidação de IMT é válida por dois anos, ainda que tenham ocorrido alterações de taxa."
- Not in the source: that IMT rates and brackets are updated every year. The page links practical tables in Ofício-Circulado 40129 of 2026-01-06 but does not say the tables change yearly.

### pt.sales.permit-statement: unreachable (corroborated elsewhere)

- Source: idealista news article. The site refused the agent's request (HTTP 403).
- Corroboration: the Cuatrecasas guide cited by two other cards says the "real estate transaction regime now requires an express statement on whether a permit exists, failing which the transaction may be annulled". It says "a permit", not specifically a use permit.

### pt.contracts.price-revision: unreachable

- Source: Diário da República consolidated text of Decree-Law 6/2004. The page is rendered by script and returned no text to the agent.
- For the reviewer: confirm the amendments (the card says the last was in 2021), Article 5 on the method and formula, Article 382 of the Public Contracts Code, and the base month.

### pt.planning.technicians-responsibility: doubtful

- Source: Cuatrecasas practical guide to Simplex Urbanístico 2.0 (Nuno Sá Carvalho and Hugo Nunes, 7 September 2026). Law-firm summary.
- Supported: "Developers and professionals assume greater responsibility for ensuring that projects comply with the applicable rules"; statements of responsibility "are now differentiated, particularly for use".
- Not in the source: that municipalities control more after the fact. The guide only says the control period for prior communications fell from 10 years to 1 year.

### pt.planning.simplex-2: doubtful (likely wrong date)

- Source: the same Cuatrecasas guide.
- Contradicted: the card says Decree-Law 108/2026 entered into force on 3 August 2026. The guide says Decree-Law 155-B/2026 of 31 July "postponed the entry into force of the main provisions from August 3 to October 1, 2026". It also mentions Declaration of Rectification 29-A/2026/1.
- Not in the source: the publication date (29 May 2026), and the card body's transitional rule for pending files.
- Partly supported: "reduces prior control and shortens procedures". The guide speaks of restructured licensing periods and procedural speed.

### pt.taxes.stamp-duty-on-purchase: supported

- Source: Portal das Finanças, "Compra da casa" (official).
- Supported: "O Imposto do Selo tem uma taxa fixa de 0,8%, aplicada sobre o mesmo valor base do IMT."
- Supported with a nuance: the IMT declaration is filed before the deed, and "No dia da escritura, é obrigatório apresentar os comprovativos de pagamento do IMT e do IS". Payment is due on the day of the assessment or within 30 days, so in practice both are paid by the deed.

### pt.vat.rates: doubtful

- Source: Tax Authority binding ruling (ficha doutrinária), process 29545, decided 2026-02-28 (official).
- Supported: the reduced rate under List I, item 2.23 for building rehabilitation contracts in urban rehabilitation areas, in the wording of Lei 56/2023 of 6 October.
- Not in the source: the 23% standard rate, and the Supreme Administrative Court's uniformizing ruling 3/2026. The 6% figure appears only in the taxpayer's request.
- Possible conflict: point 17 of the ruling says the current wording of item 2.23 no longer depends on an approved urban rehabilitation operation (Decree-Law 307/2009). The card body says ruling 3/2026 "may require an approved urban rehabilitation operation". The reviewer should check which wording and which period ruling 3/2026 concerns.

## Not checked

The glossary (`glossary/pt.yaml`, `glossary/en.yaml`) and the defaults have no cited sources; they are on the review sheet as optional rows.
