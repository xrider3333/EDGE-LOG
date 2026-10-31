# RESULTS - test 74: NOISE #382 MFE giveback stop - NO LIFT

Prereg `docs/PREREG_noise_t74_giveback_2026-10-31.md` (cfa2c03a, pushed before the grid ran). Tool
`tools/noise_t74_giveback.py`. Files under `C:\EdgeLog\_anatomy_cache\t74_giveback\`: `webull_382_mfe.csv`,
`chain_382_mfe.csv`, `grid_wf.csv`, `giveback_hist.png`. Lockbox never loaded.

## Verdict in plain words
Yes, NOISE gives a lot back: the typical trade gives back more than it ever showed. But no giveback stop in the prereg grid
beats holding the leg's own exits. A tight stop cuts the few big winners that make the leg's money. A loose stop changes too
few trades to matter, and wins at most 4 of 8 folds.

## Giveback (descriptive)
| | trades | median MFE | median giveback | up at some point, closed flat or down |
|---|---|---|---|---|
| Webull #382 (QQQ $/share) | 62 | 0.64 | 1.65 | 42 of 62 |
| #382 WF chain (NQ pts) | 2,345 | 18.0 (0.30R) | 25.3 (0.47R) | 1,393 |

Chain: MFE reaches 0.5R on 37% of trades, 1R on 21% and 1.5R on 12%. The 10-30 short (MFE 8.58, closed +0.74) is a common
shape, not a rare one.

## Grid, WF chain 2016-06-30 .. 2025-07-15 (four numbers, daily $ x20)
| cell | ROC@30k | DD5 | DD% | Sortino | folds won | trades changed |
|---|---|---|---|---|---|---|
| **HOLD** | **62.25** | $18.0k | 6.46 | **3.04** | - | - |
| Y0.5R X33% | 43.22 | $16.6k | 12.34 | 2.06 | 0/8 | 819 |
| Y0.5R X50% | 56.67 | $16.2k | 13.41 | 2.68 | 1/8 | 718 |
| Y0.5R X67% | 64.83 | $16.0k | 8.40 | 2.90 | 3/8 | 600 |
| Y1.0R X33% | 59.64 | $17.7k | 11.34 | 2.92 | 2/8 | 419 |
| Y1.0R X50% | 58.86 | $16.7k | 9.64 | 2.91 | 3/8 | 335 |
| Y1.0R X67% | 58.23 | $17.1k | 7.92 | 2.94 | 3/8 | 244 |
| Y1.5R X33% | 53.18 | $18.5k (1 episode) | 6.75 | 3.06 | 3/8 | 223 |
| Y1.5R X50% | 64.23 | $17.8k | 6.63 | 3.12 | 4/8 | 153 |
| Y1.5R X67% | 62.38 | $17.8k | 6.39 | 3.05 | 4/8 | 84 |

## Reading rule, applied
- Best cell by ROC@30k: Y0.5R X67%, 64.83. Its Sortino is 2.90 against HOLD's 3.04, so it fails rule 1. It wins 3 of 8 folds
  (rule 2), and its DD% is 8.40 against 6.46. Its ROC edge comes from a smaller worst DD, not from more money: net is $348k
  against $401k.
- Runner-up Y1.5R X50% beats HOLD on both ROC (64.23) and Sortino (3.12), but it wins only 4 of 8 folds and both neighbours
  fall below HOLD (Y1.5R X33% 53.18, Y1.0R X50% 58.86). It fails rules 2 and 3: an isolated cell, the kind a 9-cell grid
  throws up by chance.
- **NO LIFT.** This is the fourth exit-side cut on NOISE to fail (#490 target, shelf 39/41 holding rules, the 10-18
  re-reads). The giveback is the price of the fat right tail (the same lesson as ENGU-Q: the money is in the survivors).

## Caveats
- The chain is rebuilt on today's master: 2,345 trades / 20,074 pts against #382's stored 2,343 / 19,975. That is 0.5% drift
  from data edits since the run; folds 3 and 5 are exact. Fold bounds were moved past the two 2020 NT splices. Both arms use
  the same trades.
- Webull has 62 trades: descriptive only, too few for a test.

Nothing live changes.
