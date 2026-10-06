# PRE-REGISTRATION - VVIXTAIL r1: does a high VVIX / VIX ratio warn of ES weakness over the next week? (TTM scope rank 7, opened by MANAGER #72)

Drafted 2026-10-06 by the TTM lane BEFORE any real-direction number exists. DRAFT for MANAGER review.
- Computed so far: the photograph check, entry COUNTS per year, and the power line from a coin-flip side. None of these
  involves a direction.
- Harness: `tools/vvixtail_r1_stageA.py`. Only `--counts` and `--power` have run. It reuses HALFHOUR r1's book and
  power-line code.

## Mechanism (theory and literature)
VVIX is the implied volatility of VIX options, the market's price for how much VIX itself will move. Two published
findings:
- Vol-of-vol carries tail information that VIX does not (Park 2015 JFM).
- Vol-of-vol risk is priced, and high vol-of-vol forecasts weak index returns (Huang, Schlag, Shaliastovich & Thimsen 2019
  Management Science).

The hypothesis: when VVIX is unusually high RELATIVE to VIX, the option market is paying for a jump in volatility that
the index level has not yet priced. ES then tends to fall over the following week.

## Disclosed before any return: WHEN it fires (schedule only)
The ratio is high when VIX is LOW. VVIX stays near 85-100, while VIX drops to 11-13 in calm markets. In a crisis VIX
jumps faster than VVIX, so the ratio falls.

So the top-2% trigger fires in CALM, low-VIX years:
- 2017: 16 entries; 2021: 13; 2023: 10; 2016: 7; 2019: 7; 2024: 2; 2018: 1;
- NONE in 2020 or 2022.

As specified, this is a short-the-complacency trade. It is not a crisis hedge, and it cannot earn in March 2020. The
earner route can still pass on R's other 44 episodes, which the R-day sum covers.

## What is different (one line), and the dead families it is not
**The dead crash and stress shorts triggered on trend and realized vol, or on the VIX curve. This triggers on
vol-OF-vol relative to vol, which fires in the opposite regime: calm markets.**

Dead and not re-tested:
- Crash-regime NQ short, 18 of 18 cells (2.16).
- VOLCARRY (2.39).
- Q12 LONGVOL / Q13 HAVEN / Q15 STEEPENER: VIX >= VIX3M states (2.59, 2.64).
- DAILYFADE (2.68).

## Rules (frozen; MANAGER #72's specification)
**Data.**
- VIX and VVIX: the 2026-10-05 CBOE photographs, C:\EdgeLog\_research_cache\public_series\cboe\VIX_History.csv (sha256
  6edc3e39...) and VVIX_History.csv (sha256 098e91bc...), from cdn.cboe.com, fetched 14:51:50 / 14:51:51 -07:00.
- Both are re-hashed against public_series_provenance.json, and the run aborts on a mismatch. Rows after 2025-06-29 are
  dropped on read. The ratio series starts 2007-01-03.
- ES 30m RTH roll-corrected (ADJ, db_adj_rth) master, loaded 2010-06-07 .. 2025-06-29. Positions span sessions, and the
  ADJ master's additive shift leaves every point difference exact.

**Signal (prior-day values only).**
- ratio = VVIX close / VIX close on the same date.
- Session d is a signal session if the latest ratio dated strictly before d is at or above the q-quantile of the 252
  ratio days before that one.

**Trade.**
- On a signal session while flat: SHORT 1 ES at d's 09:30 open, out at the close of session d+4 (5 sessions). No stop.
- No new entry while short.
- Cost 0.363 pt per round trip, $50 a point. Marked at each RTH close.

**Cells and counts (schedule only).**
- top 2% (q 0.98) = PRIMARY: 56 WF entries (6.2 a year), 280 held sessions, 95 of them R days.
- top 5% (q 0.95) = the neighbour: 86 (9.6 a year), 430 held sessions, 165 R days.

**Family null (MANAGER #72).**
- Each cell's entry count per calendar year is placed on random sessions of the same year, non-overlapping.
- 1,000 draws, seed 20261006.
- Statistics: the family-max R-day sum (binding for the earner route) and the family-max own ROC@$30k (reported).

## POWER LINE (house rule MANAGER #37)
- Coin-flip sides on the primary's schedule, added to #463's WF daily (parity 93.81 / 3.816 asserted).
- **VOL scale (x2.22):** SD of the book-add lead 6.9; minimum detectable 11.4; four in five 17.2.
- **$30k own drawdown (x1.93):** 5.9; 9.8; 14.8.

## Stage A bars (walk-forward 2016-07-01 .. 2025-06-29; all must pass)
- **A1 route:** own ROC@$30k >= 15, OR the earner route (MANAGER #72): own ROC@$30k >= 5 AND the R-day sum (over R's 762
  days) above the family null's 95th percentile.
- **A1 count:** >= 100 trades and >= 50 a year.
- **PF > 1.**
- **>= 6 of 9 July-June years positive.**
- **A1b:** the route still holds without 2020.
- **A3:** the top-5% neighbour is net positive.
- **A4:**
  - net > 0 without the best trade;
  - net > 0 at 2x cost;
  - EARLY 2010-06-07 .. 2016-06-30 net > 0.

**Count-bound by construction (MANAGER #72).** At 6 to 10 trades a year the count bar cannot pass. A cell that fails on
count ALONE and clears every other bar is a RESEARCH ROW, not a pass, and gets no variants.

## Reported (no verdict)
- The book add at the VOL scale and the $30k twin.
- Every primary trade, with its entry date and dollars.
- Regime halves 2016-21 / 2022-25.
- Per-year rows.
- The event path by session of the hold.
- The cost curve at 0 / 5 / 10 / 20 bps.
- The dollars inside #463's worst WF drawdown.

## What follows
- **PASS:** a VVIXTAIL_1_0 plugin with a daily data input (the two photographs), harness parity to the trade first, then a
  WINDOW-PINNED Auto-Validate on a RANGED file: 900 trials over q, the hold and the lookback, lockbox veto-only. Then a
  RUNBOARD row.
- **FAIL:** dead; no other trigger, hold or instrument. Ledger row, TTM.md note, RUNBOARD research row (family MISC).
- VRPES stays mapped (MANAGER #72). Nothing live or in the adopted book changes without the owner.
