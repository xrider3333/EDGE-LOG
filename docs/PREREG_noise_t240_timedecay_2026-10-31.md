# PREREG - test 240: NOISE #382 time-decay trail Auto-Validate + regime-conditioned exits + vol-scaled partial

Owner GO 10-31 16:05 via MANAGER #150 (board row t240, was t76). Written and locked before any number below exists.
Lane: NOISE. ORB may run (b) and (c) on ORB #314 on this same file and rule; (a) is NOISE only.

## Why, and the prior
Tests 74 (giveback stop, 0 of 9), 75 (scale-out, 0 of 30) and 239 (5 trails, 0 of 5) found no exit that beats
holding NOISE #382 to its own exit. The time-decay trail came **4th of 5 out of sample** in 239 at one fixed setting.
Part (a) searches that family's settings instead of guessing them. A search over a family that failed at a fixed
setting has a LOW prior: **about 10%**. Parts (b) and (c) are new mechanisms the owner asked for (10-31: "NOISE and
ORB giving back on the SAME day says something is wrong"); prior about 15% each.

The same-day read that came first (tools/t240_giveback_days.py, posted to MANAGER #1901) found: the two legs give
back together on 5 of 626 shared days against 4.3 expected by chance; they sit on the SAME side on 85% of shared days;
giveback days show more late-day reversals (last 90 min: 23% vs 14%) and more closes back at the day's VWAP (30% vs
24%). That is why (b) gates the trail on a trend day, known by the time the trail would act.

## (a) Auto-Validate: NOISE #382 + time-decay ATR trail
- **File:** `augur_strategies/NOISE_1_8_CT304_TD.py` (`_AUGUR_PARENT` = `NOISE_1_8_CT304.py`). Core, entries and the
  size tilt are run #382's crown (tilt 2.0, gate 30 min / 16 / 1.15), fixed. Exit-only knobs, FULL ranges (not pinned):
  - `td_shape` off / linear / convex (**off = #382 exactly**, so hold is inside the search space)
  - `td_k_start` 2.0..5.0 step 0.5 ATRs (before the decay)
  - `td_k_end` 0.5..2.0 step 0.25 ATRs (at 16:00)
  - `td_atr` 7..28 step 7 bars
  - `td_start` 0..300 step 30 minutes after 09:30 (when the decay begins)
  - The trail ratchets from the trade's best close: set on bar j's close, acts from bar j+1, never loosens.
- **Parity (checked before queueing):** `td_shape=off` returns NOISE_1_8_CT304's trades at the #382 crown bit for bit
  (4,512 trades, 27,249.40 pts on 2010-06-07..2025-07-15). Against #382's STORED trades the WF-chain rebuild is ~0.5% off
  (two NT splices since #382 ran; tests 74/75/239) - that applies to every arm equally.
- **Job = run #382's own shape (pinned window AND master):** NQ 5m RTH, `db_noadj_rth` (NOADJ_NQ_5m_RTH.csv),
  2010-06-07..2026-07-16, 12-month lockbox (SPENT: veto / report only), 8 WF folds, warm 300, cost 0.533, mult 20,
  **900 trials** (owner rule), discover auto, oos_sample_k 30, mc 500. Queued behind test 196's job.
- **OOS read the owner asked for (IS 2010-21 / OOS 2022-26):** the engine's WF chain covers 2016-06..2025-07. The
  verdict is read on (1) the engine's WF chain and (2) the crowned config run once on 2010-06-07..2025-07-15 split at
  2021-12-31 (IS) / 2022-01-01..2025-07-15 (OOS), the lockbox never loaded - the same split as 239.
- **Reading rule (all must hold, else NO LIFT):**
  1. The crowned config has `td_shape` != off.
  2. It beats its own trail-off twin (#382) on OOS ROC@30k AND OOS Sortino.
  3. It wins at least 3 of the 4 OOS years AND at least 5 of 8 WF folds.
  4. Not one episode: worst DD <= 1.3 x DD5, or the same flag as the twin.
  5. Neighbours hold: the trail settings one step either side of the crown on each knob keep OOS ROC above the twin.
  6. The engine's own verdict is not FAIL.
- If the crown is `off`, the search itself says hold - the verdict is NO LIFT with no further reading.

## (b) Regime-conditioned trail (fixed grid, no search)
Trail only on a trend day, the gate known by the close of the bar the trail would act on (no look-ahead: the stop set on
bar j acts from j+1 only if the gate is true at bar j's close; once armed it stays armed for that trade).
- Gates:
  - **G1 range expansion:** session range so far (09:30..bar j) >= 1.0 x the prior 20 sessions' mean full-day range.
  - **G2 VWAP slope:** session VWAP at bar j minus VWAP 12 bars earlier, in the trade's direction, >= 0.10 x the prior
    20 sessions' mean range.
  - **G3 breadth (ES confirms):** ES 5m RTH (db_noadj_rth) is on the trade's side of its own session open at bar j's
    close (the only breadth series on file; stated as a proxy).
- Trails: **E1** ATR trail 3 x ATR14 from the best close; **E5** breakeven at 1R then 2 x ATR14 trail (239's two best).
- 3 gates x 2 trails = **6 cells**.

## (c) Partial at a vol-scaled target (fixed grid)
Close fraction F at target T = m x the prior 20 sessions' mean NQ day range (known at entry), the rest held to the
leg's own exit. The target fills at its level on bars e+1..x-1 only (never the entry bar; on the leg's exit bar the stop
comes first). One extra exit commission on the scaled part (F x cost / 2), as in test 75.
- m in {0.25, 0.50, 0.75} x F in {1/3, 1/2} = **6 cells**.

## Reading rule for (b) and (c) - test 239's, unchanged
On #382's crowned config run once 2010-06-07..2025-07-15 (lockbox never loaded), IS = to 2021-12-31, OOS = 2022-01-01..
2025-07-15. A cell LIFTS only if ALL hold: (1) beats hold on OOS ROC@30k AND OOS Sortino; (2) wins >= 3 of 4 OOS years;
(3) not one episode (worst DD <= 1.3 x DD5 or hold's flag); (4) beats hold on IS ROC@30k. 12 cells are tried: one pass
with the rest failing is reported as "1 of 12, check for chance". Second line (reported, not the verdict): the same
overlay on test 74's WF-chain rebuild. Columns also carry MFE captured and median giveback (R).

## Not done
No parameter re-tuned after numbers. No cell added after numbers. Nothing live, paper or in BOOK #463 changes on any
pass - a pass goes to MANAGER as a candidate with its four numbers. The lockbox is never loaded by (b)/(c); the
validate's lockbox is veto / report only.
