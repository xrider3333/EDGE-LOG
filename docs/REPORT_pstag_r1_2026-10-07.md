# REPORT SPEC - PS-TAG r1: does the frozen point score rank the R of NOISE #304's trades? - DRAFT for MANAGER (2026-10-07)

A REPORT, not a prereg slot (MANAGER #39; docs/SCOPE_DISC_2026-10-06.md, bridge item 4). The NOISE lane signed off on
2026-10-07 (#50): "YES, as its own report", on NOISE #304's 2,797 core WF trades as the #422 anatomy tags them. Written
before any score was joined to any trade. No NOISE rule can change either way: filters and re-sizes on NOISE are closed
(ledger 2.1, 2.53). A fail retires the score as an algo input (it stays a journal aid); a pass keeps it as a LABEL on
crown signals, never a gate or a size.

## 1. Trades (the host)
- NOISE #304 = NOISE_1_0 with NOISE_1_8_CT304's `_FROZEN` (lookback 40, bands 0.75 / 1.5, VWAP exit, bandwidth stop
  k = 1.75) on the NQ 5m RTH no-adjust master (id 37), run through BALANCE r1's harness functions
  (tools/balance_r1_stageA.py `load_master`, `build_bands`, `run_304`: exact parity with NOISE422_raw_trades.csv,
  2,797 of 2,797 WF trades).
- WF = signal date 2016-07-01 .. 2025-06-29. Signal bar = the fill bar - 1 (the bar whose close decided the entry), as in
  tools/noise_r422_anatomy.py `build()`. The tool asserts that its trade set equals `build()`'s, trade by trade (signal
  bar, side, unit dollars).
- **R** = unit P&L in points after the house cost (0.533 a round trip) / the initial risk in points. The initial risk is
  #304's own protective stop distance at the fill: 1.75 x (UB - ref_hi) for a long, 1.75 x (ref_lo - LB) for a short,
  with the band at the fill bar (NOISE_1_0.py lines 628-633). It is a band width (sigma x price x 0.75 or 1.5), not the
  signal bar's own move, so no score point is in its denominator.
- Session type (NOISE's diagnostic): a SINGLE-trade session (the trend-day break held to the close; 29% of trades, 97%
  of unit dollars in the anatomy) or a MULTI-break session.

## 2. The score
- ps1.2 (tools/point_score.py, spec docs/POINT_SCORE_SPEC.md v1.2, 200 SMA default), vectorised `score_series`, NQ 1m
  ETH no-adjust master, history loaded from 2016-01-01. Read on the last 1m bar CLOSED at the NOISE signal bar's close:
  masters are start-stamped, so for a 5m signal bar starting at t that is the 1m bar starting at t + 4 min. If that 1m
  bar is absent, the latest 1m bar starting in [t, t + 4] is used; none = no score (counted).
- Side: longs read the LONG points, shorts the SHORT points.
- **Score % = hits / non-NA over the six informative points: 2, 3, 4 (1m / 5m / 30m 200 SMA), 8, 9 (largest body /
  largest volume since today's low), plus 7 for longs (above yesterday's high) or 5 for shorts (below yesterday's
  low).** Point 1 (10 seconds) has no history (NA). Points 5-6 (longs) and 6-7 (shorts) are hit by construction (the
  bands anchor at the max / min of the open and the prior close); their observed hit rates print as a check, never in
  the score. A trade with no non-NA informative point has no score (counted).

## 3. Statistic, null, pass (frozen)
- **Primary:** Spearman rho(score %, R) over the scored WF trades.
- **Null:** 1,000 shuffles of the scores across trades WITHIN each July-June WF year (keeps every year effect),
  numpy default_rng(20261005). p95 = numpy linear percentile.
- **PASS** = rho > the null's p95 AND rho has the same sign in H1 (signal date 2016-07-01 .. 2021-12-31) and H2
  (2022-01-01 .. 2025-06-29), the anatomy's halves. Detectable rho at 80% power on ~2,797 trades: about 0.05.
- **Secondary (report):** mean R of the trades scoring ABOVE the WF median score % vs AT OR BELOW it (counts printed;
  the score is discrete).

## 4. Reported, never a verdict
- Spearman within SINGLE-trade and within MULTI-break sessions, each beside its own within-year null p95 (NOISE #50: so a
  pass is not just "the score finds trend days").
- Spearman with unit dollars instead of R.
- Per point: hit rate, and mean R hit vs miss (descriptive only; no point becomes a filter).
- Per July-June year: n and rho.
- Coverage: trades scored; NA counts by point and reason.

## 5. Order and files
- `python tools/pstag_r1.py --power`: the trade-set parity with `build()`, coverage, constant-point check, and the
  null's p95 (shuffles only) - no real rho prints.
- `python tools/pstag_r1.py`: the read. Output C:\EdgeLog\_anatomy_cache\pstag_r1\ (trades_scored.csv, null.json,
  report.txt); a copy of the report in tools/r37_results/pstag_r1.txt.
- Then: a RESEARCH_LEDGER row and the lane note. No RUNBOARD row (a report on a crown's trades, no P&L of its own).

## AMENDMENT 0 - the `--power` output (2026-10-07, before the read; no rule changed)
- Trades: 2,797 WF, equal to the #422 anatomy's `build()` trade for trade. R parity: the 110 stopped trades sit exactly
  1.75 x the band width from their fill (max difference 1.8e-12 points). Risk: median 62.5 points (5%-95%: 14.9 .. 203.3).
  Single-trade sessions: 799 trades (29%), 97% of unit dollars - the anatomy's figures.
- Scores: all 2,797 read on the 1m bar at the signal start + 4 min. 108 trades follow an incomplete prior session, so
  points 5-7 are NA there ("prior session incomplete") and they score on 5 informative points; 2,689 score on 6. The
  constant points hit 100% (longs 5-6, shorts 6-7). The score is heaped: 0.667 (1,271 trades), 0.5 (889), 0.333 (393).
- Null p95 (1,000 within-year shuffles): all +0.0292 (sd 0.0196); single-trade sessions +0.0642; multi-break +0.0315.

## RESULTS - the read (2026-10-07 19:35 MST, after the 60-minute window on MANAGER #556): PASS, a small one
Log: `tools/r37_results/pstag_r1.txt` (the `--power` log: `pstag_r1_power.txt`). The null was recomputed and matched
`--power`'s null.json.
- **Primary:** Spearman(score %, R) = **+0.053** against the null p95 of +0.029 (n 2,797).
  - Halves: H1 (2016-07 .. 2021-12) +0.053; H2 (2022-01 .. 2025-06) +0.046. Same sign, so it PASSES.
- **Secondary:** trades scoring above the WF median (0.5) average R +0.125 (n 1,389); those at or below it average
  +0.021 (n 1,408).
- **NOISE's diagnostic (#50):**
  - Single-trade sessions: +0.052 vs their null p95 of +0.064 (n 799), not above it.
  - Multi-break sessions: +0.038 vs +0.032 (n 1,998), above it.
  - So the score is not only finding trend days, but the margin is thin.
- **Per July-June year:** 7 of 9 rho are positive. The best are 2017 (+0.156) and 2021 (+0.172); the worst are 2019
  (-0.003) and 2022 (-0.009).
- **Which points carry it (descriptive):** the trend points.
  - Longs above the 30m 200 SMA average R +0.095 vs -0.022 below it; longs above yesterday's high +0.107 vs -0.003.
  - Shorts below the 1m 200 SMA average +0.103 vs -0.017.
  - The points new to the house, 8-9 (largest body / volume since today's low), fire on only 2-3% of NOISE trades and
    carry nothing here.
- **What it means:**
  - The size is small: rho 0.05 explains well under 1% of the rank variance in R, right at the ~0.05 detectable line.
  - It mostly restates trend alignment, which NOISE round 47 already read (the 200-bar mean, "no candidate") and the
    #422 anatomy tagged (side x 200-day state).
  - It changes no NOISE rule: filters and re-sizes on NOISE stay closed.
  - It keeps ps1.2 as a LABEL stamped on crown signals and CBU alerts (bridge item 1). It is never a gate or a size.
