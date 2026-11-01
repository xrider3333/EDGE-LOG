# PREREG - M6 peak-age validate on NOISE #382 (board t82, owner 11-01 via MANAGER #159)

Written and locked BEFORE any number of this read is computed. Lane: NOISE.

## Question
Test 245's one survivor: M6 "stalled runner" exit (once the trade's best open profit reaches 0.5 R, exit when 10
closed 5m bars pass with no new best) helped both the washout trades (+$3,463/yr) and everything else (+$1,228/yr) on
#382's chain overlay. Does it hold up as a FRESH ENGINE run, and does it beat a plain time exit of the same length?

## The doubt, stated up front (MANAGER #159)
A 10-bar stall rule on an 8-bar median hold may be a time exit wearing a trail's clothes. So M6 must beat a TIME-EXIT
CONTROL ("exit after 10 bars", same weight), not only hold. The lead was found on the same tuned chain trades
(tests 244/245, best of many cells), so this read can only kill it or keep it alive; it cannot confirm it. Only
forward trades (or a lockbox read the owner orders) can.

## Cells (5, fixed; no grid, no tuning)
| cell | pa_mode | pa_n | pa_arm_r | pa_weight |
|---|---|---|---|---|
| HOLD | off | - | - | - |
| M6 w0.50 | peak_age | 10 | 0.5 | 0.50 |
| M6 w1.00 | peak_age | 10 | 0.5 | 1.00 |
| TIME w0.50 | time_exit | 10 | - | 0.50 |
| TIME w1.00 | time_exit | 10 | - | 1.00 |

Strategy file `augur_strategies/NOISE_1_8_CT304_PA.py` (`_AUGUR_PARENT` = `NOISE_1_8_CT304.py`), rule copied from
`C:\EdgeLog\_anatomy_cache\t244_lock2\lock2.py` `m6_peakage`: running best from bar highs/lows, read at a bar's close,
filled at the next bar's open, never on or after the leg's own exit bar. Time control: exit at the open of bar entry+10
when that is before the leg's own exit. Weight w = fraction of size on the variant exit, the rest holds (test 245:
lot count is a weight; no extra commission charged, cost per contract unchanged at #382's 0.533 pts).

## Data / runs
- PRIMARY: #382's own WF chain, 8 folds, each fold re-run through the engine (`augur_engine.engine.run_backtest`) with
  the PA strategy file and that fold's own champion params (test 74's chain loop, same splice mapping). Master and
  window pinned to run #382's (NQ 5m RTH, its data source, date_from .. optimize end 2025-07-15).
- PARITY GATE first: pa_mode off must reproduce the chain rebuild trade for trade (count and pts) - the same rebuild
  tests 74-245 used (about 0.5% off #382's stored trades; stated, both arms on the same trades).
- SECOND LINE (descriptive, not the verdict): #382's crown run once 2010-06-07 .. 2025-07-15, IS to 2021-12-31,
  OOS 2022-01-01 .. 2025-07-15 (test 239's split).
- LOCKBOX (2025-07-16 .. 2026-07-16) NEVER LOADED.

## Measures (per cell, WF chain)
Four numbers from `augur_engine.drawdowns.four_numbers` on daily $ (every session present, zero days included):
ROC@$30k, DD5, DD% from peak, Sortino; plus net $, folds won vs HOLD (fold net > HOLD's fold net), trades changed,
share of best open profit kept, one-episode flag.

## Reading rule (fixed now)
An M6 cell is a LIFT only if ALL hold at the same weight:
1. beats HOLD on WF ROC@30k AND WF Sortino;
2. wins >= 5 of 8 folds against HOLD;
3. not one episode (worst DD <= 1.3 x DD5, or HOLD's flag unchanged);
4. beats the TIME control at the same weight on WF ROC@30k AND WF Sortino.
Prior: ~15%. If M6 passes 1-3 but fails 4, the verdict is "a time exit in disguise" and the exit side of tests
242-247 closes. If it passes all four, it is the first real exit lift of the MFE thread; the next step would be a
full-range Auto-Validate on the ranged PA file (drafted, not queued, until the owner says go). Nothing live changes
from this read either way.
