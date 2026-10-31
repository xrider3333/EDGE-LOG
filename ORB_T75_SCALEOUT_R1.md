# Test 75, ORB half: ORB #314 scale-out exits - NO LIFT (2026-10-31)

Prereg: `docs/PREREG_noise_orb_t75_scaleout_2026-10-31.md` (28885f3c) + ORB addendum
`docs/PREREG_orb_t75_scaleout_addendum_2026-10-31.md` (b33f9789, pushed before any simulation: fixed triggers QQQ 2/4/6 =
0.290/0.580/0.870% of entry; chain + R = test 74's rebuild). Tool: `tools/orb_t75_scaleout.py`. WF chain only
(2016-07-13 .. 2025-08-12, 8 anchored folds), lockbox never loaded, live leg unchanged.

## Verdict
**NO LIFT.** The best cell by WF ROC@30k is take 2/3 off at 2R (BE on or off - identical, because ORB's own breakeven
already sits at entry by then): ROC@30k 28.05 vs HOLD 26.39, DD5 $23,199 vs $24,234, DD% 20.7 vs 22.1, but Sortino
1.75 vs 1.85, and it wins only 2 of 8 folds. Reading rule fails at step 1 (Sortino) and step 2 (folds).
Plain words: banking part of a 2R winner smooths the worst stretch a little but gives up more than it saves in most
years; every 1R and fixed-point cell is worse outright. Higher MFE captured never shows up either - HOLD keeps the most
(13.7%). Leave the exits alone.

## Grid (WF chain, one contract x $20, cost 0.533 pts + one extra exit at 0.2665 x F)
| Cell | ROC@30k | DD5 $ | DD% | Sortino | One episode | Folds won | Trades scaled | MFE captured |
|---|---|---|---|---|---|---|---|---|
| HOLD (leg as is) | 26.39 | 24,234 | 22.1 | 1.85 | yes | - | 0 | 13.7% |
| T1R F1/3 BEoff | 23.60 | 23,716 | 22.9 | 1.62 | yes | 1/8 | 236 | 12.1% |
| T1R F1/3 BEon | 24.17 | 23,565 | 22.5 | 1.62 | yes | 1/8 | 236 | 12.1% |
| T1R F1/2 BEoff | 22.16 | 23,524 | 23.3 | 1.50 | yes | 1/8 | 236 | 11.3% |
| T1R F1/2 BEon | 22.56 | 23,411 | 23.0 | 1.50 | yes | 1/8 | 236 | 11.3% |
| T1R F2/3 BEoff | 20.69 | 23,416 | 23.8 | 1.39 | yes | 1/8 | 236 | 10.5% |
| T1R F2/3 BEon | 20.94 | 23,340 | 23.6 | 1.39 | yes | 1/8 | 236 | 10.5% |
| T2R F1/3 BEoff | 27.17 | 23,717 | 21.4 | 1.80 | no | 2/8 | 57 | 13.4% |
| T2R F1/3 BEon | 27.17 | 23,717 | 21.4 | 1.80 | no | 2/8 | 57 | 13.4% |
| T2R F1/2 BEoff | 27.60 | 23,458 | 21.1 | 1.77 | no | 2/8 | 57 | 13.2% |
| T2R F1/2 BEon | 27.60 | 23,458 | 21.1 | 1.77 | no | 2/8 | 57 | 13.2% |
| T2R F2/3 BEoff | 28.05 | 23,199 | 20.7 | 1.75 | no | 2/8 | 57 | 13.0% |
| T2R F2/3 BEon | 28.05 | 23,199 | 20.7 | 1.75 | no | 2/8 | 57 | 13.0% |
| T2Q F1/3 BEoff | 24.37 | 20,298 | 19.9 | 1.67 | yes | 1/8 | 769 | 10.7% |
| T2Q F1/3 BEon | 19.03 | 16,754 | 16.8 | 1.23 | yes | 1/8 | 769 | 7.3% |
| T2Q F1/2 BEoff | 23.03 | 18,463 | 18.7 | 1.51 | yes | 1/8 | 769 | 9.2% |
| T2Q F1/2 BEon | 18.38 | 16,112 | 16.3 | 1.11 | yes | 1/8 | 769 | 6.6% |
| T2Q F2/3 BEoff | 21.35 | 16,936 | 17.3 | 1.30 | no | 1/8 | 769 | 7.7% |
| T2Q F2/3 BEon | 17.09 | 15,596 | 16.3 | 1.00 | yes | 1/8 | 769 | 6.0% |
| T4Q F1/3 BEoff | 21.05 | 22,385 | 24.2 | 1.58 | yes | 0/8 | 484 | 11.3% |
| T4Q F1/3 BEon | 16.99 | 21,560 | 24.9 | 1.28 | yes | 0/8 | 484 | 9.1% |
| T4Q F1/2 BEoff | 18.46 | 22,029 | 25.4 | 1.42 | yes | 0/8 | 484 | 10.1% |
| T4Q F1/2 BEon | 15.42 | 21,566 | 26.0 | 1.18 | yes | 0/8 | 484 | 8.4% |
| T4Q F2/3 BEoff | 15.92 | 22,029 | 26.7 | 1.24 | yes | 0/8 | 484 | 8.9% |
| T4Q F2/3 BEon | 13.90 | 21,720 | 27.1 | 1.08 | yes | 0/8 | 484 | 7.8% |
| T6Q F1/3 BEoff | 22.06 | 23,970 | 23.2 | 1.55 | yes | 0/8 | 302 | 11.5% |
| T6Q F1/3 BEon | 17.63 | 24,607 | 25.2 | 1.36 | yes | 0/8 | 302 | 10.2% |
| T6Q F1/2 BEoff | 19.86 | 24,371 | 23.8 | 1.39 | yes | 0/8 | 302 | 10.4% |
| T6Q F1/2 BEon | 16.60 | 24,849 | 25.4 | 1.25 | yes | 0/8 | 302 | 9.4% |
| T6Q F2/3 BEoff | 17.65 | 24,773 | 24.5 | 1.23 | no | 0/8 | 302 | 9.2% |
| T6Q F2/3 BEon | 15.52 | 25,091 | 25.5 | 1.14 | yes | 0/8 | 302 | 8.6% |

## Parity
Same chain as test 74: 7 of 8 folds bit-exact against #314's stored folds; fold 4 (2019-12-06 .. 2021-01-28) differs
(133 trades / -827.7 pts vs stored 135 / -1,132.5) by the two 2020 NT splices on today's NQ master. Chain total
12,932.2 pts / 1,201 trades vs stored 12,627.4 / 1,203. Every cell and HOLD use the same rebuilt trades.

Outputs: `C:\EdgeLog\_anatomy_cache\t75_scaleout_orb\grid_wf.csv`.
