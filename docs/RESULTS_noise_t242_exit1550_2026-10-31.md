# RESULTS - test 242 (b): NOISE #382 exit at the 15:50 close instead of the last bar - NO LIFT

Prereg docs/PREREG_noise_t242_exit1550_2026-10-31.md, locked d6df542d9e67 and pushed (49cdcad1) before this ran. Tool
tools/noise_t242_exit1550.py; record C:\EdgeLog\_anatomy_cache\t242\exit1550.json. Walk-forward chain 2016-2025
(9.04 years), lockbox never loaded. Same t74 rebuild of the chain (2,345 trades vs the stored 2,343, ~0.5% off; both arms
use the same trades).

| WF chain | ROC@$30k | DD5 | DD% from peak | Sortino | Net | Folds won |
|---|---|---|---|---|---|---|
| Hold (#382 as is) | 62.25 | $18.0k | 6.46 | 3.04 | $401.5k | - |
| Exit at the 15:50 close | 62.98 | $17.8k | 6.52 | 3.08 | $409.4k | 3 of 8 |

- 646 of 2,345 trades are still open at the 15:50 close and change; 329 are helped, 306 hurt (the rest unchanged).
- The early exit adds +$881 a year (+$8.0k over 9 years), after cost and with highs and lows - the permutation test's
  +862 pts x size before cost survives in size.
- It beats hold on ROC and Sortino by hair widths, but wins only 3 of 8 folds; the prereg bar is 5. Neither curve is one
  episode.

**Verdict: NO LIFT** under the locked rule. Nothing live changes. The last-bar effect is real in size on these trades but
it is not steady across years (fold 4 +$15.4k and fold 5 +$8.4k carry it; folds 2, 3, 7, 8 lose $3-6k each), and the lead
was found on these same trades, so it could not have been confirmed here anyway. This is the twelfth exit-side cut on #382
that does not clear the bar.
