# RESULTS - TRENDSIZE r1 Stage A (Custom ML, 2026-10-14): DEAD

Prereg docs/PREREG_trendsize_r1_2026-10-14.md (witness prereg/custom-ml-trendsize @ dcceb58f; LF sha256 prereg
49f4a3fc..., harness 3587f244..., checked at start). Walk-forward only (2016-07-01..2025-06-29); the tilted book's
lockbox was never computed. Log: C:\EdgeLog\custom_ml\trendsize_r1_stageA.log.

| WF | ROC @ $30k | DD5 | DD % from peak | Sortino |
|---|---|---|---|---|
| #463 plain | 93.81 | $36,095 | 13.1% | 3.816 |
| #463 + ORB trend-day tilt | 66.39 | $41,771 (1 episode) | 18.5% | 3.756 |

- **Bar 1, book lift: FAIL.** ROC 66.4 against a bar of 98.5, and Sortino lower.
- **Bar 2, chance: FAIL.** The real tilt is worse than 99.5% of 1,000 within-year shuffles of the same day count (shuffle p95 109.7).
- **Bar 3, flat leverage: FAIL.** Flat leverage at the same mean size (1.042x) gives 93.3.
- **Bar 4, years: FAIL.** The ORB leg's tilted-minus-plain dollars are positive in 5 of 9 July-June years.
- **Bar 5: PASS** on both parts. Without Feb-Apr 2020 the tilt is ahead (105.5 vs 96.6), and the top day is 43% of the gain.
- **Why it dies:**
  - The rule ADDS money (+$81.5k on the ORB leg) but puts its 2x on high-range runs, and the worst one is the 2020 crash.
  - There, ORB's losses doubled and set a new, single-episode book drawdown. The ORB leg on its own goes from WF ROC 34.5 to 20.9.
  - This is the caveat the power check named: a real range score's misses are wide LOSING days, which a synthetic trend-day score cannot copy.
  - The power check gave the synthetic score a 43% chance; the real score is anti-skilled at the drawdown level.
- **Closed.** No re-tune of the 80th percentile, the 2.0 / 0.75 sizes or the windows. Range-state size-ups on ORB join the quiet-tape filter as drawdown questions, not edges.
- **Book looks:** one book look used (posted to MANAGER #1010).
