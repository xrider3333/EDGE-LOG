# SCOPE r2 - STRATEGY-BEATING lane: what is left in the stock EVENT space (2026-10-08)

DRAFT for MANAGER review (inbox #689: the lane's queue is empty). Nothing in it runs before MANAGER's GO. Written after
every verdict below is on the ledger or queued to it; no new number is computed for this note.

## Where the lane stands

The 10-05 scope ([SCOPE_STRATEGY-BEATING_2026-10-05.md](SCOPE_STRATEGY-BEATING_2026-10-05.md)) ranked 17 mechanisms. Eight
ran; all eight are dead as standalone legs, and none adds to the book line L = #463 + 0.264 x RES (S1: WF ROC @ $30k
121.06 / DD5 $34,392, $147,395 a year). The rest are spent or out of this lane:

| Family | Prior written before data ($ a year at $200k a side) | Best cell, WF ROC @ $30k | Book add over L (A2 at c) |
|---|---|---|---|
| DIVRUN r1 (2.77) | ~$8,400 (ROC 8-13) | 3.5 | - |
| EDRIFT r1 (2.85) | - | -2.3 (S1 -2.2) | - |
| NEWISSUE r1 (2.87) | - | -1.7 | 96.7 / 100.7 (vs 120.82) |
| NETISS r1 (S1, ticket 160) | ~$6,000 (ROC 5-9) | 7.7, driven by one episode | 108.9 / 111.4 |
| SHORTINT r1 (S1, ticket 160) | ~$6,000-12,000 (ROC 5-15) | -0.4 | - |
| EAP r1 (2.103) | ~$4,000-10,000 (ROC 3-15) | -0.3 | 120.30 / 110.94 |
| BUYBACK r1 (2.104) | ~$4,000-8,000 (ROC 4-8) | 1.1 | 97.95 / 103.88 |
| INSIDER r1 (2.78; TV's run, this lane reviewed) | - | 1.9 | - |

Out of this lane or spent: EDRIFT r2 (the earnings family is closed, MANAGER #84); SEASON, 52WH, IVOL, BAB, QUALITY
(FRONTIER's; SEASON and HIGH52 dead 10-08); RESREV (FRONTIER's RREV, cost-map check first); learned XBRL models (Custom ML).

## What the record says

1. **The large-cap basket tests were underpowered from the start.** FRONTIER's power line for the shared r17 engine
   (10-08): a 50-a-side, $4,000-a-name basket needs a true edge of about **$17,500 a year for a 50% chance** of clearing
   ROC 15, and about $23,000 for 80%. Every prior this lane wrote before its data was **$4,000-12,000 a year**, so each test
   could pass only if the 2016-25 effect was 2-4 times the published one. None was; most came in at or below the prior.
2. **The seat route fails the same way every time.** Four short-growth baskets (NETISS, SHORTINT, NEWISSUE, BUYBACK) earned
   inside L's drawdowns (BUYBACK P: +$298,632 over 45 episodes, DO +0.337 against a null p95 of +0.031) and lost more in the
   2019-21 growth rally, so L + c x cell fell below L at every size. MANAGER's 10-06 lesson stands: this is drawdown
   insurance, and its premium is a new worst drawdown.
3. **Among the 500 largest names, the cross-sectional spreads are close to zero after costs.** EAP's two sides made
   +$251,510 and -$256,321; BUYBACK's +$230,469 and -$215,149. Both sides rode the market, and the spread did not cover
   5 bps a side.

## Candidates for r2, each placed on the power line and the drawdown sign

- **DIVCHG r1 v2 (owed: the 10-07 review said NO to v1 and asked for 17 edits).** The draft's own map gives ROC 2-10. The
  review's power estimate needs an 8-10% a year spread where the large-cap literature gives 1-3%. Long growers / short
  cutters and freezers is long quality-momentum / short value: it should LOSE in growth sell-offs, which is the wrong sign
  for #463's drawdown weeks. **Recommend: close at draft (one ledger line), no v2.**
- **The same families in mid-caps (dollar-volume ranks 501-1500).** The data is held: the cache carries 5,367 symbols, the
  XBRL facts 4,311 CIKs. The anomalies with the biggest small-cap premia are issuance, short interest and new listings,
  which is the short-growth corner MANAGER closed. The non-growth one (payout) showed no spread at the top 500. Costs rise
  to 15-25 bps a side. **Recommend: do not draft.**
- **Thin event families: SPINOFF, Nasdaq-100 adds and deletes, split ex-dates.** On the pinned calendar there are about 7
  spin-off / stock-dividend ex-dates a year on universe names, about 10 index changes and a few dozen splits. At $4,000 a
  name and a 5% abnormal return, 30 events a year is about $6,000 gross, a third of the MDE. **Recommend: park (power fails
  by count).**
- **MERGER-ARB.** It needs deal terms from 8-K / DEFM14A (TV's 8-K space). Deal breaks cluster in sell-offs, the wrong
  drawdown sign (Mitchell & Pulvino 2001). **Recommend: park.**
- **A longer history: a data question, not a family.** Prices in the cache start 2016-01-04; XBRL facts reach back to 2009.
  Seven more years of daily prices INCLUDING delisted names (point-in-time, no survivorship) would cut every basket's MDE by
  about a quarter (more months: $17.5k -> ~$13k). This lane knows no free source with delisted names and never pulls data
  itself, so this goes to MANAGER and the owner. **Flag only.**

## A process proposal: the power-first gate (house-wide, for basket families)

Before any Stage A, the dryload prints the prior written before data ($ a year at the registered size) beside the engine's
MDE from its null alone (the 50% and 80% lines). If the prior is below the 50% line AND the draft has no seat case that
survives the 2019-21 bleed test, the family closes at draft with one ledger line, without a Stage A. MANAGER already did
this for RREV (the cost-map check). In this lane's record every priced prior sat below the 50% line; what kept the
families alive was the seat case, and four of those seat cases then died on the 2019-21 bleed. Whether FRONTIER's QUALITY r1 takes it is FRONTIER's and MANAGER's call.

## Recommendation for this lane (MANAGER decides)

1. Close DIVCHG at draft; adopt the power-first gate for basket families.
2. Draft no new stock-basket family on 2016-25 data. The stock vein reopens only with more history (see the flag above).
3. Lane work from here: the RESMOM forward line (first live rank 10-30, harm monitors only, NOTE 2 shipped), cross-lane leak
   and power reviews on request (FRONTIER QUALITY r1, Custom ML's DISTRESS-ML / FUND-ML seats, NOISE), and anything
   MANAGER assigns.
