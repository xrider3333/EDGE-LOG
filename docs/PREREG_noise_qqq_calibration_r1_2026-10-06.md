# PRE-REGISTRATION - NOISE on QQQ, calibration r1: what the NQ legs keep on QQQ shares (scope A6; MANAGER #63 / #64 / #66)

Drafted 2026-10-05 late evening by the NOISE lane, before any QQQ trade was run. It is for MANAGER's review; the harness
is written after the review and runs after IWM r1 (MANAGER: "the QQQ calibration is next either way").

## Question
The live Webull leg trades NOISE #382 on QQQ shares with NQ's settings. How much of the NQ walk-forward edge does the same
rule keep on QQQ - per unit of notional, per year, and at the live size?
- This is a CALIBRATION, not a new edge:
  - no grid, no crown, no search;
  - not a seat for the book;
  - nothing passes or fails.
- It sets the expectation the live leg is read against, and says whether the NQ backtest is a fair guide to it.

## Rules (frozen)
- **Legs, unchanged.** Every setting is relative (noise band, VWAP, bandwidth stop, percentile filters), so nothing is
  re-scaled.
  - NOISE #382 = NOISE_1_8_CT304.py, 30-minute compression gate 16 / 1.15, 2.0x. This is the live Webull base.
  - NOISE #422 = NOISE_1_8_CT304H.py, 60-minute gate 20 / 1.15, 1.75x. This is the book leg.
  - Both run the same way on both markets.
- **Data.**
  - QQQ: the 5m RTH Alpaca split-adjusted master from the NOISE fund pull. It passed the data gates (ledger 2.83).
  - NQ: the 5m RTH no-adjust master the anatomy used.
  - Both are loaded from 2016-01-04 with date_to pinned. Trades count by exit date 2016-07-01 .. 2025-06-29, the book's
    walk-forward. The lockbox is never read.
- **Cost.**
  - QQQ: $0.02 a share round trip, charged per share as traded (the TRANSFER r2 rule; QQQ had no split in the window).
  - NQ: the engine's cost.
- **The common unit.** P&L as a share of the trade's entry notional (bps), summed by day.
  - **CAL** = QQQ's mean daily return on notional / NQ's, over the walk-forward, per leg.
  - Printed with a paired stationary-bootstrap 90% band (block 20 sessions, 1,000 draws, seed 20261006). The band is a
    report, not a bar.

## Printed per leg
1. CAL with its band. Net bps a trade on each market, trades a year on each, PF on each.
2. **Trade matching.**
   - A QQQ trade matches an NQ trade when it is in the same session, on the same side, and its entry is within one
     5-minute bar.
   - The match share both ways, and the P&L of matched vs unmatched trades on each market.
   - The daily-return correlation.
3. **Where the gap comes from** (descriptive):
   - matched trades' bps on QQQ vs NQ (fills, VWAP, ticks);
   - the unmatched trades' net (different signals from the cash-open auction and the share-volume VWAP);
   - cost.
4. **Diagnostics.**
   - CAL per July-June year, H1 2016-21 vs H2 2022-25, longs vs shorts;
   - the QQQ cost curve at 1 / 2 / 3 cents a share;
   - the anatomy's single-trade-session share on QQQ vs NQ (does QQQ have the same "one break held to the close" days?).
5. **The live-size row.** The QQQ leg at 60 shares (the per-leg cap): net a year, worst drawdown and trades a year.
   Beside it, the NQ leg scaled to the same mean notional.

## How it is read (no bar - a reading rule, set now)
- **CAL >= 0.8:** the NQ backtest is a fair guide to the live leg. No action.
- **CAL 0.5 - 0.8:** the live leg's expectation is cut to CAL x the NQ number in the weekly forward reads. This is
  reported to the owner through MANAGER.
- **CAL < 0.5:** the owner is told the live Webull NOISE leg keeps under half the NQ edge per dollar. A QQQ-own crown
  becomes a question for a NEW prereg; it is not run here.
- **CAL band crossing a line:** whichever side the point estimate is on, said with the band.

## Disclosed
- The live stack is #382 + KEEL v12. KEEL's daily size is out of scope; this reads the base leg only.
- The live box books one bar after the price it acts on, and once emitted exits a bar late (fixed 2026-09-22). This
  calibrates the ENGINE on QQQ, not the box; the box's own gap is the mistake-hunt finding (2026-10-05).
- QQQ's live size has varied (caps 60 / 80 since 09-24), so the live-size row uses the cap. It is not a forecast.

## What follows
A NOISE.md section, a ledger row and a RUNBOARD research row (report), then the sector funds (A2) per the queue.
