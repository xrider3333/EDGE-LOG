# COMPARE ENGUQ -- cross-run replication

Runs compared (6): `RUN_309`, `RUN_226`, `RUN_326`, `RUN_310`, `RUN_320`, `RUN_227`.

This reads each run's own `<KEY>_summary.json` (never re-runs anything) and asks one question: which pre-entry conditions repeat, with the same sign, in discovery AND in that run's own once-touched holdout, across multiple runs.

## a. Replication table

Discovery lift sign per run (up-arrow positive / down-arrow negative), **bold** when that run's discovery lift_q < 0.10, plus a checkmark when the SAME run's holdout tercile lift (fixed threshold, from `tercile_lift_holdout`) has the same sign. Sorted by replication score (count of runs where q<0.10 AND holdout agrees), then mean |discovery lift|.

| feature | group | RUN_309 | RUN_226 | RUN_326 | RUN_310 | RUN_320 | RUN_227 | rep score |
|---|---|---|---|---|---|---|---|---|
| ind_bbw_pctile_bar | ind | ▲✓ | ▲✓ | **▲**✓ | ▲✓ | ▲✓ | **▲**✓ | 2 |
| lvl_sma50d_atr | lvl | **▼**✓ | ▼ | **▼**✓ | ▼✓ | ▼ | **▼** | 2 |
| ind_atr_pctile_bar | ind | ▲✓ | ▲✓ | **▲**✓ | ▲✓ | ▲✓ | **▲**✓ | 2 |
| ind_rsi14_daily | ind | **▼**✓ | ▼✓ | **▼**✓ | ▼✓ | ▼✓ | ▼ | 2 |
| lvl_sma200d_atr | lvl | **▼**✓ | ▼✓ | **▼**✓ | ▼✓ | ▼✓ | **▼** | 2 |
| lvl_sma20d_atr | lvl | ▼✓ | ▼✓ | **▼**✓ | ▼✓ | ▼✓ | **▼**✓ | 2 |
| lvl_pdl_atr | lvl | ▼✓ | ▼✓ | **▼**✓ | ▼✓ | ▼✓ | ▼✓ | 1 |
| lvl_ema50_60m_atr | lvl | ▼✓ | ▼✓ | **▼**✓ | ▼✓ | ▼✓ | ▼✓ | 1 |
| ind_er20_bar | ind | ▲✓ | ▲✓ | **▲**✓ | ▲✓ | ▼ | ▲ | 1 |
| lvl_ema50_atr | lvl | ▲✓ | ▲✓ | **▲**✓ | ▲✓ | ▼ | ▼ | 1 |
| ind_rsi14_bar | ind | ▲✓ | ▲✓ | **▲**✓ | ▲✓ | ▲✓ | ▲✓ | 1 |
| path_range10_atr | path | ▲✓ | ▲ | **▲**✓ | ▲✓ | ▼ | ▲ | 1 |
| path_with60_atr | path | ▲✓ | ▲✓ | **▲**✓ | ▲✓ | ▼ | ▼✓ | 1 |
| lvl_ema20_atr | lvl | ▲✓ | ▲✓ | **▲**✓ | ▲✓ | ▼ | ▼ | 1 |
| day_ret_20d | day | ▼✓ | ▼✓ | **▼**✓ | ▼✓ | ▲✓ | ▼✓ | 1 |
| lvl_ema200_atr | lvl | ▲✓ | ▲✓ | **▲**✓ | ▲✓ | ▼ | ▼✓ | 1 |
| path_upcount10 | path | **▲**✓ | ▲ | ▲ | ▲✓ | ▲✓ | ▼ | 1 |
| path_with24_atr | path | ▲✓ | ▲✓ | **▲**✓ | ▲✓ | ▼ | ▼ | 1 |
| path_with12_atr | path | ▲✓ | ▲ | **▲**✓ | ▲✓ | ▲✓ | ▼ | 1 |
| path_closepos60 | path | ▲ | ▲✓ | **▲**✓ | ▲✓ | ▲✓ | ▼ | 1 |
| ind_macd_sign_bar | ind | ▲ | ▼ | ▲ | ▼ | ▼ | ▼ | 0 |
| lvl_orb_hi_atr | lvl | ▲✓ | ▲✓ | ▲✓ | ▲ | ▼ | ▼✓ | 0 |
| ind_rsi14_60m | ind | ▲ | ▼✓ | ▼✓ | ▼ | ▼✓ | ▼✓ | 0 |
| vol_last_vs_avg20 | vol | ▲ | ▲✓ | ▲✓ | ▼ | ▼ | ▲✓ | 0 |
| day_prior_close_pos | day | ▼✓ | ▼✓ | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| vol_cum_vs_avg20 | vol | ▲ | ▲✓ | ▲ | ▲✓ | ▲✓ | ▼✓ | 0 |
| day_minutes_since_open | day | ▲✓ | ▲✓ | ▲✓ | ▲✓ | ▲ | ▲✓ | 0 |
| lvl_orb_lo_atr | lvl | ▲✓ | ▲ | ▲✓ | ▼ | ▼✓ | ▼✓ | 0 |
| lvl_session_open_atr | lvl | ▲✓ | ▲✓ | ▲ | ▼✓ | ▼✓ | ▼✓ | 0 |
| day_prior_ret_pct | day | ▼✓ | ▼ | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| lvl_prior_week_hi_atr | lvl | ▼✓ | ▼✓ | ▼✓ | ▼✓ | ▼ | ▼✓ | 0 |
| path_r9 | path | ▲✓ | ▼✓ | ▼ | ▲ | ▲ | ▼ | 0 |
| path_r6 | path | ▲✓ | ▼ | ▲✓ | ▲ | ▲✓ | ▲✓ | 0 |
| path_r1 | path | ▲ | ▲ | ▲✓ | ▼ | ▼ | ▼ | 0 |
| day_hour | day | ▼✓ | ▲✓ | ▲ | ▲✓ | ▲✓ | ▲✓ | 0 |
| day_ret_5d | day | ▼✓ | ▼ | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| lvl_vwap_atr | lvl | ▲✓ | ▲✓ | ▲✓ | ▲✓ | ▲✓ | ▼✓ | 0 |
| path_body_r2 | path | ▼✓ | ▼✓ | ▼ | ▼ | ▼ | ▼ | 0 |
| lvl_pdc_atr | lvl | ▲✓ | ▲ | ▲ | ▲ | ▼ | ▲✓ | 0 |
| path_r8 | path | ▲ | ▲ | ▲✓ | ▲✓ | ▲ | ▲✓ | 0 |
| path_range20_atr | path | ▲✓ | ▲✓ | ▲✓ | ▲✓ | ▼ | ▲ | 0 |
| ind_adx14_bar | ind | ▲✓ | ▲ | ▲✓ | ▲✓ | ▼✓ | **▲** | 0 |
| path_r3 | path | ▼ | ▼✓ | ▲ | ▲ | ▲ | ▲✓ | 0 |
| lvl_ema20_60m_atr | lvl | ▼✓ | ▼✓ | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| path_upper_wick | path | ▲✓ | ▼ | ▲✓ | ▲✓ | ▲✓ | ▲✓ | 0 |
| path_body_r1 | path | ▼✓ | ▲ | ▼✓ | ▼ | ▼ | ▼✓ | 0 |
| ind_er20_daily | ind | ▲✓ | ▼✓ | ▼ | ▲✓ | ▼ | ▲ | 0 |
| ind_atr_pctile_60m | ind | ▲✓ | ▲✓ | ▲✓ | ▲✓ | ▲✓ | ▲ | 0 |
| path_range5_atr | path | ▲✓ | ▲✓ | ▲✓ | ▲✓ | ▼ | ▲✓ | 0 |
| path_r4 | path | ▲ | ▲✓ | ▲ | ▼ | ▼✓ | ▲ | 0 |
| day_gap_pct | day | ▲ | ▲✓ | ▲ | ▲ | ▲✓ | ▲✓ | 0 |
| path_r11 | path | ▲ | ▲ | ▲ | ▲ | ▲✓ | ▼✓ | 0 |
| day_up_streak | day | ▼✓ | ▼ | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| ind_macd_sign_60m | ind | ▲✓ | ▼✓ | ▼✓ | ▲✓ | ▼✓ | ▼✓ | 0 |
| ind_bbw_pctile_60m | ind | ▲✓ | ▼ | ▼ | ▼ | ▲ | ▲ | 0 |
| lvl_prior_week_lo_atr | lvl | ▼✓ | ▼✓ | ▼✓ | ▼ | ▼✓ | ▼✓ | 0 |
| path_bars_since_lo20 | path | ▼ | ▲ | ▲✓ | ▲✓ | ▲✓ | ▼ | 0 |
| ind_macd_sign_daily | ind | ▼✓ | ▼✓ | ▼✓ | ▼✓ | ▲ | ▼✓ | 0 |
| ind_atr_pctile_daily | ind | ▲ | ▼✓ | ▲✓ | ▲✓ | ▲ | ▲ | 0 |
| ind_adx14_daily | ind | ▲ | ▼✓ | ▼ | ▲✓ | ▼✓ | ▲ | 0 |
| path_lower_wick | path | ▼✓ | ▲✓ | ▲✓ | ▲✓ | ▲✓ | ▲✓ | 0 |
| path_closepos10 | path | ▼✓ | ▲✓ | ▼✓ | ▼ | ▲✓ | ▼ | 0 |
| path_upcount5 | path | ▲✓ | ▲✓ | ▲ | ▲✓ | ▲✓ | ▼✓ | 0 |
| path_body_r3 | path | ▼ | ▼ | ▼✓ | ▼✓ | ▼✓ | ▲ | 0 |
| path_r5 | path | ▲✓ | ▼ | ▲ | ▼✓ | ▼ | ▼ | 0 |
| day_of_week | day | ▼ | ▲ | ▲ | ▲ | ▲✓ | ▲✓ | 0 |
| path_r12 | path | ▲✓ | ▼ | ▲✓ | ▲✓ | ▲✓ | ▲✓ | 0 |
| lvl_pdh_atr | lvl | ▲✓ | ▲✓ | ▲✓ | ▲ | ▼ | ▼✓ | 0 |
| path_r2 | path | ▼✓ | ▼ | ▼ | ▼ | ▼✓ | ▼ | 0 |
| path_closepos20 | path | ▼✓ | ▲✓ | ▼✓ | ▼ | ▲✓ | ▼ | 0 |
| path_bars_since_hi20 | path | ▲✓ | ▼✓ | ▼✓ | ▲ | ▲ | ▲ | 0 |
| ind_adx14_60m | ind | ▼ | ▼✓ | ▼ | ▲✓ | ▼ | ▼✓ | 0 |
| day_prior_range_pctile | day | ▲✓ | ▼✓ | ▼ | ▼ | ▼✓ | ▲ | 0 |
| path_r7 | path | ▲✓ | ▲✓ | ▲✓ | ▼ | ▼✓ | ▲ | 0 |
| path_r10 | path | ▲✓ | ▼✓ | ▼✓ | ▼ | ▼✓ | ▲✓ | 0 |
| ind_compressed_60m | ind | ▲✓ | ▲ | ▲ | ▲✓ | ▼ | ▲ | 0 |

## b. Consistent conditions

Features with the SAME discovery-lift sign in >= 3 runs, significant (lift_q < 0.10) in at least 2 of them, where the holdout tercile lift agrees in every one of those runs. This is the answer to read first.

- **ind_bbw_pctile_bar** (ind) -- higher values precede better trades, confirmed on 6 runs' own holdout: RUN_309 disc=0.513 (q=0.3200) hold=3.290; RUN_226 disc=0.390 (q=0.4366) hold=1.770; RUN_326 disc=0.654 (q=0.0304) hold=5.615; RUN_310 disc=1.041 (q=0.5568) hold=9.736; RUN_320 disc=1.935 (q=0.4081) hold=20.746; RUN_227 disc=0.855 (q=0.0886) hold=0.542
- **lvl_sma50d_atr** (lvl) -- lower values precede better trades, confirmed on 3 runs' own holdout: RUN_309 disc=-0.722 (q=0.0759) hold=-0.710; RUN_326 disc=-0.620 (q=0.0542) hold=-2.455; RUN_310 disc=-0.444 (q=0.7558) hold=-5.735
- **ind_atr_pctile_bar** (ind) -- higher values precede better trades, confirmed on 6 runs' own holdout: RUN_309 disc=0.491 (q=0.3200) hold=3.390; RUN_226 disc=0.331 (q=0.4555) hold=2.427; RUN_326 disc=0.628 (q=0.0617) hold=4.798; RUN_310 disc=0.621 (q=0.6049) hold=10.206; RUN_320 disc=1.642 (q=0.6191) hold=20.066; RUN_227 disc=0.974 (q=0.0886) hold=1.061
- **ind_rsi14_daily** (ind) -- lower values precede better trades, confirmed on 5 runs' own holdout: RUN_309 disc=-0.713 (q=0.0949) hold=-1.952; RUN_226 disc=-0.296 (q=0.6310) hold=-0.631; RUN_326 disc=-0.678 (q=0.0542) hold=-3.669; RUN_310 disc=-0.860 (q=0.5568) hold=-7.819; RUN_320 disc=-1.176 (q=0.7228) hold=-6.723
- **lvl_sma200d_atr** (lvl) -- lower values precede better trades, confirmed on 5 runs' own holdout: RUN_309 disc=-0.692 (q=0.0380) hold=-2.086; RUN_226 disc=-0.334 (q=0.4925) hold=-0.017; RUN_326 disc=-0.522 (q=0.0839) hold=-2.797; RUN_310 disc=-0.720 (q=0.6049) hold=-6.044; RUN_320 disc=-1.306 (q=0.6799) hold=-5.899
- **lvl_sma20d_atr** (lvl) -- lower values precede better trades, confirmed on 6 runs' own holdout: RUN_309 disc=-0.611 (q=0.1424) hold=-1.549; RUN_226 disc=-0.441 (q=0.4555) hold=-0.941; RUN_326 disc=-0.529 (q=0.0839) hold=-4.064; RUN_310 disc=-0.361 (q=0.7622) hold=-5.202; RUN_320 disc=-0.865 (q=0.8798) hold=-0.309; RUN_227 disc=-0.863 (q=0.0886) hold=-0.161

## c. Ledger roll-up

Every section-2c rule RECIPE (feature + direction + percentile) mined in >= 2 runs, with its verdict per run (thresholds are fit per-run on that run's own discovery set, so the numeric threshold is not compared, only the recipe and the verdict). ROBUST = carries (filter or size-tilt) in >= 3 runs and is a regime artifact in none.

| rule | RUN_309 | RUN_226 | RUN_326 | RUN_310 | RUN_320 | RUN_227 | carries | tilt | regime | ROBUST |
|---|---|---|---|---|---|---|---|---|---|---|
| Skip trades where lvl_ema50_60m_atr > p70 (threshold fit per-run on its own discovery set) | carries | carries | regime artifact | n/a | n/a | no | 2 | 0 | 1 | no |
| Skip trades where path_with24_atr < p66.7 [tercile] (threshold fit per-run on its own discovery set) | no | no | no | carries as tilt | no | no | 0 | 1 | 0 | no |
| Skip trades where lvl_sma20d_atr > p70 (threshold fit per-run on its own discovery set) | regime artifact | n/a | carries | n/a | n/a | regime artifact | 1 | 0 | 2 | no |
| Skip trades where path_closepos60 < p30 (threshold fit per-run on its own discovery set) | n/a | regime artifact | regime artifact | carries | n/a | n/a | 1 | 0 | 2 | no |
| Skip trades where lvl_pdl_atr > p70 (threshold fit per-run on its own discovery set) | no | n/a | regime artifact | n/a | n/a | n/a | 0 | 0 | 1 | no |
| Skip trades where path_body_r2 > p70 (threshold fit per-run on its own discovery set) | n/a | n/a | n/a | no | regime artifact | n/a | 0 | 0 | 1 | no |
| Skip trades where lvl_session_open_atr > p70 (threshold fit per-run on its own discovery set) | n/a | n/a | n/a | n/a | regime artifact | no | 0 | 0 | 1 | no |
| Skip trades where lvl_sma50d_atr > p70 (threshold fit per-run on its own discovery set) | regime artifact | n/a | n/a | n/a | n/a | regime artifact | 0 | 0 | 2 | no |
| Skip trades where day_hour < p30 (threshold fit per-run on its own discovery set) | n/a | regime artifact | n/a | regime artifact | n/a | n/a | 0 | 0 | 2 | no |
| Skip trades where lvl_ema50_atr < p30 (threshold fit per-run on its own discovery set) | n/a | regime artifact | regime artifact | n/a | n/a | n/a | 0 | 0 | 2 | no |
| Skip trades where ind_atr_pctile_bar < p30 (threshold fit per-run on its own discovery set) | n/a | n/a | regime artifact | no | n/a | regime artifact | 0 | 0 | 2 | no |
| Skip trades where day_ret_5d > p70 (threshold fit per-run on its own discovery set) | n/a | n/a | n/a | regime artifact | regime artifact | n/a | 0 | 0 | 2 | no |
| Skip trades where ind_bbw_pctile_bar < p30 (threshold fit per-run on its own discovery set) | n/a | n/a | n/a | regime artifact | regime artifact | no | 0 | 0 | 2 | no |
| Skip trades where ind_rsi14_daily > p70 (threshold fit per-run on its own discovery set) | regime artifact | n/a | regime artifact | n/a | n/a | regime artifact | 0 | 0 | 3 | no |

## d. Summary

6 pre-entry condition(s) repeat with the same sign across >= 3 of the 6 runs compared AND hold their sign on each of those runs' own untouched holdout set: ind_atr_pctile_bar, ind_bbw_pctile_bar, ind_rsi14_daily, lvl_sma200d_atr, lvl_sma20d_atr, lvl_sma50d_atr.
No section-2c rule recipe clears the ROBUST bar (>= 3 runs carrying, zero regime artifacts).

Standing caveat: this is still discovery-only mining with one pre-registered holdout peek per run, pooled across runs -- it is a replication READ, not a validation. Nothing above is adoptable without a fenced Auto-Validate (walk-forward + lockbox) on whatever condition's or rules survive this comparison.
