# RESULTS - PMFAIL r1 and RUNNER2 r1, Stage A (2026-10-07): both FAIL - dead, no variants

Preregs: docs/PREREG_pmfail_r1_2026-10-06.md and docs/PREREG_runner2_r1_2026-10-06.md, as amended by AMENDMENT 0 and
AMENDMENT 1. The results sit in this separate file because both harnesses pin the prereg text by hash. Walk-forward only
(2016-07-01 .. 2025-06-29); the lockbox was never read. Harnesses: tools/pmfail_r1_stageA.py and
tools/disc_runner2_r1_stageA.py (worktree commit b860f6cc). Logs: tools/r37_results/pmfail_r1_stageA_*.txt and
runner2_r1_stageA_*.txt. Outputs: C:\EdgeLog\_anatomy_cache\disc_pmfail_r1\ and disc_runner2_r1\.

## Order of work (all before any real direction)
1. **Photograph:** manifest bac11716, 10,020 files, 0 mismatches. The FB/META probe ran AFTER the pull (AMENDMENT 1), and
   all 4 endpoints returned SAME MAPPING (log 54d73395, 01:29Z).
2. **TTM's leak review:** NO LEAK on both harnesses (inbox #55 / #56). TTM's one note is now a report: halted-into-close
   exits priced as a split. It touches 0 trades in either leg (1 halted-close trade each, neither priced as a split).
3. **Counts:** PMFAIL 914 fills (101.6 a year; no year under 25). RUNNER2 791 fills (88.0 a year; 2016-17 thin at 20).
   Both pass the count gate. RUNNER2 loses 774 of its 1,757 events to the short-sale-rule skip. Premarket thinness on
   PMFAIL event days (premarket volume under 10% of the day's) falls from 92% in 2016-17 to 34% in 2024-25.
4. **Power** (coin-flip sides, the book-add lead needed at the vol scale, 5% / 80%): PMFAIL 15.8 / 23.8; RUNNER2 20.2 /
   30.5.
5. **Four-cell family null:** 500 draws a leg, null.json da1472a0. The p95 of the 4-cell max: ROC@$30k 3.95, t 1.14,
   R-day sum $32,491.

## Verdicts (judged cells at N*, reading L, base cost)
- **PMFAIL r1 primary: FAIL.**
  - 914 trades; net -$2,926; PF 0.99; own ROC@$30k -0.30.
  - Worst DD $32,989; DD5 $8,435. Driven by one episode: the worst DD is 3.9 x DD5.
  - t -0.14; R-day sum $15,100 (null p95 $32,491); 3 of 9 years positive.
  - N* = $5,000, the grid floor: even the smallest size draws $33k.
  - Neighbour: -$7,835. Fails every return bar; passes the count bar only.
- **RUNNER2 r1 P: FAIL.**
  - 791 trades; net -$40,261; PF 0.81; own ROC@$30k -2.40.
  - Worst DD $56,031; DD5 $13,616. Driven by one episode: the worst DD is 4.1 x DD5.
  - t -2.14; R-day sum -$9,376; 3 of 9 years positive.
  - N* = $5,000. Neighbour W: -$58,838.
  - Fails all bars except the count bar.

## What it teaches (reports, never bars)
- **PMFAIL's gross edge is real, and the borrow eats it.** Gross is +$70,174 at $5k a trade. Spreads cost $27,389 and
  the 1%-a-day locate charge $45,710. Break-even locate is about 0.9-1.0% a day, and break-even spread is 77 bps a side at 0%
  locate.
  - The 2016-21 half nets +$15,119; 2022-25 nets -$18,044.
  - The low-float (< 20M shares) subset nets +$35,989 (PF 1.42, t 2.44), but it is one subset among many and is never
    a bar.
- **The open print beats the failed-high signal, and still not by enough.** OPENPRINT (short the 09:30 print on every
  event day, a report): 2,591 trades, +$97,660, PF 1.11, ROC 3.65, which sits under the null p95 of 3.95. PMBREAK (long
  the premarket-high break): -$45,346.
- **RUNNER2: day 2 of a runner does not fade after costs.** Gross is +$23,165, against costs of $23,856 and locate of
  $39,570.
  - 2016-21 nets +$673; 2022-25 nets -$40,934 (t -3.10).
  - OPEN2 (short the day-2 open, a report): +$27,199, PF 1.07, but -$76,945 at stress cost.
- **Book add:** neither leg lifts #463 or L at any size.

## Consequences
- Both legs are DEAD: no variants, no re-cut by float, locate or period. The small-cap gapper habitat closes for this
  lane: three shots (PMFAIL, RUNNER2, and the OPENPRINT / OPEN2 reports) all sit inside the null after costs.
- Ledger rows "PMFAIL r1" and "RUNNER2 r1" (RESEARCH_LEDGER.md); RUNBOARD research rows PMFAIL-R1 and RUNNER2-R1 (family MISC).
- One thing for the owner's own trading (a report, not a rule): the gross short edge on failed premarket highs is
  roughly 1% of notional a trade, so it pays only when borrow costs well under 1% a day.
