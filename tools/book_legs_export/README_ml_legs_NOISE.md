# NOISE ML legs for the combined frontier-book test (2026-09-27, Custom ML chat)

Built by `tools/export_noise_ml_legs.py`. Tape: NQ 5m RTH NO-ADJUST master (db_noadj_rth), 2010-06-07 ..
2026-09-16, cost 0.533 pts, $20/pt. NOISE is flat by the close, so no trade crosses a contract roll and
no-adjust P&L is exact; roll-corrected masters exist (FADJ_/ADJ_) and were not needed.
Stages by ENTRY date: IS < 2016-06-30 <= WF < 2025-07-16 <= LB (the round-60 stretches).

Files per leg: `<LEG>_trades.csv` (entry_time, exit_time, side, pnl_usd, size, stage) and `<LEG>_daily.csv`
(date, pnl_usd, trades, size, stage; one row per session with a trade; daily sums equal the trade file).
`size` = total contract multiple (the strategy's own sizing x the overlay).

Legs: NOISE422_raw (run #422, NOISE_1_8_CT304H.py 20/1.15/1.75x) - NOISE422_fixed (+ compression 1.5x, Friday
1.5x, cap 3, FOMC pre-statement 0.5x, no model) - NOISE422_keel_s42 - NOISE422_keel_bag7 (mean of seeds
90001-90007) - NOISE382_raw (run #382, NOISE_1_8_CT304.py 30/16/1.15/2.0x) - NOISE382_keel_s42 (the live stack).

FREEZE: IS/WF sizes from KEEL v12's causal walk (leak-fixed engine, 85be1b8+); LB sizes scored by a model
FROZEN at 2025-07-16 (keel_build_state on pre-LB trades, keel_score_from_state per LB trade), so no lockbox
trade trains the model that sizes another. These LB figures therefore differ slightly from the walk-forward-
refit ones quoted earlier (docs/PREREG_keel_422_parts_2026-09-27.md).

OWNER'S YARDSTICK (ML is an edge when it beats raw at matched drawdown out of sample):

| leg | stretch | raw ret/DD | ML ret/DD | raw Sortino | ML Sortino | raw net $ | ML net at raw's DD $ |
|---|---|---|---|---|---|---|---|
| NOISE #422 fixed | WF | 2.82 | 3.63 | 4.49 | 5.48 | 448,732 | 578,154 |
| NOISE #422 fixed | LB | 3.15 | 3.36 | 3.67 | 3.86 | 82,488 | 87,969 |
| NOISE #422 keel_bag7 | WF | 2.82 | 2.64 | 4.49 | 4.97 | 448,732 | 421,113 |
| NOISE #422 keel_bag7 | LB | 3.15 | 4.15 | 3.67 | 4.05 | 82,488 | 108,744 |
| NOISE #422 keel_s42 | WF | 2.82 | 2.60 | 4.49 | 5.04 | 448,732 | 413,631 |
| NOISE #422 keel_s42 | LB | 3.15 | 4.24 | 3.67 | 4.17 | 82,488 | 111,223 |
| NOISE #382 keel_s42 | WF | 2.67 | 2.60 | 3.87 | 4.22 | 505,314 | 492,639 |
| NOISE #382 keel_s42 | LB | 2.33 | 3.90 | 2.95 | 3.79 | 90,675 | 151,716 |
| NOISE #382 fixed | WF | 2.67 | 3.12 | 3.87 | 4.84 | 505,314 | 591,988 |
| NOISE #382 fixed | LB | 2.33 | 3.13 | 2.95 | 3.26 | 90,675 | 121,892 |

## For the combiner (Frontier's PREREG_R61 asks)
- DATE: the ET SESSION date of the trade's ENTRY bar (US/Eastern, RTH). NOISE is flat by 16:00 ET, so entry
  date = exit date and there is no overnight mark; this is NOT the engine's UTC-truncated exit stamp.
- MASTER: NQ 5m RTH no-adjust (db_noadj_rth) for every NOISE leg. No trade holds across a session, so no
  roll carry is in any P&L; roll-corrected masters were not needed.
- SIZE: 1 NQ contract base ($20/pt, cost 0.533 pts). The `size` column is the TOTAL multiple (the strategy's
  own compression sizing x the overlay) - e.g. #382 raw already trades 2.0x in compressed 30-min groups and
  #422 raw 1.75x in compressed hours. Scale linearly if the book carries a different base.
- STAGES: labelled on the round-60 stretches (IS < 2016-06-30 <= WF < 2025-07-16 <= LB). Every trade from
  2010-06-07 to 2026-09-16 is in the files, so re-stage by date for any other window (e.g. WF 2016-10-17 ..
  2025-06-13, LB 2025-08-14 .. 2026-06-24). KEEL's lockbox model is frozen at 2025-07-16, which is before
  either of those lockbox starts, so it stays pre-lockbox-knowable under both.
- CHECK: NOISE422_raw reproduces run #422's settings (NOISE_1_8_CT304H.py, 20 / 1.15 / 1.75x) and the NOISE
  lane's figures on this tape (WF 49.6 %/yr, Sortino 4.49).
- NOTE ON THE FREEZE: freezing KEEL at the lockbox start RAISES its lockbox result versus letting it refit
  through the lockbox (#382 + KEEL LB return per drawdown 3.90 frozen vs 2.85 refitting). The walk-forward
  stretch, which is identical in both, is the fair read: there the fixed tilts beat raw and KEEL does not.

