# Cross-family feature board

Rule: A feature is PROMOTED only when it clears the significance bar with the same sign in at least 3 different strategy families, and its direction repeats in the last-12-months lockbox of every one of those families.

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

## WATCH (6)

- atr_norm (-, ENGUQ, NOISE): Volatility level (ATR / price) hurt in ENGUQ, NOISE — only two families, short of the 3-family bar.
- dist_pdh_atr (-, ENGUQ, NQDIP): Distance from yesterday's high (ATR units) hurt in ENGUQ, NQDIP — only two families, short of the 3-family bar.
- prev_ret (-, ENGUQ, NQDIP): Prior day's return hurt in ENGUQ, NQDIP — only two families, short of the 3-family bar.
- up_streak (-, ENGUQ, NQDIP): Consecutive up/down day count, prior day hurt in ENGUQ, NQDIP — only two families, short of the 3-family bar.
- curve (+, ENGUQ, NOISE): Yield curve (10y minus 3mo) helped in ENGUQ, NOISE — only two families, short of the 3-family bar.
- prev_day_close_pos (-, ENGUQ, NQDIP): Yesterday's close position in its own range hurt in ENGUQ, NQDIP — only two families, short of the 3-family bar.

## Caveats

- The lockbox sign check is a light peek, not a second statistical test — treat `lb_agrees` as directional support, not proof.
- NQDIP and ENGU-Q have the fewest lockbox trades of the four families, so their `lb_agrees` flags are the least reliable and most likely to be null (below 30 trades).
- Shadow-probe and block-bootstrap constants are shared with `augur_engine/context.py` (MIN_FEATURE_TRADES, FDR_Q, block-days sizing) so this board's bar matches the site's own PARAM RELATIONSHIP panel.
