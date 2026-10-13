# Drafting a market pack

A market pack gives RealizeOS the local language, money rules, permits, contract forms and duties of one country or region. An agent can draft one in under a day. A local professional then reviews it before anyone treats it as more than a draft. See [packs.md](packs.md) for the format and [ADR 0005](adr/0005-core-language-and-packs.md) for why.

## 1. Draft (verification level 1)

Use any capable agent (Claude, ChatGPT or another) with web search. Give it this brief, replacing the parts in angle brackets:

> Draft a RealizeOS market pack for **<country>** for the **<profession>** profession, following `docs/packs.md`.
> 1. `pack.yaml` with id, `kind: market`, version `0.1.0`, languages, defaults (country, currency, units, locale, work week), `verification.level: 1`, and a `limits` list that names what it does not replace.
> 2. A glossary per language that maps 15 to 25 local professional terms to core families: payment claims, quotes, changes and variations, permits, handover, contracts, the parties, defects.
> 3. 10 to 20 rule cards on VAT and other taxes on works, indexation or price revision, change rules, contractor licensing, permits and approvals, sale and disclosure duties, and energy certificates. Each card needs one statement, an `applies_to` family and kinds, a `source` URL (official where possible; say so in the body when it is secondary), `as_of` set to today, `review_by` six months ahead, and `verification: 1`.
> 4. A README that states the level, what is missing, and who could review it.
>
> Never state a rate, threshold or deadline without a source. If sources disagree, say so in the card body.

Put the result in `packs/market/<id>/`. Then:

- run `pytest tests/test_market_pack_pt.py` as a model for a smoke test, or copy it for the new market;
- confirm the pack loads with no warnings: `python -c "from realize_core.packs import discover_packs; print(discover_packs()[('market', '<id>')].warnings)"`;
- confirm no core code was needed. If it was, stop and reopen ADR 0005.

## 2. Review (level 2)

A named local professional (lawyer, solicitor, engineer, quantity surveyor or accountant, depending on the card) reviews each card. For every card, record:

- whether it is correct as drafted, corrected or removed;
- the number of facts corrected (the STORY-45 pass signal is fewer than 1 in 5 facts corrected across the pack).

Then request the level change. It goes into the approval queue like any held action:

```python
from realize_core.packs.verify import request_verification

request_verification(
    "<venture used for maintenance>",
    kind="market", pack_id="pt", level=2,
    reviewer="Name Surname, advogada (OA 12345)",
    corrections={"pt.vat.rates": 1},
)
```

When the owner approves it, the reviewer and date are written to `pack.yaml` and to every reviewed card. Pass `cards=[...]` to verify only some cards; the pack's own level then stays as it was.

## 3. Maintain (level 3)

Level 3 needs a partner with a signed maintenance agreement (`partner_agreement="..."`). The partner owns updates and every card's `review_by` date. A card whose review date passes drops back to level 1 automatically.

## 4. Field-proven (level 4)

Level 4 is never requested. It comes from a paid engagement that used the pack and produced a value-report number.
