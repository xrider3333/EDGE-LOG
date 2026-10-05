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

## Addendum A (2026-10-04, before the first forward trade - MANAGER #25/#28): the drawdown-week seat measurement

DIP failed the backtest seat test on correlation (docs/MDL_MAP_R1.md: DIP loses in the same weeks the book does, 2020).
A seat needs low correlation to #463's four legs in the book's DRAWDOWN weeks, per stretch, not overall. So at the
judging point above (50 closed trades or 9 months, per market) the forward read ALSO reports, never as a pass route on
its own:
1. the forward book: #463's four legs as the paper lanes value them daily (PAPER-NT8's BOOK-legs count), from 2026-10-05;
2. its drawdown days: every peak-to-trough episode of that daily equity at least $14,950 deep (the map's threshold),
   the days after each peak through its trough; if the forward book never falls $14,950, the read says "unreadable"
   (the map's own rule) and the seat question waits;
3. inside those days: the shadow's summed P&L valued daily (mark_open_trades) and its daily correlation with each of the
   four legs and with the book;
4. the map's first-order ratio on the forward book's worst drawdown: the shadow's P&L in that window per $1,000 the book
   lost, against the rate the book earns per $1,000 of drawdown over the stretch.
A seat stays an owner question. A market whose shadow LOSES in the forward book's drawdown days does not go to a seat
test even if it clears the four-point bar above; one that earns there goes with this measurement attached.
