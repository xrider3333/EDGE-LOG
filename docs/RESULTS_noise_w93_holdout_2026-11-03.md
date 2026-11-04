# RESULTS - NOISE #382 loser anatomy SKIP test on held folds 5-8 (w93, MANAGER #165) - 2026-11-03

Prereg: `C:\EdgeLog\manager\prereg\PREREG_noise382_loser_anatomy_2026-11-03.md` (locked before the test was written).
Script: `tools/noise_w93_holdout.py`. Output: `C:\EdgeLog\_anatomy_cache\w93_loser\holdout_folds5to8.json`.
Rule: skip a #382 entry when NQ is not leading ES in the trade's direction (div < 0.0011664, the folds 1-4 cut, fixed).

## Verdict: FAIL by its own rule. Nothing live changes.

| Folds 5-8 (2021-03-05..2025-07-15), lockbox never loaded | ROC@30k | DD5 | DD% | Sortino | Net | Worst DD | One episode |
|---|---|---|---|---|---|---|---|
| HOLD (1,138 trades) | 87.67 | $18.0k | 10.90 | 3.38 | $279.2k | $21.4k | no |
| SKIP (311 skipped) | 106.04 | $13.8k | 9.44 | 4.16 | $286.9k | $18.2k | **yes** |

| Rule line | Result | Pass? |
|---|---|---|
| SKIP beats HOLD on ROC@30k and Sortino | 106.0 vs 87.7, 4.16 vs 3.38 | yes |
| SKIP wins >= 3 of 4 folds | **2 of 4** (folds 7, 8 win; 5, 6 lose) | **no** |
| Flagged per trade below unflagged in >= 3 of 4 folds | 4 of 4 | yes |
| Flagged total net below zero | -$7.7k (-$24.7/trade vs +$347 kept) | yes |
| Not one episode | SKIP curve carries the one-episode flag, HOLD does not | **no** |

Per fold, $: hold 50.8k / 79.0k / 58.8k / 90.6k; skip 46.5k / 62.9k / 61.9k / 115.7k.

## Plain read
- The flag does find worse trades: flagged entries are weaker per trade in all 4 held folds, and lose money as a group.
- But dropping them only adds money in folds 7 and 8, and fold 8 alone carries the gain (+$25k); in folds 5 and 6 the flagged
  trades still made money in total, so skipping them cost $20k. The ROC lift is mostly a smaller worst drawdown.
- Two of the five rule lines fail, so this is a FAIL, not a lead to tune. The prereg also said the holdout was underpowered for a
  ~6-pt effect; the per-trade signal held, the money did not spread across folds.
- Caveat: the chain is the t74 rebuild (~0.5% off #382's stored trades, folds 1, 2, 4, 6, 7, 8 not bit-exact); both arms use the
  same trades.
