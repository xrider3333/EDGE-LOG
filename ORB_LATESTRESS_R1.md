# ORB lane LATESTRESS r1 — last-half-hour momentum on stress days, NQ and ES: DEAD at Stage A (2026-10-08)

Pre-registration: `docs/PREREG_orb_latestress_r1_2026-10-07.md`, with addenda 1-3, all written before any return.
- MANAGER rulings #51 / #52 are folded in as addendum 3.
- The prereg was witnessed off this PC as origin branch `prereg/orb-latestress-r1` at 98e86d40.
- Its LF sha256 501eb9d6... was posted to MANAGER (#611) before the run. The harness checked it at start: MATCH.

Tool: `tools/orb_latestress_r1.py`, on the NT r1 machinery in `tools/orb_nt_common.py`, with a breadth hook added per
addendum 1. Run log: `C:/EdgeLog/manager/latestress_r1_stageA_2026-10-08.txt`. Walk-forward 2016-07-01..2025-06-29
only; the lockbox was not read.

**Parity.** #463 reproduces exactly (93.81 / 3.816 / $44,849, with 460 drawdown days).

**The rule.** On stress days only, NQ and ES ride the last half hour in the direction of the day so far: from the
15:30 open to the 16:00 close.
- Stress = T1, the prior VIX close in its trailing-252 top fifth; or T2, the day's move >= 2x its 60-session median.
- Baltussen, Da, Lammers & Martens (2021) say dealer and leveraged-ETF hedging pushes the close this way, hardest on
  high-volatility days.
- The target was the drawdown-week earner row.

## Result: 0 of 4 cells; all four sit at zero

| Cell | WF trades | Net | t | ROC @ $30k | Worst DD | DD5 | #463 drawdown days |
|---|---|---|---|---|---|---|---|
| NQ T1 (VIX) | 439 | -$1,845 | -0.06 | -0.1 | $51,788 | $16,834 (one episode) | -$15,245 |
| ES T1 (VIX) | 438 | +$663 | +0.03 | 0.1 | $27,942 | $10,323 (one episode) | -$8,809 |
| NQ T2 (day move) | 530 | -$2,190 | -0.09 | -0.2 | $37,647 | $10,821 (one episode) | -$1,147 |
| ES T2 (day move) | 544 | -$4,974 | -0.28 | -0.5 | $33,777 | $9,633 (one episode) | -$4,586 |

- The family null's 95th percentile is t 1.50 and a drawdown-day sum of $5,479. No cell comes near either.
- The VIX pair is one test (addendum 3), and it fails on both markets.

## What it teaches

- **The mechanism is real only in the crash it was named for.**
  - Every cell earns in March 2020: +$11.8k to +$15.5k over #463's worst episode.
  - Every cell gives that back in April 2025 (-$6.0k to -$12.3k) and loses over the 460 drawdown days as a whole.
  - Without Feb-Apr 2020, every cell is -$19.7k to -$30.1k.
- **The regime flipped.**
  - The VIX cells earned in 2016-21 (ROC 12.9 NQ, 13.1 ES) and lost in 2022-25 (-4.7, -5.5). The prereg named the
    0DTE era as the enemy.
  - The year rows say the same: one year (Jul-2019..Jun-2020, +$18k to +$27k) carries the early half, and 2024-25
    gives it back (-$14k to -$32k on the VIX cells).
- **Before cost it is a few dollars a trade.** Gross over the walk-forward is +$2.8k to +$8.6k per cell on 440-545
  trades, and a round trip's cost removes it.
- **Where the move sits.** The event-time path puts most of the in-direction drift between 15:45 and 15:50, around the
  closing-imbalance publication. It is small, and it is not a trade.
- **Breadth (addendum 1).**
  - NQ T1 passes the amended bar (4 of 6 qualifying years). The other three fail it.
  - Every cell fails the standard 6/9 bar (report).
  - No cell is UNDECIDABLE: there are 6 qualifying years on the VIX cells and 9 on the day-move cells.
- **Power, honestly.**
  - The real per-trade spread was larger than the smoke run's noise (sd $774-$1,375).
  - So the smallest detectable mean was $93-$184 a trade, against the $83-$103 the earner floor needs. The VIX cells
    could not have resolved an effect of exactly earner size.
  - But every observed mean is about zero (t between -0.28 and +0.03). This is not a near miss hidden by low power.

## Reported only (no pass route; SEEN now)

- **T1 and T2 together:** NQ 149 trades +$28.2k (t 1.44); ES 175 trades +$20.3k (t 1.31). Both are under the null.
  Not proposed.
- **Gao et al.'s 15:00 -> 15:30 signal on the same days:** NQ T1 +$24.1k (t 0.84), ES T1 +$22.3k (t 1.11). Not
  proposed.
- **ALL days (the ledger 2.14 replica, SEEN):** NQ -$10.0k on 2,240 trades, ES -$16.4k. It reproduces 2.14's "flat to
  negative".
- **The book add at the volatility scale is a REPORT:** 74.5 to 90.0 against 93.8. Every cell lowers #463.

## What this closes

- Last-half-hour momentum on NQ / ES is dead:
  - unconditional (2.14);
  - on VIX-stress days;
  - on big-move days.
- The family is closed for this lane: no variants, and no re-cut stress thresholds (prereg).
- The drawdown-week earner row is not reachable this way. The March 2020 afternoons were real, but April 2025 and
  2022 took them back.
