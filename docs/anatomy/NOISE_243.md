# NOISE_243 -- trade anatomy

Discovery window (hard rule): first 60% of the pre-lockbox calendar span, by date.
- Pre-lockbox span: 2010-06-07 .. 2025-02-11 (lockbox excluded entirely).
- Discovery: 2010-06-07 .. 2019-03-30  (n=2370)
- Holdout: 2019-03-30 .. 2025-02-11  (n=1684)
- Lockbox excluded: n=375 (the split is by calendar date, not trade count, so discovery/holdout are not exactly 60/40 of trades).
- R unit (1R): $129 -- discovery-only mean absolute losing trade.

## 2c. Rules judged by total money, not averages

Every rule below was mined on discovery net PER TRADE (an average) -- the same ranking used in sections 1 and 2. This table re-scores the top-10 of those rules, plus a fixed tercile rule on the new 'already moving with the trade' feature (keep/upweight the top third of path_with24_atr, threshold fixed on discovery), by TOTAL money: net $ kept vs base, PF, drawdown $, MAR, how many calendar years the skipped trades would have LOST money (skip helped), and the same rule run as a 2x SIZE TILT on the kept trades instead of a filter (nothing dropped, kept trades just sized bigger). Discovery (D) and holdout (H) are shown side by side as D / H in each cell.

| rule | kept % (D/H) | net $ rule (D/H) | net $ base (D/H) | % change (D/H) | PF (D/H) | max DD $ (D/H) | MAR (D/H) | base MAR (D/H) | skip-helped yrs (D/H) | tilt net/DD/MAR (D) | tilt net/DD/MAR (H) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Skip trades where day_minutes_since_open > 170.000 (p70) | 69% / 70% | $63,387 / $195,709 | $50,113 / $270,018 | 26.5% / -27.5% | 1.419 / 1.439 | $3,895 / $23,011 | 1.847 / 1.448 | 0.946 / 2.495 | 9/10 / 2/7 | $113,499 / $8,852 / 1.455 | $465,727 / $40,962 / 1.936 | regime artifact |
| Skip trades where ind_bbw_pctile_bar < 46.418 (p30) | 70% / 69% | $62,693 / $242,290 | $50,113 / $270,018 | 25.1% / -10.3% | 1.393 / 1.561 | $4,811 / $20,407 | 1.479 / 2.022 | 0.946 / 2.495 | 8/10 / 2/7 | $112,805 / $8,669 / 1.477 | $512,308 / $36,768 / 2.373 | regime artifact |
| Skip trades where path_with24_atr < 1.145 (p30) | 70% / 71% | $61,635 / $226,670 | $50,113 / $270,018 | 23.0% / -16.1% | 1.397 / 1.508 | $4,544 / $19,642 | 1.539 / 1.965 | 0.946 / 2.495 | 8/10 / 2/7 | $111,747 / $8,838 / 1.435 | $496,688 / $37,225 / 2.272 | regime artifact |
| Skip trades where day_hour > 12.000 (p70) | 66% / 66% | $57,444 / $187,229 | $50,113 / $270,018 | 14.6% / -30.7% | 1.403 / 1.435 | $3,803 / $23,039 | 1.714 / 1.384 | 0.946 / 2.495 | 8/10 / 2/7 | $107,557 / $8,946 / 1.365 | $457,247 / $38,040 / 2.047 | regime artifact |
| Skip trades where ind_rsi14_daily > 64.715 (p70) | 70% / 68% | $60,245 / $219,600 | $50,113 / $270,018 | 20.2% / -18.7% | 1.436 / 1.571 | $5,456 / $15,919 | 1.253 / 2.349 | 0.946 / 2.495 | 8/10 / 3/7 | $110,358 / $10,614 / 1.180 | $489,618 / $32,953 / 2.530 | regime artifact |
| Skip trades where ind_atr_pctile_bar < 49.523 (p30) | 70% / 71% | $59,880 / $237,792 | $50,113 / $270,018 | 19.5% / -11.9% | 1.374 / 1.521 | $4,577 / $11,543 | 1.485 / 3.508 | 0.946 / 2.495 | 7/10 / 3/7 | $109,992 / $10,579 / 1.180 | $507,810 / $28,881 / 2.994 | regime artifact |
| Skip trades where day_hour > 13.000 (p80) | 75% / 75% | $61,456 / $215,522 | $50,113 / $270,018 | 22.6% / -20.2% | 1.380 / 1.464 | $3,930 / $20,608 | 1.775 / 1.781 | 0.946 / 2.495 | 8/10 / 2/7 | $111,569 / $9,942 / 1.274 | $485,540 / $38,559 / 2.144 | regime artifact |
| Skip trades where day_prior_range_pctile < 33.742 (p30) | 70% / 68% | $57,073 / $204,538 | $50,113 / $270,018 | 13.9% / -24.3% | 1.402 / 1.514 | $4,931 / $11,307 | 1.314 / 3.080 | 0.946 / 2.495 | 6/10 / 2/7 | $107,186 / $10,943 / 1.112 | $474,556 / $28,993 / 2.787 | regime artifact |
| Skip trades where path_with12_atr < 0.921 (p30) | 70% / 70% | $56,785 / $253,737 | $50,113 / $270,018 | 13.3% / -6.0% | 1.359 / 1.563 | $4,191 / $20,930 | 1.538 / 2.064 | 0.946 / 2.495 | 7/10 / 2/7 | $106,898 / $9,777 / 1.241 | $523,755 / $39,252 / 2.272 | regime artifact |
| Skip trades where ind_er20_bar < 0.204 (p30) | 70% / 68% | $55,715 / $210,819 | $50,113 / $270,018 | 11.2% / -21.9% | 1.393 / 1.527 | $4,715 / $18,232 | 1.341 / 1.969 | 0.946 / 2.495 | 6/10 / 1/7 | $105,827 / $9,008 / 1.333 | $480,837 / $27,720 / 2.954 | regime artifact |
| Skip trades where path_with24_atr < 4.354 (p66.7) [tercile] | 33% / 32% | $40,517 / $132,691 | $50,113 / $270,018 | -19.1% / -50.9% | 1.581 / 1.729 | $3,381 / $8,347 | 1.360 / 2.707 | 0.946 / 2.495 | 5/10 / 1/7 | $90,629 / $7,675 / 1.340 | $402,708 / $24,058 / 2.850 | carries as tilt |

Of 11 rules re-scored by total money: 0 carry as a FILTER (total $ AND MAR improve on both discovery and holdout), 1 carry only as a 2x SIZE TILT (nothing dropped; the tilt covers at most half the trades and lifts MAR by at least 10% in BOTH windows), 10 are regime artifacts (they help discovery and hurt holdout -- a rule that only worked because of when it was found), and 0 never clear the bar even in discovery. A rule ranking well by net-$-per-trade in sections 1/2 below is NOT the same claim as ranking well here: per-trade averages rise whenever a filter removes a block of merely-okay trades, even though the total dollars those trades would have added are gone -- that is exactly the trap this section exists to catch. The 2x tilt columns show the alternative that keeps every trade instead of dropping any: when a rule carries as a tilt, sizing up on conviction beats skipping outright.

## 1. Winner anatomy (PER-TRADE AVERAGES, discovery only -- can mislead; see section 2c for the total-money read)

What the market looked like, feature by feature, ahead of trades that became top-decile winners (top 10% by pnl_R) vs bottom-decile losers (bottom 10%), plus LIFT: mean pnl_R in the feature's OWN top third of trades minus its bottom third, permutation-tested (1000 draws, values shuffled within ~21-trading-day blocks) and BH-FDR corrected across features.

Top 20 by absolute lift:

| feature | group | top-decile mean | bottom-decile mean | lift (R) | q |
|---|---|---|---|---|---|
| ind_bbw_pctile_bar | ind | 74.977 | 72.716 | 0.617 | 0.0127 |
| ind_atr_pctile_bar | ind | 76.555 | 73.832 | 0.525 | 0.0276 |
| ind_atr_pctile_60m | ind | 61.175 | 58.423 | 0.515 | 0.0488 |
| path_with24_atr | path | 4.005 | 3.674 | 0.475 | 0.0190 |
| lvl_sma50d_atr | lvl | 1.271 | 1.543 | -0.464 | 0.0276 |
| ind_er20_bar | ind | 0.373 | 0.368 | 0.461 | 0.0127 |
| ind_rsi14_daily | ind | 52.376 | 57.375 | -0.459 | 0.0127 |
| path_with12_atr | path | 3.238 | 3.298 | 0.446 | 0.0253 |
| day_minutes_since_open | day | 76.435 | 108.698 | -0.431 | 0.0127 |
| path_range20_atr | path | 5.837 | 5.643 | 0.413 | 0.0292 |
| ind_atr_pctile_daily | ind | 59.413 | 58.664 | 0.404 | 0.3992 |
| lvl_sma20d_atr | lvl | 0.362 | 0.589 | -0.402 | 0.0127 |
| day_ret_20d | day | 0.477 | 1.215 | -0.397 | 0.0292 |
| day_prior_range_pctile | day | 55.776 | 54.453 | 0.380 | 0.2784 |
| day_hour | day | 10.278 | 10.835 | -0.375 | 0.0190 |
| lvl_sma200d_atr | lvl | 5.105 | 5.071 | -0.362 | 0.0127 |
| ind_compressed_60m | ind | 0.173 | 0.165 | 0.342 | 0.0804 |
| path_range10_atr | path | 4.598 | 4.465 | 0.324 | 0.0658 |
| day_prior_close_pos | day | 0.540 | 0.599 | -0.310 | 0.0804 |
| lvl_session_open_atr | lvl | 0.694 | -0.028 | -0.291 | 0.1265 |

Top 5 by top-vs-bottom-decile standardized difference:

| feature | group | top-decile mean | bottom-decile mean | all mean | std diff |
|---|---|---|---|---|---|
| lvl_ema20_atr | lvl | 0.893 | 0.044 | 0.647 | 0.349 |
| lvl_ema50_atr | lvl | 1.227 | 0.125 | 1.123 | 0.347 |
| day_gap_pct | day | 0.163 | 0.007 | 0.146 | 0.318 |
| ind_rsi14_bar | ind | 57.477 | 50.693 | 54.964 | 0.307 |
| ind_rsi14_daily | ind | 52.376 | 57.375 | 56.133 | -0.302 |

## 2. Rule mining (PER-TRADE AVERAGES, discovery only, one pre-registered holdout peek -- can mislead; see section 2c for the total-money read)

(a) Shallow decision tree (depth 3, min 5% of discovery trades per leaf, target = pnl_R):

| rule | n | mean R | PF | share | net $ |
|---|---|---|---|---|---|
| ind_bbw_pctile_bar <= 85.022 AND ind_rsi14_daily > 37.458 AND lvl_ema20_atr <= 2.966 | 1472 | -0.120 | 0.820 | 62.1% | $-22,679 |
| ind_bbw_pctile_bar > 85.022 AND lvl_sma50d_atr > -0.161 AND path_bars_since_hi20 > 0.500 | 233 | -0.060 | 0.931 | 9.8% | $-1,798 |
| ind_bbw_pctile_bar <= 85.022 AND ind_rsi14_daily <= 37.458 | 191 | 0.631 | 2.295 | 8.1% | $15,531 |
| ind_bbw_pctile_bar <= 85.022 AND ind_rsi14_daily > 37.458 AND lvl_ema20_atr > 2.966 | 168 | 0.429 | 1.818 | 7.1% | $9,285 |
| ind_bbw_pctile_bar > 85.022 AND lvl_sma50d_atr <= -0.161 | 163 | 1.451 | 2.795 | 6.9% | $30,480 |
| ind_bbw_pctile_bar > 85.022 AND lvl_sma50d_atr > -0.161 AND path_bars_since_hi20 <= 0.500 | 143 | 1.047 | 3.128 | 6.0% | $19,294 |

(b) Single-condition skip rules (feature thresholds at the 10/20/30/70/80/90th percentiles, both directions, must keep at least 60% of discovery trades):

Top 10 by remaining net $ per trade:

| rule | trades kept | net $/trade | MAR proxy |
|---|---|---|---|
| Skip trades where day_minutes_since_open > 170.000 (p70) | 1642/2370 | $38.6 | 16.273 |
| Skip trades where ind_bbw_pctile_bar < 46.418 (p30) | 1663/2370 | $37.7 | 13.778 |
| Skip trades where path_with24_atr < 1.145 (p30) | 1659/2370 | $37.2 | 13.563 |
| Skip trades where day_hour > 12.000 (p70) | 1555/2370 | $36.9 | 15.105 |
| Skip trades where ind_rsi14_daily > 64.715 (p70) | 1659/2370 | $36.3 | 11.041 |
| Skip trades where ind_atr_pctile_bar < 49.523 (p30) | 1663/2370 | $36.0 | 13.081 |
| Skip trades where day_hour > 13.000 (p80) | 1780/2370 | $34.5 | 15.638 |
| Skip trades where day_prior_range_pctile < 33.742 (p30) | 1662/2370 | $34.3 | 11.574 |
| Skip trades where path_with12_atr < 0.921 (p30) | 1659/2370 | $34.2 | 13.550 |
| Skip trades where ind_er20_bar < 0.204 (p30) | 1659/2370 | $33.6 | 11.818 |

Top 10 by remaining MAR proxy (net $ / max drawdown $ of the kept sequence):

| rule | trades kept | net $/trade | MAR proxy |
|---|---|---|---|
| Skip trades where day_minutes_since_open > 170.000 (p70) | 1642/2370 | $38.6 | 16.273 |
| Skip trades where day_hour > 13.000 (p80) | 1780/2370 | $34.5 | 15.638 |
| Skip trades where day_hour > 12.000 (p70) | 1555/2370 | $36.9 | 15.105 |
| Skip trades where ind_bbw_pctile_bar < 35.538 (p20) | 1899/2370 | $30.2 | 14.082 |
| Skip trades where path_bars_since_hi20 > 16.000 (p80) | 1838/2370 | $27.9 | 13.936 |
| Skip trades where day_prior_range_pctile < 22.372 (p20) | 1898/2370 | $30.8 | 13.903 |
| Skip trades where path_with24_atr < -0.224 (p20) | 1896/2370 | $31.4 | 13.844 |
| Skip trades where ind_bbw_pctile_bar < 46.418 (p30) | 1663/2370 | $37.7 | 13.778 |
| Skip trades where ind_atr_pctile_bar < 23.350 (p10) | 2134/2370 | $26.5 | 13.632 |
| Skip trades where path_with24_atr < 1.145 (p30) | 1659/2370 | $37.2 | 13.563 |

Pre-registered holdout check -- the SAME top-10-by-net-per-trade rules (same feature, same threshold, learned on discovery only) applied ONCE to the never-touched holdout set:

| rule | disc net/trade (rule) | disc net/trade (base) | disc kept | hold net/trade (rule) | hold net/trade (base) | hold kept |
|---|---|---|---|---|---|---|
| Skip trades where day_minutes_since_open > 170.000 (p70) | $38.6 | $21.1 | 1642 | $166.8 | $160.3 | 1173 |
| Skip trades where ind_bbw_pctile_bar < 46.418 (p30) | $37.7 | $21.1 | 1663 | $208.5 | $160.3 | 1162 |
| Skip trades where path_with24_atr < 1.145 (p30) | $37.2 | $21.1 | 1659 | $190.5 | $160.3 | 1190 |
| Skip trades where day_hour > 12.000 (p70) | $36.9 | $21.1 | 1555 | $167.3 | $160.3 | 1119 |
| Skip trades where ind_rsi14_daily > 64.715 (p70) | $36.3 | $21.1 | 1659 | $193.1 | $160.3 | 1137 |
| Skip trades where ind_atr_pctile_bar < 49.523 (p30) | $36.0 | $21.1 | 1663 | $199.7 | $160.3 | 1191 |
| Skip trades where day_hour > 13.000 (p80) | $34.5 | $21.1 | 1780 | $171.0 | $160.3 | 1260 |
| Skip trades where day_prior_range_pctile < 33.742 (p30) | $34.3 | $21.1 | 1662 | $178.6 | $160.3 | 1145 |
| Skip trades where path_with12_atr < 0.921 (p30) | $34.2 | $21.1 | 1659 | $215.6 | $160.3 | 1177 |
| Skip trades where ind_er20_bar < 0.204 (p30) | $33.6 | $21.1 | 1659 | $183.0 | $160.3 | 1152 |

This is a single peek at holdout, not a validation. Any rule that looks good here still has to clear a fenced Auto-Validate plus walk-forward and lockbox checks before it means anything.

## 3. Charts

- NOISE_243/win_01..16.png, NOISE_243/loss_01..16.png -- 60 bars before / 20 after entry, EMA20 + VWAP overlay, prior-day H/L/C dashed, entry (up marker) / exit (down marker), for the 16 largest discovery winners and losers by pnl_R.
- NOISE_243_path_overlay.png -- median normalized close path (ATR units, 0 at the decision bar) over the 60 bars before entry: top-decile winners vs bottom-decile losers vs all discovery trades, with interquartile shading.

## Caveats

- Discovery-only, single-leg. Nothing here has been checked against another strategy family -- that is feature_board.py's job, not this file's.
- Multiple comparisons: the lift table is BH-FDR corrected across features; the standardized-difference ranking, the tree, and the skip-rule search are NOT -- treat them as leads to test, not findings.
- Thin tails: top/bottom-decile means and the tree's deepest leaves can be a handful of trades; one outlier trade can move them a lot.
- The holdout check is one look. Re-running this file and re-peeking at holdout with a different rule set defeats the point of holding it out at all.
- Everything here must still pass a fenced Auto-Validate and the walk-forward / lockbox gauntlet before any rule is adopted into a live strategy.
