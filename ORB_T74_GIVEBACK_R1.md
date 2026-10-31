# Test 74, ORB half: ORB #314 MFE giveback stop - NO LIFT (2026-10-31)

Prereg: `docs/PREREG_orb_t74_giveback_2026-10-31.md` (pushed 061f218e before any simulation). Tool: `tools/orb_t74_giveback.py`.
WF chain only (2016-07-13 .. 2025-08-12, 8 anchored folds), lockbox never loaded, live leg unchanged.

## Verdict
**NO LIFT.** All 9 giveback cells lose to HOLD on WF ROC@30k (best 22.97 vs 26.39) and on Sortino (best 1.72 vs 1.85).
No cell wins more than 3 of 8 folds. Reading rule fails at step 1 for every cell; steps 2-3 are moot.
Plain words: cutting ORB's winners short once they have run costs more on the trades that would have gone on to the
target than it saves on the ones that came back. Leave the exits alone.

## Grid (WF chain, one contract x $20, cost 0.533 pts)
| Cell | ROC@30k | DD5 $ | DD% | Sortino | Folds won | Trades changed |
|---|---|---|---|---|---|---|
| HOLD (leg as is) | 26.39 | 24,234 | 22.1 | 1.85 | - | - |
| Y0.5R X33% | 14.67 | 23,273 | 25.4 | 1.04 | 0/8 | 536 |
| Y0.5R X50% | 17.27 | 22,588 | 21.3 | 1.10 | 1/8 | 459 |
| Y0.5R X67% | 21.36 | 22,962 | 21.8 | 1.45 | 3/8 | 372 |
| Y1.0R X33% | 17.36 | 25,117 | 26.6 | 1.37 | 2/8 | 173 |
| Y1.0R X50% | 20.15 | 24,290 | 25.3 | 1.48 | 0/8 | 131 |
| Y1.0R X67% | 22.97 | 24,088 | 23.3 | 1.61 | 2/8 | 88 |
| Y1.5R X33% | 21.32 | 25,601 | 25.1 | 1.61 | 3/8 | 72 |
| Y1.5R X50% | 21.92 | 25,930 | 25.9 | 1.70 | 1/8 | 49 |
| Y1.5R X67% | 22.29 | 25,954 | 25.1 | 1.72 | 1/8 | 29 |

The gentler the stop (higher Y, higher X), the closer to HOLD - the curve only approaches HOLD from below.

## Descriptive (read after the prereg)
- **Webull ORB, 13 closed trades** (box backup 2026-10-30, QQQ 1m; one open-at-EOD row without an exit price dropped):
  median MFE 3.61 $/share, median giveback 2.91; 6 trades were up at some point and closed flat or down.
- **#314 WF chain, 1,201 trades:** MFE >= 0.5R on 49%, >= 1R on 20%, >= 1.5R on 10%; median giveback 0.53R.
  Giving back is normal for this leg; the grid shows locking it in is worse.

## Parity
7 of 8 folds bit-exact against the stored run. Fold 4 (2019-12-06 .. 2021-01-28) differs: 133 trades / -827.7 pts against
the stored 135 / -1,132.5, because today's NQ master carries the two 2020 NT splices (2020-02-28 +60 bars, 2020-06-30
+69 bars) that #314's master did not. Chain total 12,932.2 pts / 1,201 trades vs stored 12,627.4 / 1,203. Both arms
use the same rebuilt trades, so the comparison is like-for-like; the chain's absolute numbers are not #314's stored ones.

Outputs: `C:\EdgeLog\_anatomy_cache\t74_giveback_orb\` (grid_wf.csv, chain_314_mfe.csv, webull_orb_mfe.csv, giveback_hist.png).
