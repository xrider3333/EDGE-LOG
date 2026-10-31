# Test 239 (was 75) Phase B, ORB half: ORB #314 trailing / breakeven exits - NO LIFT (2026-10-31)

Prereg LOCKED before the run: `docs/PREREG_t75b_exits_2026-10-31.md` (v73.1450 8cd5b80c, prereg_lock v1 sha 0cb05bb6,
re-checked by the tool before computing). Tool: `tools/orb_t239b_exits.py` (NOISE's overlay `tools/noise_t75b_exits.py`,
unchanged, on the ORB leg). #314's crowned config run ONCE on its own NQ 5m RTH master cut at the optimize end 2025-08-12;
the lockbox (2025-08-13 .. 2026-08-13) is never loaded. IS = 2010-06-07 .. 2021-12-31 (1,588 trades), OOS = 2022-01-01 ..
2025-08-12 (546 trades). ATR on #314's own bars; levels set on a bar's close act from the next bar; the leg's own stop,
breakeven and 15:30 exit still apply. One contract x $20, cost 0.533 pts.

## Verdict
**NO LIFT - 0 of 5.** On OOS every exit loses to hold on ROC@30k and on Sortino, and none wins more than 1 of 4 OOS years.
- Best on OOS: E5 (breakeven at 1R, then a 2-ATR trail) ROC@30k 53.63 vs hold 77.94, Sortino 2.23 vs 2.92, 0/4 years.
- E1 (3-ATR trail) is the only exit ahead of hold in IS (ROC 11.07 vs 8.97) but it halves OOS (35.85 vs 77.94), 1/4 years.
Plain words: every trail cuts ORB's big trend days short, and those days are where the money is. Hold keeps the most of each
trade's best move (OOS 16.9% of MFE captured vs 2.6-13.0% for the trails). Leave the exits alone.

## Main line: full run, IS and OOS
| Stretch | Exit | ROC@30k | DD5 $ | DD% | Sortino | One episode | Years won | MFE captured | Median giveback (R) | Trades changed |
|---|---|---|---|---|---|---|---|---|---|---|
| IS 2010-21 | HOLD | 8.97 | 15,577 | 16.6 | 1.06 | yes | - | 10.8% | 0.47 | 0 |
| OOS 2022-25.08 | HOLD | 77.94 | 19,962 | 16.3 | 2.92 | no | - | 16.9% | 0.50 | 0 |
| IS 2010-21 | E1 ATR trail 3x14 | 11.07 | 9,674 | 9.5 | 0.91 | yes | 6/12 | 6.8% | 0.53 | 1308 |
| OOS 2022-25.08 | E1 ATR trail 3x14 | 35.85 | 18,343 | 18.5 | 2.12 | yes | 1/4 | 9.2% | 0.56 | 440 |
| IS 2010-21 | E2 Chandelier 3x22 | 4.05 | 10,973 | 17.6 | 0.52 | yes | 5/12 | 4.4% | 0.51 | 1407 |
| OOS 2022-25.08 | E2 Chandelier 3x22 | 47.97 | 14,309 | 11.0 | 2.51 | yes | 1/4 | 10.1% | 0.53 | 471 |
| IS 2010-21 | E3 6-bar trail | 1.91 | 6,861 | 18.2 | 0.31 | yes | 3/12 | 2.8% | 0.48 | 1519 |
| OOS 2022-25.08 | E3 6-bar trail | 7.72 | 17,312 | 29.0 | 0.71 | yes | 1/4 | 2.6% | 0.53 | 517 |
| IS 2010-21 | E4 Time-decay ATR trail | 6.31 | 10,089 | 13.4 | 0.75 | yes | 4/12 | 5.2% | 0.49 | 1533 |
| OOS 2022-25.08 | E4 Time-decay ATR trail | 9.34 | 15,934 | 17.2 | 0.62 | yes | 0/4 | 2.8% | 0.54 | 529 |
| IS 2010-21 | E5 BE 1R + 2 ATR trail | 9.68 | 14,382 | 17.6 | 0.87 | yes | 4/12 | 9.2% | 0.50 | 249 |
| OOS 2022-25.08 | E5 BE 1R + 2 ATR trail | 53.63 | 21,505 | 18.9 | 2.23 | no | 0/4 | 13.0% | 0.53 | 83 |

## Second line: test 238's WF chain (2016-07-13 .. 2025-08-12)
| Stretch | Exit | ROC@30k | DD5 $ | DD% | Sortino | One episode | Years won | MFE captured | Median giveback (R) | Trades changed |
|---|---|---|---|---|---|---|---|---|---|---|
| WF chain | HOLD | 26.39 | 24,234 | 22.1 | 1.85 | yes | - | 13.7% | 0.53 | 0 |
| WF chain | E1 ATR trail 3x14 | 14.22 | 20,539 | 19.4 | 1.14 | no | 4/10 | 6.4% | 0.57 | 1011 |
| WF chain | E2 Chandelier 3x22 | 13.44 | 17,799 | 23.4 | 1.18 | yes | 3/10 | 6.2% | 0.56 | 1069 |
| WF chain | E3 6-bar trail | 1.18 | 20,948 | 27.0 | 0.14 | yes | 1/10 | 1.2% | 0.53 | 1148 |
| WF chain | E4 Time-decay ATR trail | 4.51 | 18,537 | 21.2 | 0.41 | yes | 3/10 | 2.5% | 0.54 | 1167 |
| WF chain | E5 BE 1R + 2 ATR trail | 17.76 | 25,168 | 27.5 | 1.35 | yes | 2/10 | 10.2% | 0.55 | 195 |

Same verdict: every exit below hold (best E5 17.76 vs 26.39, Sortino 1.35 vs 1.85).

## Parity
- Full run: one backtest of the stored champion params (2,134 trades); there is no stored full-run trade list to match.
- WF chain: test 238's rebuild, 7 of 8 folds bit-exact; fold 4 differs (133 vs 135 trades) by the two 2020 NT splices on
  today's NQ master. Chain 12,932.2 pts / 1,201 trades vs stored 12,627.4 / 1,203. Hold and every exit use the same trades.

Outputs: `C:\EdgeLog\_anatomy_cache\t239b_orb\` (full_grid.csv, chain_grid.csv).
