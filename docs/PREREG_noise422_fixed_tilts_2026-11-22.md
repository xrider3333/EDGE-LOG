# PRE-REGISTRATION - NOISE #422 x frozen v12 fixed tilts (board test 112, 2026-11-22)

Written BEFORE the validate is queued. Nothing below may change after this file is pushed.

## What is tested
- File: `augur_strategies/NOISE_1_8_CT304H_FT.py` = NOISE #422 (`NOISE_1_8_CT304H.py`) with the v12 fixed tilts applied to each trade's size at its ENTRY bar, exactly as frozen 2026-09-27 (`augur_engine.ml_keel.fixed_tilt_sizes_v12`, arm A3 of `docs/PREREG_keel_422_parts_2026-09-27.md`):
  - compression on (last complete 60-min squeeze) 1.5x;
  - Friday 1.5x;
  - product capped at 3;
  - 0.5x before an FOMC statement.

  No model and no knobs. The tilts are never tuned.
- Final size = #422's own tilt size x fixed multiplier. Cost: same as the parent (0.533 pts, engine subtracts once; size-s trade = s*raw - (s-1)*cost).
- Search: #422's parent ranges unchanged (gate_len 16/20/24, gate_ratio 0.85/1.0/1.15, tilt_mult 1.25/1.5/1.75), 900 trials.
- Window and master pinned like run #422; master db_noadj_rth NQ 5m RTH. Runs on the DESKTOP.

## Parity before queueing (no lockbox rows read)
- At #422's champion (20 / 1.15 / 1.75), tape 2010-06-07..2025-06-30:
  - 4,473 of 4,495 trades match the 09-27 export (`C:/EdgeLog/book_legs/NOISE422_fixed_trades.csv`, LB rows dropped unread);
  - 20 of the matched trades differ;
  - 22 / 24 trades are unmatched at the edges;
  - sum $662,983 vs $658,715 (+0.6 pct).
- Residual is master bars changed since the 09-16 tape (later fills), not the tilt rule, which is the same function.

## Pass bar (all must hold)
1. Walk-forward lift over #422 AT EQUAL DRAWDOWN: the FT stitched WF series scaled to #422's WF max DD beats #422 on ROC@30k AND on Sortino.
2. Not one episode:
   - count folds - FT beats #422 (equal-DD) in at least 6 of 8 WF folds;
   - worst DD / DD5 <= 1.3.
3. Lockbox read ONCE, after 1-2. It must not lose to #422 at equal DD. One read, no re-run.

Leverage alone fails: a tilt that raises money and drawdown together is judged only at equal DD.

## Not allowed
- Re-tuning any tilt value.
- Adding knobs.
- A second lockbox read.
- Changing window or master after seeing a result.
