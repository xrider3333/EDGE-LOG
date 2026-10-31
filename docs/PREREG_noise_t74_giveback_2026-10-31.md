# PREREG - test 74: NOISE #382 MFE giveback stop (owner GO 10-31, MANAGER #143)

Written and pushed BEFORE any giveback stop is simulated. Only the descriptive pass (MFE / MAE / giveback per trade) has been
read. Tool: `tools/noise_t74_giveback.py` (`describe`, then `grid`).

## Question
NOISE #382 often gives back what it shows: on 10-30 the Webull short ran +8.58 $/share in its favour and closed +0.74. Does
a stop that locks part of the open profit, once there is enough of it, beat the leg's own exits (VWAP cross, bandwidth stop,
flat at the close)? This is the GIVEBACK question, not a target: targets are closed (#490, shelf 39/41, 10-18 re-reads).

## Already seen (descriptive, no stop simulated)
- Webull #382, 62 closed trades (box backup 2026-10-30, QQQ 1m): median MFE 0.64, median giveback 1.65 $/share; 42 of 62
  were up at some point and closed flat or down.
- #382 WF chain rebuilt on today's NQ 5m RTH master, 2,345 trades: MFE >= 0.5R on 37% of trades, >= 1R on 21%,
  >= 1.5R on 12%; median giveback 0.47R. (R = the entry's own bandwidth-stop distance.)
- Rebuild drift: 2,345 trades / 20,074 pts against the stored 2,343 / 19,975 (0.5%); folds 3 and 5 exact. Fold bounds were
  moved past the two NT splices (2020-02-28 +60 bars, 2020-06-30 +69). Both arms use the SAME rebuilt trades, so the
  comparison is like-for-like; the chain's absolute numbers are not #382's stored ones.

## The rule (fixed)
Once the running MFE >= **Y x R**, a stop sits at entry + side x (1 - X) x MFE. MFE is measured through bar j; the stop acts
from bar j + 1 (no intrabar look-ahead). Open through the stop = fill at the open; touch = fill at the stop. On the leg's own
exit bar it acts only when that exit is not at the bar's open. The leg's size tilt and cost (0.533 pts a contract) are kept.

## Grid (9 cells, nothing else runs)
Y in {0.5, 1.0, 1.5} R  x  X in {33%, 50%, 67%} of the MFE given back. Twin = HOLD (the leg as is).

## Stretch and numbers
WF chain only, 2016-06-30 .. 2025-07-15 (8 anchored folds, crown params per fold). **Lockbox never loaded** (the tool loads
data only to the optimize end). Four numbers per cell from `augur_engine.drawdowns.four_numbers` on daily $ (x20):
ROC@30k, DD5, DD% from peak, Sortino; plus folds won against HOLD and trades changed.

## Reading rule (mirrors #422 TP)
A giveback stop is a LIFT only if ALL hold for the best cell by WF ROC@30k:
1. It beats HOLD on WF ROC@30k AND WF Sortino.
2. Not one episode: it wins at least 5 of 8 folds on net $, AND its worst DD <= 1.3 x its DD5 (or the one-episode flag equals HOLD's).
3. Its grid neighbours (same Y with the adjacent X, same X with the adjacent Y) also beat HOLD on ROC@30k.
Else: NO LIFT. Prior about 15% (every exit/target cut on NOISE so far has failed).
A lift is a draft only: it goes to a pinned 900-trial validate, never straight to the live leg. Nothing live changes.
