# RESULTS - M6 peak-age validate on NOISE #382 (board t82)

Prereg: `docs/PREREG_noise_m6_peakage_2026-11-01.md`, locked (sha 7363528909e4) and pushed (v87.84 518abe2d) before any
number. Tool: `tools/noise_t82_peakage.py`. Outputs: `C:\EdgeLog\_anatomy_cache\t82_peakage\{chain,full}.csv`.
Lockbox never loaded (every load stops at the optimize end 2025-07-15).

## Verdict
**M6 PASSES the preregistered bar on the WF chain at both weights, and it is NOT a time exit: the 10-bar time control
loses badly at both weights (0 of 8 folds).** But the descriptive second line (the crown run once, IS/OOS) shows the
lift is mostly drawdown shape: M6 nets slightly LESS money there in both halves and wins 4/12 IS years and 2/4 OOS
years. And the lead came from these same chain trades, with its tighter neighbours below hold in test 244. Read: a
real candidate, not a finding. Nothing live changes. Next step per the prereg: a full-range Auto-Validate on the
ranged PA file - drafted below, NOT queued until the owner says go.

## Primary: WF chain (8 folds, fresh engine per fold with each fold's champion params)
Parity: pa_mode off = test 74's chain rebuild trade for trade (2,345 trades / 20,073.95 pts) - PASS. The rebuild is
about 0.5% off #382's stored chain (2,343 / 19,974.5; 2 of 8 folds bit-exact) - same caveat as tests 74-245.

| cell | ROC@30k | DD5 | DD% | Sortino | net | folds won | trades changed |
|---|---|---|---|---|---|---|---|
| HOLD | 62.25 | $18.0k | 6.46 | 3.04 | $401.5k | - | 0 |
| M6 w0.50 | 69.57 | $16.8k | 6.92 | 3.28 | $422.8k | 7/8 | 475 |
| M6 w1.00 | 77.85 | $16.1k | 8.50 | 3.47 | $444.1k | 7/8 | 475 |
| TIME w0.50 | 58.47 | $13.7k | 6.96 | 2.66 | $301.2k | 0/8 | 1,079 |
| TIME w1.00 | 36.11 | $14.8k | 15.33 | 1.84 | $200.8k | 0/8 | 1,079 |

Reading rule, per M6 cell: (1) beats HOLD on ROC and Sortino - yes both; (2) >= 5/8 folds - 7/8 both; (3) not one
episode - neither flagged (worst DD $18.9k / $20.2k vs 1.3 x DD5); (4) beats TIME at the same weight on ROC and
Sortino - yes, by 11 / 42 ROC points. The one losing fold is fold 3 (2016-17 era): $2.7k vs hold's $16.8k at w1.00.
DD% from peak is WORSE at w1.00 (8.50 vs 6.46) - the bigger account curve makes its dips deeper in % terms.

## Second line (descriptive, not the verdict): crown params, run once
| cell | stretch | ROC@30k | DD5 | DD% | Sortino | net | years won |
|---|---|---|---|---|---|---|---|
| HOLD | IS 2010-21 | 41.16 | $10.3k | 6.00 | 2.43 | $226.9k | - |
| M6 w0.50 | IS 2010-21 | 48.26 | $10.2k | 5.17 | 2.50 | $223.4k | 4/12 |
| M6 w1.00 | IS 2010-21 | 51.27 | $9.9k | 5.83 | 2.54 | $219.9k | 4/12 |
| HOLD | OOS 2022-25.07 | 129.32 | $17.5k | 10.22 | 4.30 | $318.1k | - |
| M6 w0.50 | OOS 2022-25.07 | 140.66 | $15.5k | 9.24 | 4.35 | $316.5k | 2/4 |
| M6 w1.00 | OOS 2022-25.07 | 152.51 | $14.9k | 8.64 | 4.35 | $315.0k | 2/4 |
| TIME w1.00 | OOS 2022-25.07 | 58.28 | $13.9k | 11.11 | 2.46 | $149.0k | 0/4 |

On the crown run the ROC lead comes from a smaller worst drawdown with about the same money (-$3k to -$7k) and a
Sortino that is level - the drawdown-shape pattern of tests 239/240. On the chain (fold params) the money is real
(+$42.6k, 7/8 folds). The two lines disagree on money; the chain is the preregistered verdict line.

## What it means in plain words
- MANAGER's doubt is answered: M6 is not a time exit in disguise. Cutting every trade at 10 bars loses about half the
  leg; cutting only stalled runners that already reached half a risk unit costs nothing and trims drawdowns.
- It is still the best of many cells found on the same trades. Two independent things would make it real: a
  full-range validate (does the search pick it, and do its neighbours hold?) and forward trades.

## Drafted, NOT queued: full-range Auto-Validate
`NOISE_1_8_CT304_PA.py` already carries open ranges (pa_mode off/peak_age/time_exit, pa_n 3-20, pa_arm_r 0.25-2.0,
pa_weight 0.25-1.0; off = #382 is in the space). Shape: #382's own (NQ 5m RTH, its master pinned, 2010-06-07 ..
2026-07-16 with the 12-month lockbox veto-only, 8 folds, warm 300, cost 0.533, 900 trials). Reading rule to write in
that prereg: crowned pa_mode is peak_age, beats its off twin on WF ROC and Sortino, folds, not one episode, and both
pa_n neighbours keep WF ROC above the twin's. Owner GO needed.
