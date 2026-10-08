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

## ADDENDUM 1 - pre-data, after MANAGER's adversarial review (2026-10-07, GO WITH EDITS)
Review: C:/EdgeLog/manager/reviews/REVIEW_VRPES_JUMPSPLIT_2026-10-07.md (inbox #82). Written BEFORE any real-direction
number. Where it differs from the sections above, this addendum governs. The harness is re-written to it:
`python tools/vrpes_r1_stageA.py --predata` (schedule, inputs, counts, power) and `python tools/vrpes_r1_stageA.py`
(Stage A; it refuses unless this file is on origin/main).

**Edit 1 - RV on every session.**
- RV now uses every ES RTH session that has any bar. A return across a missing bar counts as one return.
- 122 sessions have fewer than 78 bars and would have been dropped by the old rule, 4-14 a year. Most are CME holiday and
  early-close sessions.
- The four 2020 circuit-breaker days are inside RV: 03-09 with 77 bars; 03-12, 03-16 and 03-18 with 76 each.
- The ES holes are inside RV with what is there: 2020-02-28 has 18 bars (to 10:55), 2020-06-30 has 9.

**Edit 2 - overnight variance in RV (the primary).**
- Per-session RV = the squared overnight return + the RTH sum. The overnight return is the ADJ 30m close-to-open point gap
  over the prior session's no-adjust close, which is exact across rolls. It is available on 3,867 of 3,868 sessions.
- RTH-only RV becomes a REPORTED twin. At lag 1 it has 43 in-months, 34 of them shared with the primary.

**Edit 3 - the schedule, restated before the run.**
- **Lag 1 (primary):** 39 WF in-months (4.3 a year) in 22 runs. 9 fall in 2020: January, February, March and June to
  November.
- **Lag 2:** 40 in-months in 24 runs, 9 in 2020.
- **The 2020 states at lag 1:**
  - February IN: VRP dated 01-31, VIX 18.84, rank 0.948.
  - March IN: 02-28, VIX 40.11, RV22 605, rank 0.997.
  - April OUT: 03-31, VIX 53.54, RV22 7,885, rank 0.000.
- **At lag 2:** February IN (0.757), March IN (0.999), April OUT (0.000).
- Edits 1-2 moved April 2020 OUT. The draft had it IN, which bears out the review's suspicion that dropping the halt days
  understated RV. The schedule is still LONG through March 2020.
- **Neighbour (top quartile):** 33 in-months at lag 1, 32 at lag 2.
- **By half:** 32 / 7 at lag 1; 32 / 8 at lag 2.

**Edit 4 - every in-month's inputs** are printed by --predata: the VRP date used, its gap to entry in VIX days, VIX, RV22
and the rank.
- At lag 1 every gap is 1 VIX day, except September 2018. Its entry session is the CME Labor Day session (2018-09-03), so
  no VIX day falls in between (gap 0); the VRP is still dated strictly before the entry. At lag 2 every gap is 2, except
  that month (gap 1).
- **No gap is larger than its lag.**
- **Hand check against the CBOE photograph:** 01/31/2020 close 18.84; 02/28/2020 40.11; 03/31/2020 53.54; lag 2:
  01/30 15.49, 02/27 39.16, 03/30 57.08. All six match the harness.
- **Hole months:** February 2020's last session is the 02-28 hole, so its exit is that day's last bar in the master (the
  10:55 close, a traded price). June 2020 exits at the 06-30 hole's last bar the same way.
- **Holiday rows:** the VIX photograph carries rows on some CME-holiday sessions from 2022 on. They enter VRP's trailing
  history (a few a year) but are never a decision value in this schedule.

**Edit 5 - A2 on the worse lag.**
- The circular shift is run on EACH lag's own WF state vector (k = 12 .. 96, 85 shifts, both cells together).
- p is printed as a RANK out of 86 (85 shifts plus the real). A2 passes only if at most 4 of the 85 shifts are at or above
  the real (rank <= 5).
- The earner route's null is the family max of the R-day sum on the same shifts, read the same strict way.

**Edit 6 - new binding A6, regime-matched.**
- The primary's own ROC@$30k must beat a VIX^2-ALONE twin: the rank of VIX among the 756 values before it, on the same
  dates, with the same tercile, lags and calendar.
- At lag 1 the twin has 41 in-months, 25 of them shared with the primary (14 primary only, 16 twin only). At lag 2, 25 are
  shared.
- **Failing A6 files the row as "VIX-level timing, not VRP".**

**Edit 7 - per stretch (Ruling 2).**
- A4's EARLY and no-February-April-2020 tests move onto the LEAD vs always-long. They now form the RISK r1 trio:
  - the lead (ROC@$30k timed minus always-long, each sized on its own drawdown in the stretch) is > 0 over the WF, over EX
    (the WF without 2020-02-15 .. 04-30, rows joined end to end) and in EARLY 2013-08 .. 2016-06;
  - paired d (daily timed minus always-long at fixed WF $30k multipliers) is > 0 in >= 6 of the 9 WF July-June years.
- **Standalone net > 0 in BOTH WF halves is binding.** 2022-25 holds only 7 in-months at lag 1 and 8 at lag 2.
- A4 keeps: net > 0 without the best trade, and net > 0 at 2x cost (roll charges doubled too).
- The old A5 ("own ROC > always-long's") is replaced by the trio.

**Edit 8 - can the 6-of-9 bar be met?**
- In-months per July-June year, 2016-17 .. 2024-25: lag 1 = 4, 2, 5, 8, 9, 6, 2, 0, 3; lag 2 = 3, 3, 7, 7, 9, 5, 2, 0, 4.
- **2023-24 has no in-month and counts as NOT positive**, so 6 of the other 8 years must be positive.
- EARLY 2013-08 .. 2016-06 has 10 in-months at lag 1 and 7 at lag 2.

**Edit 9 - roll charge.**
- One extra 0.363 pt round trip is charged for each real ES switch held through. The switches come from
  tools/data/rolls_ES.csv: 61 between 2010-06 and 2025-06, all 'exact'.
- A switch counts when its evening falls on or after the month's first session and before its last.
- 15 of the 39 lag-1 in-months carry one.

**Edit 10:** the book add is also reported against the RESMOM line, L = #463 + 0.264 x RES. L's parity (120.82 / 3.916)
is asserted via balance_r1_stageA.load_L.

**Edit 11 - forward BOOK line gate.**
- No forward BOOK line opens unless BOTH hold:
  - the VOL-scale lead over #463 stays > 0 without calendar 2020;
  - the leg's worst WF drawdown is not flagged one-episode (> 1.3 x DD5).
- At about 4 trades a year, with the lockbox spent, any forward read is a HARM MONITOR only.

**Edit 12 - the minimum detectable lead in own money.**
- The power line, re-run after edits 1-2 (it moved because the coin-flip draw falls on the new schedule):
  - VOL scale (x0.796): SD 17.0, minimum detectable 28.0, four in five 42.3.
  - $30k own drawdown (x0.733): 16.4 / 27.1 / 40.9.
- **Converted at the $30k-own-drawdown sizing.**
  - At the VOL scale a sparse leg's lead SATURATES: a deterministic edge raises its daily SD as fast as its mean. So the
    VOL line has no own-money equivalent.
  - A book-add lead of 27.1 needs own ROC@$30k 94. That is the median over 200 coin-flip draws; p25 is 16 and p75 is 97,
    and the spread is the sign each draw gives March 2020. It equals own **$94k a year at a $30k drawdown**.
- **The prior median is ROC 5 = $5,000 a year** (ROC@$30k 1 = $1,000 a year at a $30k drawdown; the review's "$1.5k" reads
  it against $30k).
- Neither reaches the $15k MDL, let alone the minimum detectable lead. **The BOOK ADD is labelled UNDECIDABLE** and is
  printed as a report only.

**Edit 13 - VIX rows on CME holidays: DROP (MANAGER 10-07, after the addenda were accepted; still pre-data).**
- The photograph carries VIX rows on 23 of the 71 CME US-holiday sessions in the ES data (stock market closed). All 23
  are 2022-05-30 or later; every one is listed in the --predata log.
- **They are DROPPED, so no VRP value is ever dated on a holiday.** A holiday session ends with the 12:55 or 13:00 bar,
  complete from 09:30 (the CME schedule). Its own returns stay in RV.
- **Effect, printed before data:** trailing ranks move by about 0.01 on a few 2024-25 months, and NO in-month changes at
  either lag. The schedule in edit 3 stands: 39 / 40 in-months.
- (The GEX file used by GAMMA r1 has no holiday rows.)

**MANAGER 10-07 (acceptance):** the book add is undecidable (edit 12), so VRPES files as a RESEARCH ROW at best. That
holds whatever the standalone bars say: no plugin, no Auto-Validate, no forward line.
