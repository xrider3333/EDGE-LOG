# COMPARE NEWFEAT -- cross-run replication

Runs compared (4): `NOISE_243`, `ORB_314`, `RUN_309`, `RUN_326`.

This reads each run's own `<KEY>_summary.json` (never re-runs anything) and asks one question: which pre-entry conditions repeat, with the same sign, in discovery AND in that run's own once-touched holdout, across multiple runs.

## a. Replication table

Discovery lift sign per run (up-arrow positive / down-arrow negative), **bold** when that run's discovery lift_q < 0.10, plus a checkmark when the SAME run's holdout tercile lift (fixed threshold, from `tercile_lift_holdout`) has the same sign. Sorted by replication score (count of runs where q<0.10 AND holdout agrees), then mean |discovery lift|.

| feature | group | NOISE_243 | ORB_314 | RUN_309 | RUN_326 | rep score |
|---|---|---|---|---|---|---|
| lvl_sma50d_atr | lvl | **▼**✓ | ▼✓ | **▼**✓ | **▼**✓ | 3 |
| lvl_sma200d_atr | lvl | **▼**✓ | ▼✓ | **▼**✓ | **▼**✓ | 3 |
| ind_rsi14_daily | ind | **▼**✓ | ▼✓ | ▼✓ | **▼**✓ | 2 |
| day_ret_20d | day | **▼**✓ | ▼✓ | ▼✓ | **▼**✓ | 2 |
| ind_bbw_pctile_bar | ind | **▲**✓ | ▲✓ | ▲✓ | **▲**✓ | 2 |
| lvl_sma20d_atr | lvl | **▼**✓ | ▼✓ | ▼✓ | **▼**✓ | 2 |
| path_with12_atr | path | **▲**✓ | ▲✓ | ▲✓ | **▲**✓ | 2 |
| ind_atr_pctile_bar | ind | **▲**✓ | ▲✓ | ▲✓ | **▲**✓ | 2 |
| path_range10_atr | path | **▲**✓ | ▲✓ | ▲✓ | **▲**✓ | 2 |
| ind_er20_bar | ind | **▲**✓ | ▲ | ▲✓ | **▲**✓ | 2 |
| path_with24_atr | path | **▲**✓ | ▼✓ | ▲✓ | **▲**✓ | 2 |
| vt_intraday_daily_ratio | vt | ▲✓ | ▼ | ▲✓ | **▲**✓ | 1 |
| lvl_pdl_atr | lvl | ▼✓ | ▲✓ | ▼✓ | **▼**✓ | 1 |
| path_with60_atr | path | ▲✓ | ▼✓ | ▲✓ | **▲**✓ | 1 |
| xm_relret_60m_atr | xm | ▲ | ▲ | ▲✓ | **▲**✓ | 1 |
| ind_rsi14_bar | ind | ▲ | ▲ | ▲✓ | **▲**✓ | 1 |
| lvl_ema50_atr | lvl | ▲ | ▲✓ | ▲✓ | **▲**✓ | 1 |
| xm_es_rsi14 | xm | ▲✓ | ▲✓ | ▲✓ | **▲**✓ | 1 |
| lvl_ema200_atr | lvl | ▼✓ | ▼✓ | ▲✓ | **▲**✓ | 1 |
| lvl_ema50_60m_atr | lvl | ▼✓ | ▼✓ | ▼✓ | **▼**✓ | 1 |
| ind_atr_pctile_60m | ind | **▲**✓ | ▲✓ | ▲✓ | ▲✓ | 1 |
| path_range20_atr | path | **▲**✓ | ▲✓ | ▲✓ | ▲✓ | 1 |
| xm_relret_12b_atr | xm | ▲ | ▲ | ▲✓ | **▲**✓ | 1 |
| path_closepos60 | path | ▲ | ▲ | ▲ | **▲**✓ | 1 |
| path_upcount10 | path | ▲ | ▲✓ | **▲**✓ | ▲ | 1 |
| xm_relret_1d_atr | xm | ▼✓ | ▲ | ▼ | **▼**✓ | 1 |
| lvl_ema20_atr | lvl | ▲ | ▲✓ | ▲✓ | **▲**✓ | 1 |
| day_minutes_since_open | day | **▼**✓ | ▼✓ | ▲✓ | ▲✓ | 1 |
| day_hour | day | **▼**✓ | ▼ | ▼✓ | ▲ | 1 |
| cal_is_fomc_next_day | cal | ▼ | ▼ | ▼ | ▼ | 0 |
| cal_is_holiday_adjacent | cal | ▲ | ▲ | ▲ | ▲ | 0 |
| cal_is_fomc_day | cal | ▼✓ | ▼ | ▼✓ | ▼✓ | 0 |
| cal_is_month_end_2 | cal | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| vt_intraday_daily_pctile20 | vt | ▲✓ | ▼✓ | ▲✓ | ▲✓ | 0 |
| day_ret_5d | day | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| xm_relret_5d_atr | xm | ▼ | ▼✓ | ▼✓ | ▼✓ | 0 |
| lvl_prior_week_hi_atr | lvl | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| cal_is_fomc_prev_day | cal | ▲✓ | ▼ | ▼✓ | ▼ | 0 |
| cal_is_opex_day | cal | ▼ | ▼ | ▼✓ | ▲✓ | 0 |
| cal_days_to_month_end | cal | ▲✓ | ▲✓ | ▲✓ | ▲✓ | 0 |
| day_prior_close_pos | day | ▼ | ▼✓ | ▼✓ | ▼✓ | 0 |
| ind_atr_pctile_daily | ind | ▲✓ | ▲✓ | ▲ | ▲✓ | 0 |
| path_upcount5 | path | ▲✓ | ▼✓ | ▲✓ | ▲ | 0 |
| xm_es_divergence_hilo20 | xm | ▼ | ▼✓ | ▲ | ▼✓ | 0 |
| cal_is_month_start_2 | cal | ▼✓ | ▼✓ | ▲ | ▲ | 0 |
| path_r5 | path | ▲✓ | ▲✓ | ▲✓ | ▲ | 0 |
| path_upper_wick | path | ▲ | ▲✓ | ▲✓ | ▲✓ | 0 |
| cal_day_of_month | cal | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| lvl_orb_lo_atr | lvl | ▼✓ | ▲ | ▲✓ | ▲✓ | 0 |
| ind_compressed_60m | ind | ▲✓ | ▲✓ | ▲✓ | ▲ | 0 |
| lvl_orb_hi_atr | lvl | ▼ | ▲ | ▲✓ | ▲✓ | 0 |
| on_range_atr | on | ▲ | ▲✓ | n/a | n/a | 0 |
| lvl_vwap_atr | lvl | ▼✓ | ▲ | ▲✓ | ▲✓ | 0 |
| path_body_r2 | path | ▲✓ | ▼ | ▼✓ | ▼ | 0 |
| vol_last_vs_avg20 | vol | ▲✓ | ▲✓ | ▲ | ▲✓ | 0 |
| day_prior_range_pctile | day | ▲✓ | ▲✓ | ▲✓ | ▼ | 0 |
| lvl_session_open_atr | lvl | ▼✓ | ▲ | ▲✓ | ▲ | 0 |
| day_gap_pct | day | ▲✓ | ▲ | ▲ | ▲ | 0 |
| lvl_prior_week_lo_atr | lvl | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| day_prior_ret_pct | day | ▼ | ▼ | ▼✓ | ▼✓ | 0 |
| path_r10 | path | ▼✓ | ▲ | ▲✓ | ▼✓ | 0 |
| path_r6 | path | ▲ | ▼ | ▲✓ | ▲✓ | 0 |
| path_r9 | path | ▲ | ▲ | ▲✓ | ▼ | 0 |
| path_r7 | path | ▲ | ▲✓ | ▲✓ | ▲✓ | 0 |
| ind_rsi14_60m | ind | ▼ | ▲✓ | ▲ | ▼✓ | 0 |
| ind_macd_sign_daily | ind | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| path_r4 | path | ▼ | ▼✓ | ▲ | ▲ | 0 |
| ind_adx14_bar | ind | ▼ | ▲ | ▲✓ | ▲✓ | 0 |
| lvl_pdc_atr | lvl | ▲ | ▲ | ▲✓ | ▲ | 0 |
| ind_adx14_daily | ind | ▲✓ | ▲ | ▲ | ▼ | 0 |
| path_range5_atr | path | ▲✓ | ▲✓ | ▲✓ | ▲✓ | 0 |
| ind_macd_sign_bar | ind | ▲ | ▼✓ | ▲ | ▲ | 0 |
| cal_is_opex_week | cal | ▲✓ | ▼ | ▼✓ | ▼✓ | 0 |
| path_lower_wick | path | ▼✓ | ▼✓ | ▼✓ | ▲✓ | 0 |
| path_r11 | path | ▲ | ▲ | ▲ | ▲ | 0 |
| path_closepos20 | path | ▲ | ▲ | ▼✓ | ▼✓ | 0 |
| ind_er20_daily | ind | ▼ | ▼✓ | ▲✓ | ▼ | 0 |
| vol_cum_vs_avg20 | vol | ▲✓ | ▼✓ | ▲ | ▲ | 0 |
| xm_ratio_20d | xm | ▲✓ | ▼✓ | ▲ | ▼✓ | 0 |
| path_bars_since_hi20 | path | ▼✓ | ▼✓ | ▲✓ | ▼✓ | 0 |
| path_body_r1 | path | ▲✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| path_body_r3 | path | ▲✓ | ▲ | ▼ | ▼✓ | 0 |
| ind_adx14_60m | ind | ▼✓ | ▼✓ | ▼ | ▼ | 0 |
| cal_is_quarter_end_week | cal | ▼✓ | ▲ | ▼ | ▲ | 0 |
| cal_week_of_year | cal | ▼✓ | ▲ | ▼ | ▼✓ | 0 |
| path_r8 | path | ▲ | ▲✓ | ▲ | ▲✓ | 0 |
| vt_vrp | vt | ▼ | ▼ | ▼ | ▼ | 0 |
| ind_macd_sign_60m | ind | ▼ | ▲✓ | ▲✓ | ▼✓ | 0 |
| path_closepos10 | path | ▲ | ▲ | ▼✓ | ▼✓ | 0 |
| vt_realized5d_vs_20d | vt | ▲ | ▼ | ▼✓ | ▼ | 0 |
| on_mins_since_lo | on | ▼✓ | ▲✓ | n/a | n/a | 0 |
| path_r12 | path | ▲ | ▼ | ▲✓ | ▲✓ | 0 |
| on_ret_pct | on | ▲✓ | ▼ | n/a | n/a | 0 |
| lvl_ema20_60m_atr | lvl | ▼✓ | ▼✓ | ▼✓ | ▼✓ | 0 |
| day_up_streak | day | ▼ | ▲✓ | ▼✓ | ▼✓ | 0 |
| day_of_week | day | ▲✓ | ▲✓ | ▼ | ▲ | 0 |
| ind_bbw_pctile_60m | ind | ▲ | ▲ | ▲✓ | ▼ | 0 |
| path_r1 | path | ▼✓ | ▼ | ▲ | ▲✓ | 0 |
| on_mins_since_hi | on | ▼✓ | ▲✓ | n/a | n/a | 0 |
| lvl_pdh_atr | lvl | ▼ | ▼✓ | ▲✓ | ▲✓ | 0 |
| on_gap_vwap_atr | on | ▼ | ▲✓ | n/a | n/a | 0 |
| path_r2 | path | ▼ | ▲ | ▼✓ | ▼ | 0 |
| path_bars_since_lo20 | path | ▼✓ | ▲✓ | ▼ | ▲✓ | 0 |
| path_r3 | path | ▼✓ | ▲ | ▼ | ▲ | 0 |
| on_open_pos | on | ▲ | ▲✓ | n/a | n/a | 0 |

## b. Consistent conditions

Features with the SAME discovery-lift sign in >= 3 runs, significant (lift_q < 0.10) in at least 2 of them, where the holdout tercile lift agrees in every one of those runs. This is the answer to read first.

- **lvl_sma50d_atr** (lvl) -- lower values precede better trades, confirmed on 4 runs' own holdout: NOISE_243 disc=-0.464 (q=0.0381) hold=-0.971; ORB_314 disc=-0.182 (q=0.4911) hold=-1.148; RUN_309 disc=-0.722 (q=0.0989) hold=-0.710; RUN_326 disc=-0.620 (q=0.0618) hold=-2.455
- **lvl_sma200d_atr** (lvl) -- lower values precede better trades, confirmed on 4 runs' own holdout: NOISE_243 disc=-0.362 (q=0.0175) hold=-1.189; ORB_314 disc=-0.078 (q=0.8151) hold=-0.988; RUN_309 disc=-0.692 (q=0.0495) hold=-2.086; RUN_326 disc=-0.522 (q=0.0899) hold=-2.797
- **ind_rsi14_daily** (ind) -- lower values precede better trades, confirmed on 4 runs' own holdout: NOISE_243 disc=-0.459 (q=0.0175) hold=-0.993; ORB_314 disc=-0.202 (q=0.6125) hold=-0.907; RUN_309 disc=-0.713 (q=0.1236) hold=-1.952; RUN_326 disc=-0.678 (q=0.0618) hold=-3.669
- **day_ret_20d** (day) -- lower values precede better trades, confirmed on 4 runs' own holdout: NOISE_243 disc=-0.397 (q=0.0403) hold=-0.475; ORB_314 disc=-0.352 (q=0.3147) hold=-0.637; RUN_309 disc=-0.603 (q=0.1854) hold=-1.244; RUN_326 disc=-0.537 (q=0.0714) hold=-3.407
- **ind_bbw_pctile_bar** (ind) -- higher values precede better trades, confirmed on 4 runs' own holdout: NOISE_243 disc=0.605 (q=0.0175) hold=1.518; ORB_314 disc=0.098 (q=0.8151) hold=0.833; RUN_309 disc=0.513 (q=0.3214) hold=3.290; RUN_326 disc=0.654 (q=0.0330) hold=5.615
- **lvl_sma20d_atr** (lvl) -- lower values precede better trades, confirmed on 4 runs' own holdout: NOISE_243 disc=-0.402 (q=0.0175) hold=-0.882; ORB_314 disc=-0.285 (q=0.4312) hold=-0.501; RUN_309 disc=-0.611 (q=0.1854) hold=-1.549; RUN_326 disc=-0.529 (q=0.0903) hold=-4.064
- **path_with12_atr** (path) -- higher values precede better trades, confirmed on 4 runs' own holdout: NOISE_243 disc=0.446 (q=0.0315) hold=1.654; ORB_314 disc=0.196 (q=0.6125) hold=0.695; RUN_309 disc=0.507 (q=0.3214) hold=2.885; RUN_326 disc=0.626 (q=0.0714) hold=2.898
- **ind_atr_pctile_bar** (ind) -- higher values precede better trades, confirmed on 4 runs' own holdout: NOISE_243 disc=0.533 (q=0.0315) hold=1.350; ORB_314 disc=0.120 (q=0.7646) hold=0.339; RUN_309 disc=0.491 (q=0.3214) hold=3.390; RUN_326 disc=0.628 (q=0.0706) hold=4.798
- **path_range10_atr** (path) -- higher values precede better trades, confirmed on 4 runs' own holdout: NOISE_243 disc=0.324 (q=0.0909) hold=0.471; ORB_314 disc=0.468 (q=0.2098) hold=0.518; RUN_309 disc=0.272 (q=0.5895) hold=2.722; RUN_326 disc=0.555 (q=0.0714) hold=3.016
- **ind_er20_bar** (ind) -- higher values precede better trades, confirmed on 3 runs' own holdout: NOISE_243 disc=0.461 (q=0.0175) hold=0.927; RUN_309 disc=0.135 (q=0.8420) hold=1.792; RUN_326 disc=0.554 (q=0.0895) hold=3.679
- **path_with24_atr** (path) -- higher values precede better trades, confirmed on 3 runs' own holdout: NOISE_243 disc=0.475 (q=0.0262) hold=1.204; RUN_309 disc=0.139 (q=0.8413) hold=2.387; RUN_326 disc=0.563 (q=0.0706) hold=5.761

## c. Ledger roll-up

Every section-2c rule RECIPE (feature + direction + percentile) mined in >= 2 runs, with its verdict per run (thresholds are fit per-run on that run's own discovery set, so the numeric threshold is not compared, only the recipe and the verdict). ROBUST = carries (filter or size-tilt) in >= 3 runs and is a regime artifact in none.

| rule | NOISE_243 | ORB_314 | RUN_309 | RUN_326 | carries | tilt | regime | ROBUST |
|---|---|---|---|---|---|---|---|---|
| Skip trades where path_with24_atr < p66.7 [tercile] (threshold fit per-run on its own discovery set) | carries as tilt | no | no | no | 0 | 1 | 0 | no |
| Skip trades where lvl_sma20d_atr > p70 (threshold fit per-run on its own discovery set) | n/a | n/a | regime artifact | carries | 1 | 0 | 1 | no |
| Skip trades where ind_rsi14_daily > p70 (threshold fit per-run on its own discovery set) | regime artifact | n/a | regime artifact | regime artifact | 0 | 0 | 3 | no |

## d. Summary

11 pre-entry condition(s) repeat with the same sign across >= 3 of the 4 runs compared AND hold their sign on each of those runs' own untouched holdout set: day_ret_20d, ind_atr_pctile_bar, ind_bbw_pctile_bar, ind_er20_bar, ind_rsi14_daily, lvl_sma200d_atr, lvl_sma20d_atr, lvl_sma50d_atr, path_range10_atr, path_with12_atr, path_with24_atr.
No section-2c rule recipe clears the ROBUST bar (>= 3 runs carrying, zero regime artifacts).

Standing caveat: this is still discovery-only mining with one pre-registered holdout peek per run, pooled across runs -- it is a replication READ, not a validation. Nothing above is adoptable without a fenced Auto-Validate (walk-forward + lockbox) on whatever condition's or rules survive this comparison.
