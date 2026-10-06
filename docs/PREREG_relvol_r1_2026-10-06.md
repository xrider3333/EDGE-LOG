# PRE-REGISTRATION - RELVOL r1: does NQ's volatility relative to ES's tell the next session's NQ-vs-ES spread? (TTM scope rank 2)

Drafted 2026-10-06 by the TTM lane BEFORE any real-direction number exists. DRAFT for MANAGER review (60-minute rule).
- Computed so far: trade COUNTS per cell and the power line, from a coin-flip side on the primary's schedule. Neither
  involves a direction.
- Harness: `tools/relvol_r1_stageA.py`. Only `--counts` and `--power` have run. It reuses HALFHOUR r1's book, power-line,
  standalone-bar and overlap code (`tools/halfhour_r1_stageA.py`).
- Scope: docs/SCOPE_TTM_2026-10-05.md rank 2. Rank 1 (OPENCOIL) was dropped after round 24 returned SQUEEZE.

## Mechanism (theory and literature)
Stocks with high idiosyncratic volatility earn low future returns (Ang, Hodrick, Xing & Zhang 2006 JF; 2009 JFE,
international). The effect is concentrated where mispricing is hard to arbitrage, e.g. under short-sale limits and lottery
demand (Stambaugh, Yu & Yuan 2015 JF). At the index level, the part of NQ's volatility that ES does not share is the
tech-specific component. The hypothesis: when NQ is unusually volatile RELATIVE to ES, NQ underperforms ES next, and the
mirror holds when NQ is unusually calm relative to ES.

## What is different (one line), and the dead families it is not
**Every dead NQ-vs-ES family on EL traded the PRICE ratio or relative return. This one trades the relative VOLATILITY,
beta-neutral, and never conditions on which index went up.**

Dead and not re-tested:
- SPREAD r1: ratio momentum, 0 of 12 cells (2.24).
- SPREAD r2: intraday relative strength at 10:30; continuation beat reversal, and it still failed (2.45).
- MISC round 16 PAIRS: ES/NQ log-ratio mean reversion, cost ate the edge (MISC_SWEEP.md).
- The volatility-feature family as filters (2.4); vol-state seats and vol targeting (2.32, 2.39, 2.47, 2.59).

The signal's correlation with the 20-day relative RETURN percentile is printed, so a relative-strength trade in disguise
would show.

## Rules (frozen)
**Data.**
- ES and NQ 5m RTH no-adjust masters (ids 33 and 37), loaded with date_to 2025-06-29.
- Every position opens and closes inside one RTH session, so roll gaps never enter a return.
- Sessions without a 15:55 bar on either root are dropped: 3,750 common full sessions, 2,240 of them in the WF stretch.

**Signal**, at each RTH close d:
- RV = the sum of squared 5m log returns inside the session (the first bar's open-to-close included; at least 70 valid
  returns, else missing).
- Q_L = sqrt(sum of NQ's RV over the last L sessions / the same for ES).
- pct = the share of the previous 252 sessions' Q_L below today's Q_L.

**Trade**, on session d+1:
- pct >= q: SHORT 1 NQ and LONG h ES.
- pct <= 1 - q: LONG 1 NQ and SHORT h ES.
- h = beta x (NQ open x $20) / (ES open x $50) at the entry open. beta = the OLS slope of NQ's open-to-close log return on
  ES's over the 60 sessions ending at d. h's WF median is 1.49 ES per NQ (5-95%: 0.97-1.96); fractional in research.
- In at the 09:30 bar's open, out at the 15:55 bar's close. No stop.
- Cost per round trip: 0.533 pt NQ ($20 a point) plus h x 0.363 pt ES ($50 a point).

**Cells (3), with counts from the schedule only:**
- L 20, q 0.9 = PRIMARY: 476 WF trades (53 a year), 220 short-NQ / 256 long-NQ.
- L 20, q 0.8: 1,008 (112 a year).
- L 40, q 0.9: 508 (56 a year).

The scope's 5-session hold is NOT a cell: it gives about 11 trades a year, under the house's 50. It is replaced by the
one-session form above.

**Family null.**
- Each cell's signal days in each July-June year are moved, with their sides, to random sessions of the same year.
- 1,000 draws, seed 20261006. Statistic: the family MAX of own ROC@$30k.
- This keeps the count, the side mix and NQ's drift against ES (NQ outran ES over most of 2016-25, so a long-NQ-leaning
  rule earns drift on any days). It removes only the timing the mechanism claims.

## Where it sits on the MDL map (docs/MDL_MAP_R1.md)
Beta-neutral, so it aims at the "uncorrelated" row: about $15k a year at a $30k own drawdown. The NQ leg's overlap with
#463's ORB / NOISE held bars is printed.

Reported, not barred: the leg's dollars in #463's worst WF drawdown (HALFHOUR's worst-window code), calendar 2022, and
2025-02-19 .. 04-30.

## POWER LINE (written before any real-direction run; house rule MANAGER #37)
- Method: coin-flip sides on the primary's schedule (476 trades), added to #463's WF daily (parity 93.81 / 3.816
  asserted). Paired stationary bootstrap, mean block 20, 1,000 draws.
- **VOL scale (the primary book-add size, x2.51 NQ):** SD of the lead 16.1 points; minimum detectable 26.5; four in five
  40.1.
- **$30k own drawdown (x0.32 NQ):** SD 2.7; 4.5; 6.8.
- **In plain words:** a spread leg's daily swings are small, so the volatility sizing puts about 2.5 NQ on it, and then
  only a strong leg shows on the book. The book add is a REPORT anyway (house line #45); the standalone bars decide.

## Stage A bars (walk-forward only, 2016-07-01 .. 2025-06-29; all must pass)
- **A1 standalone (house line #45, HALFHOUR's code):**
  - own ROC@$30k >= 15, OR the earner route (>= 5 and positive in #463's worst WF drawdown, also without its 3 best days
    there);
  - PF > 1;
  - >= 100 trades and >= 50 a year;
  - >= 6 of 9 July-June years positive.
- **A1b:** the same route holds with calendar 2020 removed.
- **A2 null:** primary own ROC@$30k > the null's 95th percentile.
- **A3 neighbours:** both are net positive after cost.
- **A4 checks:**
  - net > 0 without the single best trade;
  - net > 0 at 2x cost;
  - the EARLY block (2010-06-07 .. 2016-06-30, after the 272-session warm-up) net > 0.

## Reported (no verdict)
- The book add at the VOL scale and the $30k twin (HALFHOUR's book_report), and the overlap with #463's NQ legs.
- Addendum 2 diagnostics:
  - the event path at each half-hour close;
  - regime halves 2016-21 / 2022-25;
  - short-NQ vs long-NQ;
  - the cost curve at 0 / 5 / 10 / 20 bps of notional, both legs;
  - per-year rows;
  - per-episode rows (runs of consecutive signal days on one side, with the five largest);
  - the correlation with the relative-return percentile.

## What follows
- **PASS:** the same day, a RELVOL_1_0 plugin (two-instrument; harness parity to the trade first), then a pinned
  Auto-Validate (900 trials over L, q and the beta window), then a RUNBOARD row.
- **FAIL:** dead. No other window, hold or threshold is tried; ledger row + TTM.md note + RUNBOARD research row.
- Nothing live or in the adopted book changes without the owner.
