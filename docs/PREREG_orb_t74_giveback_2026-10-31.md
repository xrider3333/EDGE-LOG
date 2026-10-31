# PREREG - test 74, ORB half: ORB #314 MFE giveback stop (owner GO 10-31, MANAGER #144 / ORB #125)

Addendum to `docs/PREREG_noise_t74_giveback_2026-10-31.md` (NOISE #382 half): same question, same rule, same grid, same
reading rule, applied to ORB #314. Written and pushed BEFORE any giveback stop is simulated on ORB and before the ORB
descriptive pass (MFE / MAE / giveback) is read. Tool: `tools/orb_t74_giveback.py` (`describe`, then `grid`).

## Question
The 10-23 Webull ORB long ran +4.76 pts (NQ-equivalent) in its favour, the breakeven stop armed at 10:50, and the 15:30 time
exit closed it at +0.19. Does a stop that locks part of the open profit, once there is enough of it, beat #314's own exits
(protective stop, breakeven after 0.5R, 5R target, flat at the close)? GIVEBACK question, not a target.

## The leg (HOLD twin)
ORB #314 = `ORB_3_6_R6.py` on NQ 5m RTH (`db_noadj_rth`), 0.533 pts a round trip, one contract, x20. Its WF chain: 8 anchored
folds 2016-07-13 .. 2025-08-12, each fold's crown params as stored on the run (stored: 1,203 trades / 12,627.4 pts).
HOLD = the leg exactly as is.

## The rule (fixed, identical to NOISE's)
R = the entry's own protective-stop distance (ORB `levels[].risk`). Once the running MFE >= **Y x R**, a stop sits at
entry + side x (1 - X) x MFE. MFE is measured through bar j; the stop acts from bar j + 1 (never the bar that made the MFE).
Open through the stop = fill at the open; touch = fill at the stop. On the leg's own exit bar it acts only when that exit is
not at the bar's open. Cost (0.533 pts) is kept on every trade. The leg's own stops still act first where they already would
(the simulation only ever exits EARLIER than HOLD, never later).

## Grid (9 cells, nothing else runs)
Y in {0.5, 1.0, 1.5} R  x  X in {33%, 50%, 67%} of the MFE given back. Twin = HOLD.

## Stretch and numbers
WF chain only. **Lockbox never loaded** (data loaded only to the optimize end, 2025-08-12). The chain is rebuilt from the
stored per-fold params and parity-checked fold by fold against the stored OOS net / trades; any drift is reported, and both
arms use the SAME rebuilt trades. Four numbers per cell from `augur_engine.drawdowns.four_numbers` on daily $ (x20):
ROC@30k, DD5, DD% from peak, Sortino; plus folds won against HOLD and trades changed.
Descriptive, not scored: giveback histogram of the 14 Webull ORB trades (box backup 2026-10-30, QQQ 1m) and of the chain.

## Reading rule (same as NOISE's)
A giveback stop is a LIFT only if ALL hold for the best cell by WF ROC@30k:
1. It beats HOLD on WF ROC@30k AND WF Sortino.
2. Not one episode: it wins at least 5 of 8 folds on net $, AND its worst DD <= 1.3 x its DD5 (or the one-episode flag equals HOLD's).
3. Its grid neighbours (same Y with the adjacent X, same X with the adjacent Y) also beat HOLD on ROC@30k.
Else: NO LIFT. Prior about 15%: ORB re-optimising, target and exit cuts have not paid (ORB_NOTHING_BEATS_LEAVING_IT_ALONE,
shelf 39/41, BE/ride rounds 64). A lift is a draft only: pinned 900-trial validate next, never straight to the live leg.
Nothing live changes.
