# PRE-REGISTRATION - IMPLIEDMOVE r1: does a first hour that outruns the option market's priced move keep going on ES? (TTM scope rank 3)

Drafted 2026-10-06 by the TTM lane BEFORE any real-direction number exists. DRAFT for MANAGER review (60-minute rule).
- Computed so far: the VIX photograph check, trade COUNTS, the NOISE #422 / R overlap (schedule only) and the power line
  from a coin-flip side. None of these involves a direction.
- Harness: `tools/impliedmove_r1_stageA.py`. Only `--counts` and `--power` have run, plus one counts-only probe of the
  yardstick (below). It reuses HALFHOUR r1's book, power-line, standalone-bar and overlap code.
- Scope: docs/SCOPE_TTM_2026-10-05.md rank 3. MANAGER #67 conditions are folded in below.

## Mechanism (theory and literature)
VIX is the option market's price for the next month's S&P 500 variance. Implied variance usually sits ABOVE what is then
realized (Bollerslev, Tauchen & Zhou 2009 RFS), so a session whose first hour already outruns the priced move is a genuine
surprise. Dealers who are short gamma then hedge in the direction of the move, which extends it (Baltussen, Da, Lammers &
Martens 2021 JFE; Barbon & Buraschi 2020).

The trade: on those sessions, ride the first hour's direction to the close.

## What is different (one line), and the dead families it is not
**NOISE's band measures a big move by the TRAILING REALIZED move on NQ (and died on ES). This measures it by the OPTION
MARKET'S IMPLIED move, on ES, and must beat a count-matched trailing-realized twin, or it is NOISE on ES again.**

Dead and not re-tested:
- NOISE on ES, transferred and re-tuned natively (NOISE.md 2026-08-22).
- First-hour-to-close momentum unconditioned (LDM / DRIVE, BACKTESTING_STACK.md line 688).
- The volatility-feature family as filters (2.4).
- VIX-state seats (2.39, 2.59, 2.64).

## The yardstick, and a ruling needed (counts only, no direction)
The scope wrote "k x the implied DAILY move". The VIX photograph check and counts show that a first hour's range almost
never reaches a full day's 1-SD implied move:
- k 1.0 gives 39 WF trades (4 a year); k 1.25 gives 8 (1 a year).
- Either cell fails the 100 / 50 bar by construction, so the most it could ever be is a research row.

The right yardstick for a ONE-HOUR range is the implied move for one hour: the daily move x sqrt(60 / 390). On that
yardstick (counts only):
- the median WF session's first-hour range is 1.09x the hour-scaled implied move; the 75th percentile is 1.42x, the 90th
  1.86x;
- k 1.0: 1,288 WF trades (143 a year); k 1.25: 809 (90 a year); k 1.5: 460 (51 a year); k 1.75: 32 a year; k 2.0: 19
  a year.

**Ruling asked of MANAGER (two values either way, per #67):**
- **Option A, kept literally:** k 1.0 / 1.25 on the hour-scaled yardstick (143 / 90 a year). k 1.0 sits below the median
  session, so that cell is closer to "every day" than to "an expansion day".
- **Option B, recommended:** k 1.25 (PRIMARY, 90 a year) / 1.5 (51 a year) on the hour-scaled yardstick. Both are
  upper-tail sessions (roughly the top 36% / 21%), and both clear the 50-a-year bar.
- **If no answer within 60 minutes:** Option A, since it keeps #67's numbers. Its primary is k 1.0, with k 1.25 as the
  neighbour.

## Rules (frozen except the k pair above)
**Data.**
- ES 5m RTH no-adjust master (id 33), loaded with date_to 2025-06-29. Every position is intra-session.
- Sessions need their 09:30 open, their 10:30 bar and their 15:55 bar: 3,750 full sessions, 2,240 in the WF stretch.

**VIX (MANAGER #67 (1), a PHOTOGRAPHED public pull).**
- C:\EdgeLog\_research_cache\public_series\cboe\VIX_History.csv, fetched 2026-10-05T14:51:50-07:00 from
  https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv, 473,329 bytes, sha256
  6edc3e3928c4b164b9e4ed1ec874e0ed53c7d52997557adebb7d6b7451db565a (public_series_provenance.json).
- The harness re-hashes the file and aborts on a mismatch, and drops rows after 2025-06-29 on read.
- Only the latest VIX close strictly BEFORE the session is read. The session's own VIX is never read.

**Signal**, per session d:
- IM = prior VIX close / 100 / sqrt(252) x d's 09:30 open; the hour-scaled IM_1h = IM x sqrt(60 / 390).
- FH = the first hour's range: the high minus the low of the 09:30 .. 10:25 bars.
- dir = the sign of the 10:25 bar's close minus the 09:30 open.

**Trade.**
- If FH >= k x IM_1h and dir is not 0: 1 ES in dir, in at the 10:30 bar's open, out at the 15:55 bar's close.
- No stop. 0.363 pt a round trip, $50 a point.

**THE BINDING NULL (MANAGER #67 (2)): the realized twin.**
- The same rule with IM replaced by the trailing realized move: sqrt(mean 5m realized variance over the previous 20
  sessions) x the open, intra-session returns only.
- Its multiple is set so that the twin has the SAME number of WF trades as the cell (count-only bisection).
- Both cells must beat their own twin on own ROC@$30k.
- It removes exactly the claim: that the OPTION-implied yardstick picks better days than the realized one.

## Overlap and R, printed before any return (MANAGER #67 (2); schedule only)
These figures were computed on the literal daily-move yardstick (k 1.0: 39 days). They are re-printed by `--counts` once
the k pair is ruled:
- NOISE #422 trades NQ on 24 of the 39 days (62%), the same side on 21.
- 10 of the 39 days are R days (R: 657 of the 2,240 WF sessions).

On the hour-scaled yardstick (`--counts`, both pairs):

| k | WF trades | NOISE #422 trades NQ that day | same side | R days | days shared with its count-matched realized twin |
|---|---|---|---|---|---|
| 1.0 | 1,288 (143/yr) | 825 (64%) | 632 | 384 | 1,115 (87%) |
| 1.25 | 809 (90/yr) | 533 (66%) | 410 | 251 | 624 (77%) |
| 1.5 | 460 (51/yr) | 300 (65%) | 237 | 138 | 331 (72%) |

The candidate and its twin share most of their days. A2 is therefore decided on the 13-28% of days where the implied and
the realized yardsticks disagree, and it has little power. That favours Option B, where they disagree more.

The R-DAY SUM (primary, and without its 3 best R days) is the FIRST line Stage A prints.

## POWER LINE (house rule MANAGER #37)
- Printed for the literal k 1.0 schedule (39 trades): VOL scale x3.02 NQ-equivalent; SD of the book-add lead 9.3;
  minimum detectable 15.2; four in five 23.0. At the $30k own drawdown (x0.98): 3.3 / 5.3 / 8.1.
- It is recomputed by `--power` on the ruled primary's schedule and posted before Stage A runs.

## Stage A bars (walk-forward only, 2016-07-01 .. 2025-06-29; all must pass)
- **A1 standalone (house line #45, HALFHOUR's code):**
  - own ROC@$30k >= 15, OR the earner route;
  - PF > 1;
  - >= 100 trades and >= 50 a year;
  - >= 6 of 9 July-June years positive.
- **A1b:** the same route holds without 2020.
- **A2 (binding null):** each cell's own ROC@$30k > its count-matched realized twin's.
- **A3:** the neighbour cell is net positive after cost.
- **A4:**
  - net > 0 without the best trade;
  - net > 0 at 2x cost;
  - EARLY 2010-06-07 .. 2016-06-30 net > 0.
- A cell that fails on count alone and clears every other bar is a RESEARCH ROW, not a pass, with no variants
  (MANAGER #67).

## Reported (no verdict)
- The book add at the VOL scale and the $30k twin; the overlap with #463's NQ legs.
- Addendum 2 diagnostics:
  - the event path at each half-hour close;
  - regime halves 2016-21 / 2022-25;
  - long vs short;
  - the cost curve at 0 / 5 / 10 / 20 bps;
  - per-year rows;
  - prior VIX < 20 vs >= 20.

## What follows
- **PASS:** the same day, an IMPLIEDMOVE_1_0 plugin (a second, daily data input: the VIX photograph; harness parity to the
  trade first), then a WINDOW-PINNED Auto-Validate on a RANGED file (never a pinned single-config file): 900 trials,
  lockbox veto-only. Then a RUNBOARD row.
- **FAIL:** dead; no other yardstick, window or k. Ledger row, TTM.md note, RUNBOARD research row.
- Nothing live or in the adopted book changes without the owner.

## AMENDMENT 1 - MANAGER rulings #68 (2026-10-06 11:06 MST, GO), written in before any return
- The one-hour scaling (the daily implied move x sqrt(60 / 390)) is accepted.
- No return had been read when the ruling arrived; only counts, the overlap and the power line had run. So **Option B is
  the registered cell pair: k 1.25 = PRIMARY (90 a year), k 1.5 = neighbour (51 a year).**
- Option A's other value (k 1.0) and its count-matched twin print as a REPORT, never a cell.
- The count-matched realized twin binds as written (A2).
- The power line is re-run on the k 1.25 schedule before Stage A. The run starts after this file is on main.
