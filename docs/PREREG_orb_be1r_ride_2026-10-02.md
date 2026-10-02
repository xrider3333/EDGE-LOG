# PRE-REGISTRATION — ORB "breakeven at +1R, then ride" (ORB round 64, 2026-10-02)

Written and pushed before any figure for the new exit was computed. Owner idea via MANAGER inbox #20
(from the CBU review): once an ORB trade is up 1R, move the stop to entry, then let it run to the strategy's
normal exit or the close, instead of a fixed target. Test it on the crown #314 and on the control #234
(the ORB leg of the adopted BOOK #463).

## What the rule is, in the engine's own terms

`ORB_3_6.py` already has both pieces, so no new code touches the trade walk:
- `be_after_R` - the stop moves to entry once a 5-minute bar **closes** at or beyond entry + that many
  times the initial risk; it acts from the **next** bar. Only finished bars are read, so there is no
  intrabar peeking. Stops still fill stop-first, with gap-through fills.
- `target_R = 0` - no take-profit. The trade ends at its stop (initial or breakeven) or at the session's
  last close.

| arm | settings | its raw twin |
|---|---|---|
| **P1 - crown** | #314 with `be_after_R` 0.5 -> **1.0** and `target_R` 5.0 -> **0 (ride)** | #314 unchanged |
| **P2 - book leg** | #234 with `target_R` 5.5 -> **0 (ride)**; its breakeven is already 1.0R close-armed | #234 unchanged |

Reported only (they cannot pass or fail anything): the two halves of P1 on their own, D1 = #314 with
breakeven 1.0 and its 5.0R target kept, and D2 = #314 with breakeven 0.5 kept and no target. They show
which half does the work.

## Data, costs, windows

The house NQ 5-minute RTH master (`db_noadj_rth`), 2010-06-07 .. 2026-08-13, cost 0.533 points a round
trip, $20 a point, one contract, which is what runs #314 and #234 were validated on.
- **Walk-forward stretch** 2016-07-13 .. 2025-08-12 (the family's walk-forward years).
- **Lockbox** 2025-08-13 .. 2026-08-13 (the 12-month lockbox of #314 and #234).
- Both stretches are replays of fixed settings: the twins were chosen on these years, and the arms change
  only the exit, so neither stretch is a clean out-of-sample test. That is why the Auto-Validate step below
  exists.
- **Parity first.** Each twin must reproduce its run's stored lockbox to 0.01 points (#314: 168 trades,
  4,605.081 points; #234: 178 trades, 4,447.126 points) or the round stops.

## The yardstick (owner rule 2026-09-28, unified convention 2026-09-30)

ROC %/yr at a $30k worst drawdown = 30 x (net / years) / worst drawdown, with net and drawdown taken from
the daily P&L inside each stretch (an ORB trade opens and closes the same session, so closed-trade daily
P&L is the daily valuation), and years = (last day - first day) / 365.25 of that stretch's session
calendar. Daily Sortino = mean / downside deviation x sqrt(252) over every session in the stretch
(non-trading sessions count as $0).

## The bar (per arm against its twin; all four must hold)

1. ROC at a $30k drawdown **higher in the walk-forward stretch AND the lockbox**;
2. daily Sortino **higher in both**;
3. at least 100 walk-forward trades and 50 lockbox trades;
4. the arm's lockbox stays **profitable without its single biggest trade**.

The known trap: a breakeven rule shrinks the average loss and so flatters every R-based figure (EV R,
R/YR, win/loss ratio) while it can lose money. **R figures are printed only to show that trap. They never
judge.**

Reported beside the bar, not gating: net dollars and drawdown in each stretch; money by calendar year
against the twin (2011-2025); how often the twin's target was hit; the paired per-trade difference and its
t-statistic; R figures (average loss, scratch count). For P2, BOOK #463 with its ORB leg swapped to the arm,
on the same convention, against the book reference WF 93.8 / LB 155.5 with round 63's book bar (ROC both,
Sortino both, not behind by calendar year 2011-2025). A book swap is always the owner's call.

## What happens next

- **An arm that clears the bar** goes through the house Auto-Validate on the runner. The validate file fences
  narrow open ranges around the arm (target pinned OFF; breakeven 0.8 / 1.0 / 1.2; stop, breakout buffer and
  both filters one step either side). It runs on the pinned window 2010-06-07 .. 2026-08-13 with a 12-month
  lockbox, the 900-trial budget, and ES transfer. It is read for the **region**: folds held, re-fitted
  walk-forward ROC at $30k against #314's 21.7, PBO, and the lockbox. The forward candidate is the frozen arm
  cell, never the validate's crowned cell (re-tuning ORB picked a worse cell in #421 and #480). If the region
  passes, the arm becomes an owner call for a no-order paper shadow beside its twin.
- **An arm that fails** is written up DEAD for that seat. It goes on the RUNBOARD watch list only if a
  validate ran.

Tool: `tools/orb_r64_be1r_ride.py` (run from the shared checkout). Results: `ORB_ROUND64_BE1R_RIDE.md`.

## Addendum 1 (2026-10-02, after the parity step, before any arm figure)

The first run stopped at parity: #314's twin gave 168 lockbox trades and 4,356.581 points against the stored
4,605.081. ORB.md already records why - #314's stored lockbox was measured before the v73.841 warm-start fix
(its indicators started cold at the lockbox's first bar) and reads about 5% high. A cold replica (data starting
2025-08-13) reproduces the stored 168 trades / 4,605.081 points exactly, and #234 reproduces 4,447.126 both
ways. So the parity check now runs the cold replica against the stored figure, and the round itself uses the
warm, corrected series (data from 2010-06-07) for every twin and arm. Nothing else changes; no arm had been
run.
