# PRE-REGISTRATION - VRPES r1: does a high variance risk premium time ES month by month? (TTM scope rank 5, opened by MANAGER 2026-10-07)

Drafted 2026-10-07 evening by the TTM lane BEFORE any real-direction number exists. DRAFT for MANAGER's ADVERSARIAL REVIEW;
no Stage A before that review and a GO.
- Computed so far: the photograph check, the month schedule and COUNTS, and the power line from a coin-flip side. None of
  these involves a direction.
- Harness: `tools/vrpes_r1_stageA.py` (`--counts`, `--power`). It reuses HALFHOUR r1's book and power-line code.

## THE PRIOR, written down first: LOW
- Scope prior (SCOPE_TTM rank 5): ROC 0..12 at $30k, median 5, P(>= 15) 5%.
- **Count-bound by construction:** 41 in-months in the walk-forward (4.6 a year) against the 100-trade bar. The best possible
  outcome is a RESEARCH ROW, never a pass.
- **Power is poor:** the minimum detectable book-add lead is 19.0 points (below).
- **The schedule is long ES through the Covid crash:** February and March 2020 are both in-months, because VIX was high
  against the realized variance of the month before. The no-2020 bar and the drawdown will bind first.
- It runs because it is cheap and closes the last mapped long-horizon volatility idea, not because it is likely.

## Mechanism (theory and literature)
- The variance risk premium (VRP) is implied variance minus realized variance. Investors pay it to insure against
  variance, so it is high when risk aversion is high.
- A high VRP forecasts higher equity returns over the next one to three months, beyond the price-dividend ratio and other
  standard predictors (Bollerslev, Tauchen & Zhou 2009 RFS; Bekaert & Hoerova 2014 JoE; Drechsler & Yaron 2011 RFS).
- Those results are in-sample regressions with full-sample estimates. This test uses a trailing rank only.

## What is different (one line), and the dead families it is not
**This trades equity DIRECTION from the LEVEL of the variance premium. No house row has used VIX^2 minus realized variance.**

Dead and not re-tested:
- VOLCARRY (2.39): shorted VIX futures, i.e. harvested the premium itself.
- Q12 LONGVOL / Q13 HAVEN / Q15 STEEPENER (2.59, 2.64): VIX term-structure STATE as a seat.
- Vol-managed exposure (round 62 V / V2, RISK r1): sizes by realized vol, without implied vol.
- IMPLIEDMOVE r1 (2.89), VVIXTAIL r1 (2.92), SKEWREAL r1 (2.91).

## Rules (frozen)
**Data.**
- VIX: the 2026-10-05 CBOE photograph `C:\EdgeLog\_research_cache\public_series\cboe\VIX_History.csv` (sha256
  6edc3e39...), re-hashed against public_series_provenance.json; the run aborts on a mismatch. Rows after 2025-06-29 are
  dropped on read.
- Realized variance: the ES 5m RTH NO-ADJUST master (id 33). Only intra-session returns are used, so the no-adjust prices
  are exact.
- The position: the ES 30m RTH roll-corrected (ADJ) master (id 61). It is held for a month across rolls, and the additive
  shift leaves every point difference exact.
- Everything loaded 2010-06-07 .. 2025-06-29. Full 78-bar sessions only for realized variance; the ES holes (2020-02-28,
  2020-06-30) are skipped there.

**Signal.**
- RV(d) = the sum of squared 5m log returns of the 22 full sessions ending at d (the first return of each session from
  its 09:30 open), x 252 / 22 x 10^4. That is annualised and in VIX points squared. RTH only: the overnight return is left
  out, because the no-adjust overnight return is wrong across rolls. The tercile is a trailing RANK, so a uniform level
  shift does not move it.
- VRP(d) = VIX close(d)^2 - RV(d).
- For each calendar month: p = the share of the 756 VRP days (3 years) before the decision value that are below it.

**THE LOOK-AHEAD CHARGE (MANAGER 10-07: "the null must charge the VIX/VRP look-ahead").**
1. **The binding timing (lag 1):** the decision value is the latest VRP dated STRICTLY BEFORE the month's first session.
   VIX closes at 16:15 ET, after ES's 16:00 RTH close. Entry is at the next session's 09:30 open, more than 17 hours
   later.
2. **The lag-2 twin:** the same rule with the VRP dated TWO sessions before the entry. The Stage A bars are judged on the
   WORSE of lag 1 and lag 2. Anything earned only from the last decision day's information, including the 16:00-16:15
   window, is charged and not credited.
3. **The null keeps the state's persistence:** VRP terciles cluster (the 41 primary in-months come in 22 runs). A
   within-year shuffle would break the clusters and make the null too easy. So the null circularly SHIFTS the month-state
   series against the returns (below).
4. **No full-sample anything:** the tercile is trailing only. 2010-07 .. 2013-07 is the warm-up (VRP day 756 = 2013-07-17) and is never traded.

**Trade.**
- In-month (p >= 2/3, the top tercile): LONG 1 ES at the month's first session's 09:30 open, out at the month's last
  session's close. Flat over the night between months.
- Each in-month is one trade with its own round-trip cost: 0.363 pt, $50 a point. Marked at each RTH close.
- The WF's last month is June 2025, cut at the 2025-06-27 close (arrays end 2025-06-29).

**Cells and counts (schedule only).**

| Cell | lag 1 (binding twin A) | lag 2 (binding twin B) |
|---|---|---|
| top tercile = PRIMARY | 41 in-months (4.6 a year), 22 runs, 880 held sessions, 160 R days | 40, 20 runs, 860 held, 131 R days |
| top quartile = neighbour | 32 (3.6 a year), 13 runs, 691 held, 133 R days | 36, 18 runs, 775 held, 116 R days |

- Lags 1 and 2 share 37 primary months; 4 are lag 1 only, 3 are lag 2 only.
- Primary in-months by calendar year: 2016 3, 2017 1, 2018 6, 2019 7, **2020 11** (January to November), 2021 6, 2022 5,
  2023 0, 2024 1, 2025 1.
- By half: 34 in 2016-21, 7 in 2022-25.
- VRP is below zero on 68 of 2,236 WF VRP days.
- **Reported twin (not a bar):** ALWAYS LONG, every WF month on the same calendar (108 months). The claim is that VRP timing
  beats always-long per unit of drawdown.

## The family null (binding for A2 and the earner route)
- **CIRCULAR SHIFT:** the 108-month WF state vector (both cells together, lag 1) is rotated by k months against the returns.
  Every k from 12 to 96 is used (85 draws, exhaustive), so it is deterministic and needs no seed.
- The shift keeps each cell's count, the clustering and the persistence. It removes only the alignment between the premium
  and the returns.
- **Statistics:** the family max over the two cells of own ROC@$30k (with DD5), and the family max of the R-day sum.
- **Reported beside it:** a within-calendar-year label shuffle (x1,000, seed 20261007). It is an easier null, and the gap
  between the two is printed.

## POWER LINE (house rule MANAGER #37)
- Coin-flip sides on the primary's schedule, added to #463's WF daily (parity 93.81 / 3.816 asserted).
- **VOL scale (x0.709):** SD of the book-add lead 11.5; minimum detectable 19.0; four in five 28.7.
- **$30k own drawdown (x0.665):** 11.0; 18.1; 27.4.
- This is poor power. Only a large edge is detectable on 41 months.

## Stage A bars (walk-forward 2016-07-01 .. 2025-06-29; all must pass, on the WORSE of lag 1 and lag 2)
- **A1 route:** own ROC@$30k >= 15, OR the earner route: own ROC@$30k >= 5 AND the R-day sum above the family null's p95.
- **A1 count:** >= 100 trades and >= 50 a year (MANAGER #41 Q3); any year under 25 is flagged thin. **Cannot pass:** 41
  in-months. A cell that fails on count ALONE and clears every other bar is a RESEARCH ROW, not a pass, and gets no
  variants.
- **PF > 1.**
- **>= 6 of 9 July-June years positive.**
- **A1b:** the route still holds without 2020 (calendar 2020 removed).
- **A2:** the primary's own ROC@$30k > the circular-shift null's p95.
- **A3:** the top-quartile neighbour is net positive.
- **A4:**
  - net > 0 without the best trade;
  - net > 0 at 2x cost;
  - net > 0 without 2020-02-15 .. 04-30;
  - EARLY 2013-08 .. 2016-06 net > 0 (the first month with a full 756-day rank) (reported as a bar, like VVIXTAIL's).
- **A5 (beats always-long):** own ROC@$30k > the always-long twin's own ROC@$30k.
- **Every ROC @ $30k prints its DD5 beside it (#77).** A worst drawdown > 1.3 x DD5 is flagged "driven by one episode".

## Reported (no verdict)
- Addendum 2 diagnostics:
  - the event path by session of the month;
  - regime halves 2016-21 / 2022-25;
  - the cost curve at 0 / 5 / 10 / 20 bps;
  - per-year and per-episode rows;
  - every in-month with its dollars.
- The book add at the VOL scale and the $30k twin, each with DD5.
- The dollars inside #463's worst WF drawdown.
- The within-year-shuffle null beside the binding circular-shift null.

## What follows
- **PASS** is impossible on count. **RESEARCH ROW** (count-only fail, all other bars clear): ledger row, RUNBOARD research
  row (family MISC, with --wf-dd5), TTM.md note. No plugin and no Auto-Validate unless MANAGER relays an owner decision.
- **FAIL:** dead; no other premium definition, horizon, lag or instrument. Ledger row, lane notes, RUNBOARD research row.
- Nothing live or in the adopted book changes without the owner.
