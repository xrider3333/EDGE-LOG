# Test 240 part B: days ORB #314 and NOISE #382 BOTH gave back > 50% of MFE (2026-10-31, descriptive)

Owner (MANAGER #132): "list the days ORB and NOISE both gave back > 50% of MFE and what the tape did late day - I think the
same-day giveback is a tell." Tool: `tools/orb_t240_both_giveback.py`. Trades: both WF chains as test 238 rebuilt them,
NQ 5m RTH, 2022-01-01 .. 2025-07-15. The lockbox is never loaded. Not a test and not a verdict: no prereg, no rule changes.

Giveback > 50% = MFE > 0 and (MFE - final) / MFE > 0.5, final = raw points before cost (an ORB trade stopped at breakeven
counts as 100%). A "both" day = each leg had at least one such trade that session.

## Headline
- Both legs traded on **287** days; on **171 (60%)** both gave back more than half their MFE. If the two legs gave back
  independently the rate would be 52% (ORB 62% x NOISE 84% of shared days), so they coincide a little more than chance.
- They are mostly the SAME bet: on 85% of those days both legs were on the same side. A shared giveback day is largely one
  market move counted twice, not two independent signals.
- By year: 2022 40, 2023 53, 2024 59, 2025 (to 07-15) 19.

## What the tape did late on those days (medians, NQ 5m)
| Trait | Both-giveback days (171) | Other both-traded days (116) |
|---|---|---|
| Last hour return, in ORB's direction | -0.04% | +0.10% |
| Close vs session VWAP, in ORB's direction (x day range) | -0.10 | +0.30 |
| Close location in the day's range (0 = low, 1 = high) | 0.56 | 0.80 |
| Last-hour range, share of the day's range | 35% | 25% |
| Day range vs prior 20-day mean | 1.00x | 1.22x |

Plain words: on the giveback days the late session turned against the trades, the close finished back near (or through)
VWAP instead of stretched away from it, and the last hour was busier. On the other days the move kept going into the close
and the day was wider than normal.

## Is it a tell? Not shown
- **Circular.** A giveback IS price coming back against the trade, so "the last hour went against us and the close came back
  to VWAP" is close to the definition of the day, measured after the fact. Nothing here was knowable when a stop could still
  have been moved.
- **What a tell would need:** a trait measured BEFORE the giveback (for example at 14:00: price vs VWAP, the second leg
  already giving back, the morning range vs normal) that changes what happens next. That is a prereg'd test with a held-out
  stretch, not this list. Tests 238 and 239 already found no exit rule that profits from the giveback on ORB or NOISE.
- **Small n, one market:** 171 days, both legs on NQ, mostly the same direction. The 60% vs 52% co-occurrence is about what
  two correlated intraday legs on one index should show.

## Files
`C:\EdgeLog\_anatomy_cache\t240_both_orb\both_days.csv` (every day: each leg's side, MFE, final, giveback, giveback %,
and the five late-day traits) and `traits.csv` (the table above).
