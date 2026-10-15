# Reading shelf #29 - "Price Drift Before U.S. Macroeconomic News" (Kurov, Sancetta, Strasser, Wolfe 2019, JFQA 54(1)) - TV, 2026-10-15

**Verdict: CLOSE at draft (MAPCHECK-F own-ROC rule on the realistic prior). No backtest, no data read.**

## The paper (RePEc abstract page, read 10-15; the PDF was not downloaded - a download needs the owner's own yes in this session)
- 30 US macro releases; 9 of the 20 that move markets show informed trading: E-mini and Treasury futures start drifting the
  "correct" way about 30 minutes before the release, about 40% of the total price adjustment.
- The abstract does not name the nine releases or state the sample period, so the trade below assumes the 10:00 ET releases the
  literature usually lists (ISM, Conference Board confidence, home sales). We hold no historical 10:00 release calendar (data need).

## The trade the map check priced
At 09:55 ET follow the NQ move since 09:30 into the release, exit 10:05, on the ~9 drift releases a month (~108 trades a year).
Per-trade edge guess ~1.5 pt on a ~15 pt move, minus the 0.706 cost -> per-trade Sharpe ~0.05 x sqrt(108) = ~0.52 a year as
published. Halved for post-publication decay AND because the leak story rests on early data access that ended around 2013-14 (TV's
reading, not the abstract's) -> 0.26 +- 0.25.

## MAPCHECK-F (tools/tv_mapcheck_shelf29.py imports tools/mapcheck_f.py unchanged; 2,000 synthetic legs; WF only)
| prior | yearly Sharpe | own WF ROC@30k median | P(own >= 15) | P(book lift, #463 WF) | verdict |
|---|---|---|---|---|---|
| realistic (decayed) | 0.26 +- 0.25 | +2.5 | 7% | 18% | CLOSE at draft |
| as published (upper bound) | 0.52 +- 0.25 | +6.4 | 19% | 34% | clears, barely |

Four numbers: - (a map check, no curve). Re-open only with a dated 10:00-release calendar (names + times, 2016-2026) and evidence the
drift survived 2014; the 08:30 side is already covered (MACRO830 dead, EVENT SLEEVE part C forward).
