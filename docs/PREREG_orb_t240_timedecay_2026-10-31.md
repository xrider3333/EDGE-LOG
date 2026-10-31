# PREREG - test 240, ORB half: time-decay trail Auto-Validate on ORB #314 (owner GO 10-31, MANAGER #132)

Written, locked (`tools/prereg_lock.py`) and pushed BEFORE the validate is queued. NOISE runs the same study on NOISE #382.

## Question
Test 239 Phase B tried ONE fixed time-decay trail (E4: 3 x ATR(14), tightening to 1 x ATR into the close) on ORB #314 and it
lost OOS (ROC@30k 9.3 vs hold 77.9). The owner asks whether a time-decay trail with its knobs SEARCHED (not fixed) can beat
hold. This is that search, with the full walk-forward machinery, so the knobs are chosen inside each fold, never on OOS.

## Strategy file
`augur_strategies/ORB_3_6_R6_TD.py` (`_AUGUR_PARENT = ORB_3_6_R6.py`). Every #314 knob PINNED at #314's champion (or 2,
First-candle dir, stop 2.5, buffer 0.25, close-confirm on, breakeven 0.5R, target 5R, ATR filter 0.75, pace 0.8, flat at the
close, skip holidays). Checked before the lock: with the trail switched off (k = 99) the file reproduces the parent exactly
(2,134 trades / 15,672.8 pts after cost, 2010-06-07 .. 2025-08-12).
Open knobs (the only search space):

| Knob | Range |
|---|---|
| td_k_start (trail width at the start, x ATR) | 2.0 .. 5.0 step 0.5 |
| td_k_end (trail width at the close, x ATR) | 0.5 .. 2.0 step 0.25 |
| td_atr_len (bars) | 8 .. 30 step 2 |
| td_shape | linear, sqrt, square |
| td_start_min (decay starts, minutes after the open) | 0 .. 300 step 30 |

Rule: stop = best close since entry - k(t) x ATR; k holds at td_k_start until td_start_min, then decays to td_k_end at
16:00 by the shape. Level set on a bar's close acts from the next bar; never on the entry bar; open-through = open fill,
touch = level; the leg's own exits still apply; on the leg's exit bar the worse fill is taken.

## The run
One Auto-Validate, **900 trials** (never fewer), WF on, the SAME master and window as #314: NQ 5m RTH `db_noadj_rth`, cost
0.533 pts, x20, date_from 2010-06-07, date_to 2026-08-13 with the normal 12-month lockbox (optimize end 2025-08-12; the
lockbox is the validate's own veto-only read, nothing else reads it). Queued behind test 196.

## Hold
ORB #314's own stored WF chain: ROC@30k, DD5, DD% from peak, Sortino on daily $ from `augur_engine.drawdowns.four_numbers`
(test 238's rebuild: ROC@30k 26.39, DD5 $24,234, DD% 22.1, Sortino 1.85, 8 folds; fold 4 drifts by the 2020 splices).

## Reading rule (fixed now)
The trail LIFTS ORB only if ALL hold on the validate's WF chain vs hold:
1. It beats hold on WF ROC@30k AND WF Sortino.
2. It wins at least 5 of 8 folds on net $, and its worst DD <= 1.3 x its DD5 (or the same one-episode flag as hold).
3. The lockbox does not veto (lockbox net > 0 and not worse than #314's lockbox by more than its own WF fold spread).
4. The landscape agrees: the chosen knobs sit on a plateau (the validate's neighbourhood / PDP read), not a lone spike.
Else NO LIFT. Prior about 10%: tests 238 and 239 (giveback, scale-out, five trails) all failed on ORB.
A lift is a proposal for a forward shadow, never a live switch. Nothing live changes.
