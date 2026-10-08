# PRE-REGISTRATION - LATESTRESS r1: last-half-hour momentum on STRESS days, NQ and ES (ORB lane, 2026-10-07)

**Status:** drafted 2026-10-07 18:20 MST and sent to MANAGER (inbox #548), with a pre-data note (#550). No MANAGER answer
came within 60 minutes, so under the standing order this file is committed locally at about 19:05 MST, before any
return. It ships behind the push queue and Stage A runs the next morning. Any MANAGER edit that arrives before the run
goes in as a further addendum. Scope rank 1 in `docs/SCOPE_ORB_2026-10-05.md`; it replaces NT2 in the lane's queue.

## Mechanism (fixed before data)

- **Gamma hedging.** Dealers short gamma, and leveraged and inverse ETFs, must trade WITH the day's move into the close.
  That pushes the last 30 minutes in the direction of the day so far. The effect is strongest on high-volatility days.
  Source: Baltussen, Da, Lammers & Martens (2021 JFE), "Hedging demand and market intraday momentum", 60+ futures.
- **Gao, Han, Li & Zhou (2018 JFE):** on SPY, the first half-hour return predicts the last half-hour. The effect is
  stronger on high-volatility days, high-volume days and in recessions.
- **Map placement.** The house's 460 #463 drawdown days include March 2020, 2022 and April 2025. Those are exactly the
  high-volatility afternoons where the literature says the effect lives. The target row is the DRAWDOWN-WEEK EARNER
  (own ROC >= 5 plus a drawdown-day sum above its null). The standalone row (ROC >= 15) is not expected.

## What is already SEEN (disclosed)

- **Ledger 2.14:** 15:30 -> 16:00 (and -> 16:15) with the day so far, on ALL days: -$1.9 a trade, 4 of 16 years. Dead.
  It did not condition on stress. Its cells are not re-read here except as the report-only ALL-days line, labelled SEEN.
- **Ledger 2.5:** last-hour momentum, 0 of 40 cells.
- **Ledger 2.74:** BONDLEAD's own-morning twin (noon -> close with the morning) read +10.7. A different window, seen.
- **The ORB lane has read no stress-conditioned late-day number.** The stress conditions below come from the two papers.

## Rule

- **Markets:** NQ and ES, 1 contract, the roll-corrected 5-minute RTH masters (`db_adj_rth`). Bars are stamped at the
  START, Eastern; the 15:25 bar closes at 15:30. The signal is in POINTS, so it is shift-invariant on a back-adjusted
  master.
- **Signal:** m = close of the 15:25 bar - prior session's last close (the 15:55 bar; 12:55 on early closes).
- **Trade:** side = sign(m); enter at the 15:30 bar's OPEN, which is after the signal; exit at the 15:55 bar's CLOSE
  (16:00). Early-close days drop out through the missing bars. One trade a day at most.
- **Cost:** NQ 0.533 points and ES 0.363 points a round trip (the house figures NT1 used). Stress cost is +0.25 points.
- **Stress triggers (the cells):**
  - **T1 VIX:** the prior day's VIX close is >= the 80th percentile of the 252 VIX closes before it (CBOE photograph
    `_research_cache/public_series/cboe/VIX_History.csv`, sha-checked as IMPLIEDMOVE does).
  - **T2 day move:** |m| >= 2 x the median |m| of the previous 60 sessions (strictly earlier).
- **Cells:** {NQ, ES} x {T1, T2} = 4.
- **Report-only lines:**
  - ALL days: the 2.14 replica, SEEN;
  - the T1 and T2 intersection;
  - the 15:00 -> 15:30 half-hour as the signal (Gao et al.'s 12th half-hour).

## Bars (identical to NT r1, `tools/orb_nt_common.evaluate`, walk-forward 2016-07-01..2025-06-29 only)

- (a) >= 100 walk-forward trades.
- (b) the map: own ROC @ $30k >= 15, OR >= 5 with the earner test. The earner test needs a drawdown-day sum > the
  null's 95th percentile and positive without its 3 best days.
- (c) PF >= 1.05.
- (d) t >= 2 and above the family null's 95th percentile of the max t.
- (e) net positive at the stress cost.
- (f) positive without the best day.
- (g) positive in >= 6 of 9 walk-forward years.
- (i) positive without Feb-Apr 2020. This bar is decisive here, because stress days cluster in 2020.
- (j) 2010-06..2016-06 positive.
- (k) the book add at a volatility-only scale is a REPORT (house line #45).

## Null (family-wide, 500 reps, seed 20261007)

- **Random days:** for each cell, the same number of NON-trigger sessions per year, the same rule (the side from that
  day's own m).
- This asks the cell's question: does stress conditioning add anything over an ordinary afternoon?
- Max t and max drawdown-day sum are taken across the 4 cells.

## Printed first (before any signed number)

- **Trigger counts** per cell per year.
- **The power line:** the minimum detectable mean = 2.8 x sd / sqrt(N), from the UNSIGNED 15:30 -> 16:00 moves on
  trigger days, against the mean the earner row needs.

## Diagnostics (addendum 2, the 10-07 DD5 rule)

- The event-time path: the mean signed P&L at each 5-minute bar, 15:30 -> 16:00.
- Regime halves 2016-21 / 2022-25. The post-2022 0DTE era is the named enemy: more options gamma could strengthen the
  effect, and crowding could kill it.
- Cost curve x0 / x1 / x2 / x4.
- Per-year rows, and per-episode rows for #463's five deepest walk-forward episodes.
- Long against short.
- DD5 beside every ROC, with the one-episode flag.

## After the verdict

- **A PASS:** a strategy file with the frozen cell, and a WINDOW-PINNED Auto-Validate the same day. The window is pinned
  with date_from / date_to on a RANGED file, never a single-config file. Then a RUNBOARD research row with DD5, and a
  forward shadow line if the book-add report clears.
- **A FAIL:** the ledger row and a RUNBOARD research row, and the family is closed for the lane: no variants and no
  re-cut stress thresholds.

## What could fool us

- **A few crash afternoons.** March 2020, and the 2022 and April 2025 sell-offs, can carry a cell. Bar (i), the
  per-episode rows and DD5 are there for this.
- **The MOC imbalance at 15:50** is public to the market. If the move is the imbalance being priced, the path shows it
  arriving after 15:50, and the 15:30 entry is still fair; the path line says which.
- **VIX's top quintile is persistent** (weeks in a row), so trades are not independent. The random-day null draws per
  year, but not by block. Stated; a block-bootstrap t is printed beside the plain t as a report.

## Addendum 1 (2026-10-07 19:05 MST, before any return)

A smoke run checked the plumbing. Every dollar column (the trade P&L and the event-time path) was replaced by random
noise. The signals, trigger days and counts were real; no return was read.

**Real walk-forward counts:**
- VIX cell (T1): 441 trades on NQ, 440 on ES.
- Day-move cell (T2): 530 on NQ, 544 on ES.
- 2010-16: 259-352 per cell.
- Power line: the smallest detectable mean is about $46-54 a trade. The earner floor needs about $83-102 a trade (for
  $5k a year), and the ROC-15 row needs about $250-310.

**Two consequences, fixed now:**

1. **The breadth bar (g) is unfair to T1 by construction.** VIX stress days are lumpy: 2016 H2 has 2, 2017 has 9,
   2019 has 15, 2021 has 10 and 2023 has 1, against 110 in 2018.
   - For THIS family, bar (g) is: positive in at least two thirds of the walk-forward years that hold >= 10 trades of
     the cell.
   - The original "6 of 9 calendar years" is printed beside it as a report. The amended bar decides.
   - It was proposed to MANAGER (#550) before any return. If MANAGER rules the original bar before the run, the
     original decides.
2. **NQ T1 and ES T1 trade the SAME days** (same VIX trigger). They are one stress test on two markets, not two
   independent tests. The family null already takes the max across all four cells, so the bar is unchanged. The
   write-up must not count an NQ-T1 and ES-T1 pair as two confirmations.

## Addendum 2 (2026-10-08 10:45 MST, before any return)

A data-hygiene fix to the VIX trigger (T1), found from the house's session-calendar note of 10-07 and not from any
return.

- **The trap:** the CBOE VIX file has rows on 23 US stock-market holidays from 2022 on (for example 2022-05-30,
  2023-01-16). Those were CME-holiday futures sessions, where the stock market was closed.
- **The fix:** those rows are dropped before the 252-close percentile and the "prior VIX close" are taken. A CME-holiday
  session is identified as an RTH master session ending with the 12:55 or 13:00 bar. NYSE early closes (13:10 / 13:15)
  are kept.
- **Effect, counts only (smoke run with every dollar column as noise):** T1 goes from 441 to 439 walk-forward trades on
  NQ and from 440 to 438 on ES. T2 is unchanged.
- **Two related facts, stated rather than fixed:**
  - Holiday and early-close sessions have no 15:25 / 15:30 / 15:55 bars, so they never trade.
  - The ES master's data hole on 2020-02-28 (bars only to 10:55) drops that ES afternoon. It is a stress day, and it
    is lost to the data.
