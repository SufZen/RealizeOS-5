# Comparing Contractor Quotes

## Level against the bill of quantities (BoQ)
Map every quote line to a BoQ item. Normalise units and quantities. One table: rows are BoQ
items, columns are bidders.

## Flag
- **Missing:** BoQ item with no price → a gap, never filled with an average
- **Excluded or qualified:** "not included", "by others", "subject to"
- **Provisional sums and allowances:** amounts that will change
- **Scope differences:** a bidder pricing something different from the BoQ
- **Validity and payment terms** that differ from the tender

## Output
Levelled totals per bidder, the gaps per bidder, and the clarification questions to send (drafts;
the developer sends them). The cheapest total is only comparable once the gaps are priced.
