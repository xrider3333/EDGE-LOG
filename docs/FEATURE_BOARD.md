# Cross-family feature board

Rule: A feature is PROMOTED only when it clears the significance bar with the same sign in at least 3 different strategy families, and its direction repeats in the last-12-months lockbox of every one of those families. The rule runs on two bases, rank and lift (see lift_note) — a feature can be PROMOTED/WATCH on either one, or on both.

## Leg parity (reproduced locally vs the doc's own numbers)

| leg | window | n pre / lb | net pre / lb | parity |
|---|---|---|---|---|
| ORB #314 (crown) | 2010-06-07..2026-08-13 | 2131 / 168 | $310,019 / $87,132 | PASS |
| ORB #234 (control, pinned card) | 2010-06-07..2026-06-30 | 2411 / 173 | $300,779 / $72,526 | n/a (defaults, no doc) |
| NOISE #243 (paper leg, pinned) | 2010-06-07..2026-08-12 | 4054 / 375 | $320,130 / $60,615 | PASS |
| NOISE #316 | 2010-06-07..2026-08-12 | 3556 / 228 | $332,759 / $26,373 | PASS |
| ENGU-Q #309 (crown, NQ 1m ETH) | 2010-06-07..2026-06-30 | 1505 / 99 | $505,756 / $85,511 | PASS |
| NQDIP #307 | 2010-06-07..2026-08-24 | 851 / 56 | $458,383 / $20,938 | PASS |

## PROMOTED (0)

None cleared the 3-family + lockbox bar this round.

## WATCH (7)

- atr_norm (mixed, conflict, ENGUQ, NOISE): Volatility level (ATR / price): the two tests disagree - by rank order it hurt (ENGUQ, NOISE) but by average dollars per trade it helped (ENGUQ, NOISE). A feature cannot be promoted until both readings point the same way.
- dist_pdh_atr (-, rank, ENGUQ, NQDIP): Distance from yesterday's high (ATR units) hurt in ENGUQ, NQDIP on rank order (Spearman) — only 2 families, short of the 3-family bar, though not on average dollars per trade (lift).
- prev_ret (-, rank, ENGUQ, NQDIP): Prior day's return hurt in ENGUQ, NQDIP on rank order (Spearman) — only 2 families, short of the 3-family bar, though not on average dollars per trade (lift).
- up_streak (-, rank, ENGUQ, NQDIP): Consecutive up/down day count, prior day hurt in ENGUQ, NQDIP on rank order (Spearman) — only 2 families, short of the 3-family bar, though not on average dollars per trade (lift).
- vix (+, lift, ENGUQ, NOISE): VIX level, prior close helped in ENGUQ, NOISE on average dollars per trade (lift) — only 2 families, short of the 3-family bar, though not on rank order (Spearman).
- curve (mixed, conflict, ENGUQ, NOISE): Yield curve (10y minus 3mo): the two tests disagree - by rank order it helped (ENGUQ, NOISE) but by average dollars per trade it hurt (ENGUQ, NOISE). A feature cannot be promoted until both readings point the same way.
- prev_day_close_pos (-, rank, ENGUQ, NQDIP): Yesterday's close position in its own range hurt in ENGUQ, NQDIP on rank order (Spearman) — only 2 families, short of the 3-family bar, though not on average dollars per trade (lift).

## LIFT — tail-aware second read

LIFT is the difference in average profit, measured in R (the leg's own typical losing trade), between the top third and bottom third of a feature's trades — it catches an edge that shows up mainly in a few big winners even when the trades' RANK ORDER (Spearman) shows nothing.

### `compressed_60m` on every leg — rank vs lift

| leg | rank rho | rank survives | lift_r (R) | lift survives | lockbox lift agrees |
|---|---|---|---|---|---|
| ORB #314 (crown) | +0.0108 | False | +0.199 | False | True |
| ORB #234 (control, pinned card) | +0.0149 | False | +0.169 | False | True |
| NOISE #243 (paper leg, pinned) | +0.0612 | True | +0.456 | True | True |
| NOISE #316 | +0.0390 | True | +0.299 | False | True |
| ENGU-Q #309 (crown, NQ 1m ETH) | -0.0146 | False | +0.484 | False | True |
| NQDIP #307 | -0.0513 | False | -0.060 | False | n/a |

### Cells where lift_survives=true (15)

| feature | leg | family | lift_r (R) | 95% CI | lockbox lift_r | lockbox agrees |
|---|---|---|---|---|---|---|
| dist_pdl_atr | ENGU-Q #309 (crown, NQ 1m ETH) | ENGUQ | -1.069 | [-1.620, -0.543] | -3.097 | True |
| curve | ENGU-Q #309 (crown, NQ 1m ETH) | ENGUQ | -1.035 | [-1.705, -0.559] | n/a | n/a |
| vix | ENGU-Q #309 (crown, NQ 1m ETH) | ENGUQ | +1.006 | [+0.418, +1.788] | +5.093 | n/a |
| atr_norm | ENGU-Q #309 (crown, NQ 1m ETH) | ENGUQ | +0.902 | [+0.376, +1.459] | +3.265 | True |
| dist_sma200d_atr | ENGU-Q #309 (crown, NQ 1m ETH) | ENGUQ | -0.711 | [-1.513, -0.220] | -3.473 | True |
| atr_norm | NOISE #243 (paper leg, pinned) | NOISE | +0.531 | [+0.307, +0.820] | +0.678 | True |
| compressed_60m | NOISE #243 (paper leg, pinned) | NOISE | +0.456 | [+0.177, +0.769] | +0.852 | True |
| vix | NOISE #316 | NOISE | +0.428 | [+0.174, +0.736] | n/a | n/a |
| curve | NOISE #316 | NOISE | -0.395 | [-0.754, -0.007] | n/a | n/a |
| vix | NOISE #243 (paper leg, pinned) | NOISE | +0.368 | [+0.135, +0.650] | n/a | n/a |
| curve | NOISE #243 (paper leg, pinned) | NOISE | -0.366 | [-0.799, -0.057] | n/a | n/a |
| dist_sma50d_atr | NOISE #316 | NOISE | -0.345 | [-0.629, -0.078] | +1.634 | False |
| vix_pctile_1y | NOISE #316 | NOISE | +0.330 | [+0.096, +0.623] | -0.318 | False |
| dist_sma50d_atr | NOISE #243 (paper leg, pinned) | NOISE | -0.324 | [-0.623, -0.089] | -0.086 | True |
| vix_pctile_1y | NOISE #243 (paper leg, pinned) | NOISE | +0.316 | [+0.088, +0.619] | +0.032 | True |

## Caveats

- The lockbox sign check is a light peek, not a second statistical test — treat `lb_agrees` as directional support, not proof.
- NQDIP and ENGU-Q have the fewest lockbox trades of the four families, so their `lb_agrees` flags are the least reliable and most likely to be null (below 30 trades).
- Shadow-probe and block-bootstrap constants are shared with `augur_engine/context.py` (MIN_FEATURE_TRADES, FDR_Q, block-days sizing) so this board's bar matches the site's own PARAM RELATIONSHIP panel.
