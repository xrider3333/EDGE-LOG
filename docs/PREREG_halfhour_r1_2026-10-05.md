# PRE-REGISTRATION - HALFHOUR r1: same-half-hour seasonality on NQ (new strategy type 1 of 3, MANAGER #40)

Drafted 2026-10-05 by the NOISE lane BEFORE any real-direction number exists. The only number computed so far is the
power line below, from a coin-flip leg (random directions on the primary's trade schedule).
Harness: `tools/halfhour_r1_stageA.py` (its `--power` mode is the only mode run).

## Mechanism (theory and literature)
Some institutions trade on a fixed clock: the same half-hour, day after day, for weeks. Examples are pension and
index rebalancing spread over sessions, execution algorithms that slice one big order across many days, and fund-flow
trades at fixed times. That leaves a return footprint that repeats at the SAME half-hour on later days.

- Heston, Korajczyk & Sadka (2010, Journal of Finance): in US stocks a half-hour's return predicts the same half-hour's
  return for 40+ trading days. Half-hours at other times of day do not predict it.
- Bogousslavsky (2016, Journal of Finance): infrequent, periodic rebalancing produces exactly this pattern.

The question here is whether the market-wide part of those flows shows in NQ futures, large enough to pay a 0.533-point
round trip.

## What is different (one line), and the dead families it is not
**Every dead intraday family on EL reads today's tape or the calendar. This one reads only the same clock slot on
earlier days, which is information independent of today's price path.**

Dead and not re-tested, checked against the ledger:
- Gaps, fade and go (2.5, family-seed hunt).
- Event days and releases (2.5, 2.6).
- Last-hour momentum (2.5).
- Overnight and European-morning drift (2.13, 2.15).
- Leveraged-ETF close flow (2.14).
- NQ-vs-ES spread (2.24, 2.45).
- Failed-high fade and post-close reversal (2.38, 2.41).
- Breadth (2.48).
- Weekend, FOMC weeks and earnings nights (IDEAS_R4 1-3).
- Every NOISE re-size, rounds 63-70: pyramid, half-hour entry checkpoints, order-flow delta, time stop, ES
  confirmation, overnight clearance, breakeven, tilt depth, short tilt.
- The closest relative is the standalone xgboost model (2.17). It had a static time-of-day feature refit yearly and no
  same-slot lagged returns, so it could not see this.
- IDEAS_R4 #8 listed this exact idea and did not run it ("expected cost-dead"). That prior is restated below and is the
  reason for the z thresholds.

## Rules (frozen)
**Data**
- NQ 5m RTH no-adjust master (id 37), loaded 2010-06-07 .. 2025-06-29 with date_to pinned. Nothing later is in memory.
- Bars are start-stamped 09:30 .. 15:55.
- Sessions without a 15:55 bar (half days, broken sessions) are dropped whole.
- Roll seams cannot touch a slot (every slot sits inside one session).

**Slots and returns.** There are 13 half-hours (09:30-10:00 .. 15:30-16:00). Slot return = close of its 6th 5m bar minus
open of its 1st, in points. A slot with any missing bar is invalid in both history and trading.

**Signal, using only sessions before today**
- S = mean of that slot's previous L valid returns.
- t = S / (SD of its previous 250 valid returns / sqrt(L)).
- No signal until 250 valid observations exist.

**Trade**
- If |t| >= z, trade 1 NQ in the sign of S, from the slot's first open to its last close.
- No stop.
- $20 a point, cost 0.533 point per round trip.
- Trades are counted only from 2016-07-01 to 2025-06-29 (#463's walk-forward stretch).

**Cells (4).** The PRIMARY is L 40, z 1.0. The neighbours are (L 20, z 1.0), (40, 2.0) and (20, 2.0).

**Family null**
- The same four cells, with slot h trading on the signal of a DIFFERENT slot.
- 200 random derangements of the 13 slots, seed 20261005.
- This keeps recent market drift and trade density, and removes only the same-slot alignment the mechanism claims.
- Statistic: the family MAX of own ROC@$30k across the four cells.

## Where it sits on the MDL map (docs/MDL_MAP_R1.md)
- It is long and short every day, with no trend or volatility condition. Its drawdown-week correlation with #463 should
  therefore be near zero.
- That puts it on the map's "uncorrelated" row: about $15k a year at a $30k drawdown of its own to lift the walk-forward
  past 98.5 half the time.
- It is not a drawdown-week earner by design. Its P&L in #463's worst walk-forward weeks (2020-03-02 .. 03-27) is
  reported, not barred.
- Prior: probably cost-dead.
  - The primary trades about 920 times a year, so cost alone is about $9.8k a year per NQ.
  - The edge needs more than about a 0.02 correlation between a slot's trailing mean and its next return.

## POWER LINE (written before any real-direction run; house rule MANAGER #37)
- Method: coin-flip directions on the primary's schedule (8,290 walk-forward trades, 922 a year), scaled to a $30k own
  drawdown, added to #463's walk-forward daily.
- Paired stationary bootstrap, mean block 20, 1,000 draws.
- The SD of the book-add ROC@$30k lead is 7.8 points.
- The MINIMUM DETECTABLE lead is 12.9 points (5% line); clearing the bar four times in five needs 19.5.
- So the bootstrap, not the 98.50 book bar (+4.7), is the binding gate. A real leg must lift #463's walk-forward by about
  13 points to have even odds. That is more than the map's $15k-a-year leg delivers, so a pass needs a leg of roughly
  $25-30k a year at a $30k own drawdown.

## Stage A bars (walk-forward only; all four must pass)
- **A1 own:**
  - Primary own ROC@$30k >= 15 (the map's $15k a year at a $30k own drawdown).
  - PF > 1.
  - >= 100 trades, and >= 50 a year.
  - >= 6 of the 9 July-June years positive.
- **A2 null:** primary own ROC@$30k above the 95th percentile of the wrong-slot null's family max.
- **A3 neighbours:** all three are net positive after cost.
- **A4 book add:**
  - The primary is scaled to a $30k own walk-forward drawdown and added to #463's walk-forward daily (parity 93.81 /
    3.816 asserted first).
  - The combined book's ROC@$30k must be >= 98.50 with Sortino >= 3.816.
  - The paired bootstrap 5th percentile of the lead must be > 0.

## What follows
- **PASS:** the same day, a HALFHOUR_1_0 plugin is built (harness parity to the trade first), then a pinned Auto-Validate
  (date_from 2010-06-07, date_to 2026-07-16, 900-trial budget over L and z). The Auto-Validate lockbox is this new
  strategy's own first look (allowed by MANAGER #40). Book adds are judged forward.
- **FAIL:** recorded dead with no variants, and no other slot length or lookback is tried.
- **Either way:** a RUNBOARD research verdict with ROC@$30k and DD%, a RESEARCH_LEDGER row and a NOISE.md note. Nothing
  live or in the adopted book changes without the owner.

## AMENDMENT 1 - MANAGER review #44 + house line #45 (2026-10-05 ~08:10 MST, before any real-direction run)
- **The bars that decide (house line #45).** The standalone bars decide the pinned Auto-Validate and the RUNBOARD row.
  - **A1:** own ROC@$30k >= 15, OR the earner route, plus PF > 1, >= 100 trades and >= 50 a year, and >= 6 of 9 years.
    The earner route is own ROC@$30k >= 5 AND positive P&L in #463's worst walk-forward drawdown (peak to trough on its
    daily series, computed), also without the leg's 3 best days in that window.
  - **A1b no-2020:** the same route still holds with calendar 2020 removed. This is my reading of #45's "no-2020";
    MANAGER may correct it.
  - **A2:** wrong-slot family null.
  - **A3:** neighbours.
- **A4 becomes a REPORT.** It decides only whether a forward BOOK shadow line is also opened.
- **A4 sizing (#44 edit 1).** The leg is scaled by VOLATILITY, not by the outcome: its daily SD over the first two WF
  years (2016-07-01 .. 2018-06-30) is set to 25% of #463's daily SD on the same days. The $30k-own-drawdown version is
  reported as the twin. Power lines, recomputed BEFORE the run with the same coin-flip leg:
  - **VOL scale (x0.715 NQ):** SD 19.3; minimum detectable 31.8; four in five 48.0.
  - **$30k own drawdown (x0.180 NQ):** SD 7.8; minimum detectable 12.9; four in five 19.5.
- **Overlap report (#44 edit 2).** On HALFHOUR's held 5m bars, the share on which ORB #314 or NOISE #422 holds the SAME
  side, and the share on which it holds the opposite side. ENGU-Q (1m ETH) and TTM (ES) are not included. Also the
  dollars per slot.
- **Mechanism check (#44 edit 3, report only).** The primary restricted to the mid-day slots (10:00 .. 15:30) beside all
  13. If a pass lives only in the 09:30 or 15:30 slot, it is read as the known open or close effect, not the
  fixed-clock story.
- Unchanged: cells, signal, null, cost, stretch, and no variants on a fail.
