# PRE-REGISTRATION - ROUND r1: stop cascades at round NQ prices (new strategy type 2 of 3, MANAGER #40)

Drafted 2026-10-05 by the NOISE lane BEFORE any real-direction number exists. The only number computed is the power
line below, from a coin-flip leg on the primary's trade schedule. Harness: `tools/round_r1_stageA.py` (only its
`--power` mode has run). It reuses the HALFHOUR r1 loaders and bars (`tools/halfhour_r1_stageA.py`).

## Mechanism (theory and literature)
Traders place resting orders at round prices. Osler (2003, Journal of Finance; 2005, Journal of International Money and
Finance) read the order books of a large dealer and found two clusters:
- **Take-profit orders sit AT round numbers.** A trend that reaches one without crossing tends to stop or turn.
- **Stop-loss orders sit just BEYOND round numbers.** A trend that crosses one tends to accelerate as the stops fire
  (a "price cascade").

Equity versions: Donaldson & Kim (1993) on Dow levels at round hundreds; Bhattacharya, Holden & Jacobsen (2012) on
buy-sell imbalance around round prices.

NQ is a market where many discretionary and retail traders place stops by hand on a futures price they watch. The
question is whether crossing a multiple of 100 points carries momentum that crossing an arbitrary level does not.

## What is different (one line), and the dead families it is not
**Every dead level family on EL used levels the tape made. These levels are fixed by arithmetic, and the null moves
the same grid off the round numbers.**
- Tape-made levels already dead: prior-day high/low and value area, opening range, overnight and weekly range, Asia and
  London range, VWAP, failed new high of the day.
- Round numbers on EL so far were only a FILTER on ENGU-Q trades (ENGUQ.md anatomy, p 0.97), never a strategy.
- Not a NOISE re-size. Every NOISE lever in rounds 63-70 is dead: pyramid, half-hour checkpoints, delta, time stop,
  ES confirmation, overnight clearance, breakeven, tilt depth, short tilt.
- HALFHOUR r1 (type 1) is a clock signal; this is a price-level signal.

## Rules (frozen)
**Data.**
- NQ 5m RTH no-adjust master (id 37): the RAW front-month price, the one traders put stops on. Never the roll-adjusted
  one, whose levels are shifted.
- Loaded 2010-06-07 .. 2025-06-29 with date_to pinned. Trades counted only in 2016-07-01 .. 2025-06-29.
- Sessions without a 15:55 bar are dropped.
- Signals compare two closes in the same session, so a roll seam can never make a cross.

**CROSS (primary).** A 5m bar starting 09:35 .. 15:20 CLOSES across a multiple of G, with the previous bar's close (same
session) on the other side. Trade 1 NQ in the crossing direction:
- in at the next bar's open;
- out H minutes later at a bar close, or at the 15:55 bar's close if sooner;
- no stop; one position at a time per cell;
- $20 a point, 0.533 point per round trip.

**REVERSE.**
- A bar's high reaches the multiple of G above the previous close, but the bar closes below it: sell.
- Or its low reaches the multiple below and it closes above it: buy.
- Same entry and exit as CROSS.

**Cells (4).**
- CROSS G100 H30 = PRIMARY.
- CROSS G100 H60 and CROSS G50 H30 = neighbours.
- REVERSE G100 H30 = Osler's other half, in the family. It raises the null's bar but cannot pass on its own.

**Family null.**
- The same four cells on a grid shifted OFF the round numbers: offset f x G, with f drawn uniformly from 0.1 to 0.9,
  200 draws, one f per draw for all four cells, seed 20261005.
- Same volatility, same trend content, same crossing rate. Only the roundness is removed.
- Statistic: the family MAX of own ROC@$30k.

## Where it sits on the MDL map (docs/MDL_MAP_R1.md)
- CROSS trades with short-term momentum. On trend days it may share direction with ORB and NOISE, so its drawdown-week
  correlation with #463 could be mild rather than zero.
- It sits on the "uncorrelated" row (about $15k a year at a $30k own drawdown), with that caveat.
- Its P&L in #463's worst walk-forward weeks (2020-03-02 .. 03-27) is reported.

**Trade count (direction-free) for the primary:** 6,650 walk-forward trades, 739 a year. By calendar year: 2016 115
(half year), 2017 194, 2018 478, 2019 376, 2020 886, 2021 823, 2022 1,244, 2023 882, 2024 1,029, 2025 623 (half year).
A 100-point step is a bigger move at 4,500 than at 21,000, so the early years are thin and the result leans on 2020-2025.

**Prior: weak.**
- Stops in a market this deep are absorbed fast, and EL's dead list says the NQ intraday tape is mined.
- Momentum on ANY level cross is already known to be positive (intraday continuation beats reversion), which is exactly
  why the null keeps it and removes only the roundness.

## POWER LINE (written before any real-direction run; house rule MANAGER #37)
- Coin-flip directions on the primary's schedule, scaled to a $30k own drawdown and added to #463's walk-forward daily.
  Paired stationary bootstrap, mean block 20, 1,000 draws.
- SD of the book-add ROC@$30k lead: 6.3 points.
- MINIMUM DETECTABLE lead: 10.3 points (5% line). Four times in five: 15.6.
- So, as for HALFHOUR, the bootstrap is the binding gate, not the 98.50 book bar (+4.7). A real leg must lift #463 by
  about 10 points to have even odds.

## Stage A bars (walk-forward only; all four must pass)
- **A1 own:**
  - primary own ROC@$30k >= 15;
  - PF > 1;
  - >= 100 trades and >= 50 a year;
  - >= 6 of the 9 July-June years positive.
- **A2 null:** primary own ROC@$30k above the 95th percentile of the off-round null's family max.
- **A3 neighbours:** both CROSS neighbours net positive after cost.
- **A4 book add:**
  - primary scaled to a $30k own walk-forward drawdown and added to #463's walk-forward daily (parity 93.81 / 3.816
    asserted);
  - book ROC@$30k >= 98.50 with Sortino >= 3.816;
  - paired bootstrap 5th percentile of the lead > 0.

## What follows
- **PASS:** the same day, a ROUND_1_0 plugin (harness parity to the trade first), then a pinned Auto-Validate (date_from
  2010-06-07, date_to 2026-07-16, 900-trial budget over G and H). The Auto-Validate lockbox is its own first look.
- **FAIL:** recorded dead; no other grid or horizon is tried.
- **Either way:** a RUNBOARD research verdict with ROC@$30k and DD%, a RESEARCH_LEDGER row and a NOISE.md note. Nothing
  live or in the adopted book changes without the owner.
