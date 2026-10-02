# DIP forward shadow — a fresh lockbox for a parked family (pre-registered 2026-10-02)

Owner 2026-09-29 (via MANAGER): DIP stays parked for ROC **until new data or a fresh lockbox exists**. The
ES/NQ lockboxes to 2026-08-24 have been read, so the only clean evidence left is forward. This file fixes,
before any forward trade exists, what a no-order paper shadow would run and what it must show.

## What runs (needs the paper lane and MANAGER's OK - this chat runs no paper infrastructure)

- **DIP on ES = run #452's frozen champion** (`NQDIP_1_3.py`, ES 5m RTH no-adjust master, true rolls from
  `tools/data/rolls_ES.csv`), $100,000 notional, cost as in the file. No orders, shadow only.
- **DIP on NQ = run #433's frozen champion** (`NQDIP_1_2.py`, NQ), same terms.
- Daily signals on the RTH close, fills at the next RTH open, exactly as the backtest. Every open position
  valued at each session close (the files' mark_open_trades).
- Start: the first session after the shadow is switched on. Nothing before that date counts.

## The bar (owner yardstick, applied to the forward stretch as if it were a lockbox)

Judged per market at the FIRST of: 50 closed trades, or 9 months after the start.
1. ROC %/yr at a $30k worst drawdown, drawdown valued daily, at least **half its walk-forward figure** on the
   same yardstick (`docs/DIP_ROUND3.md` RAW: ES 13.2 -> bar 6.6; NQ 26.9 -> bar 13.5);
2. daily Sortino above 0.5;
3. net profit stays positive without its single biggest trade;
4. forward drawdown valued daily no deeper than the walk-forward's ($71,941 ES, $53,267 NQ).
A market that clears all four re-opens DIP for a pre-registered book-seat test against BOOK #463, with the
forward stretch as its lockbox. A market that fails stays parked; the shadow then stops. Nothing is adopted
by this file, and no setting may change while the shadow runs.
