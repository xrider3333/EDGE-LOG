# PRE-REGISTRATION — fixed-rule sizing round 1: ORB #314 risk-parity / time-of-day, TTM #458 KEEL parts (2026-09-28)

Written and pushed BEFORE any number below was computed. Owner ask via MANAGER inbox #24: fixed sizing rules
(no learned gates), chosen before looking, judged on the owner yardstick. Anything learned after goes in POST-HOC.

## Dead-hunt check (why these two and not the obvious ones)
Already dead on ORB / ENGU-Q, do not re-test: the NOISE compression tilt (ORB #314 fails flat leverage, WF DD
+13.6%), Friday (fails ENGU-Q), depth, FOMC pre-statement and BLS-release tilts (all fail by stretch),
release-day ORB 1.5x, calendar / sequence / cross-state / NQ-vs-ES tilts (~175 candidates, 0 pass), learned
gates, book re-weighting, book volatility dial, risk-parity on ENGU-Q 1m. What has NOT been judged on a current
crown: ORB's own July sizing overlay (augur_engine/sizing.py, ORB.md sections 4.7 and 4.10). It was measured on
ORB 3.x, which was later voided for its volatility-filter look-ahead, and never re-run on #314.

## Test A — ORB #314 execution-layer sizing (the ORB.md rules, frozen as written in July)
Mechanism: constant dollar risk per trade (a wide opening range means a wide stop, so fewer contracts) removes
the size noise that ORB's P&L inherits from its stop width; morning breakouts carried about twice the profit
factor. Neither rule reads a trade's outcome.
- Trades: ORB_3_6_R6.py at run #314's settings, NQ 5m RTH db_noadj_rth, cost 0.533, $20/pt, 2010-06-07 ..
  2026-08-13 (the run's own window). ORB is flat by the close: daily = sum of the session's trades.
- Risk = stop_frac 2.5 x the session's opening-range width (or_bars 2), exactly sizing.trade_features.
- Arms (multiplier on one contract, same trades):
  - R    raw, 1.0.
  - RP   risk parity, CAUSAL form: (median risk of the previous 100 trades, min 20, else 1.0) / this trade's
         risk, capped at 3.0. (The July form divided by the whole-history mean, which on a tape whose price rose
         ten-fold is an era re-weighting that could not be traded; the causal form is the live rule.)
  - TT   time tilt, sizing.DEFAULT_TIME_TIERS: 2.0 in the first hour, 1.0 to the third hour, 0.5 after.
  - RPTT RP x TT, capped at 3.0.
- Stretches (run #314's gate_validate dates): WF 2016-07-13 .. 2025-08-13; LB 2025-08-13 .. 2026-08-13.

## Test B — TTM #458: which part of KEEL carries its walk-forward win (design input for the TTM shadow)
KEEL v12 beat raw in #458's WF (32.9 vs 29.1 %/yr at $30k DD). Learned gates are out, so the question is whether
the fixed parts alone do it. Trades = C:\EdgeLog\book_legs\TTM458_raw_trades.csv (step7, reproduces #458).
- Arms: R raw; FX the NOISE fixed package unchanged (compression 1.5x, Friday 1.5x, cap 3, FOMC pre-14:00 0.5x =
  ml_keel.compression_sizes on the ES 30m RTH arrays); EV FOMC half-size only; K KEEL v12 seed 42 (the file).
- Honest limit: LB has 12 trades, far under 50 - Test B can only choose WHICH arm the forward shadow carries,
  never pass anything. Compression 1.5x was a by-product of the TTM study itself, so FX is not unseen on TTM.

## Yardstick and pass bar (owner rule 2026-09-28), per arm vs its raw twin R
1. ROC %/yr at a $30k worst drawdown (= 30 x annual net / max daily drawdown) higher than R's in WF AND in LB.
   (Scale-free, so an arm that only adds size cannot win - it is the uniform-leverage control built in.)
2. Sortino (analytics.sortino_from_pnls, per stretch) higher than R's in WF AND in LB.
3. At least 100 WF and 50 LB trades; LB net positive without its single biggest trade.
4. Aim, not shape: WF ROC above the 98.3th percentile (0.05 / 3 arms) of 500 random permutations of the same
   arm's multipliers across the same trades (seed 20260928).
An ORB arm passing 1-4 becomes a forward SHADOW arm on the ORB_R6 paper leg beside the tree test (no live
change; owner decides via MANAGER) and is offered to Frontier as a book-leg stream. Failing any clause = dead,
written to the ledger. Test B's pick = the arm with the best WF ROC among arms that also beat R on WF Sortino;
if that is FX or EV (a fixed rule), it is proposed as a third arm of the TTM shadow.
Driver: tools/fixed_sizing_r1.py (pushed with the results).

## RESULT (2026-09-28, run once, as registered) - nothing passes; no validate queued
Test B stretches = the export's stage column (WF 2016-07-27 .. 2025-07-09, LB .. 2026-06-30).

| arm | WF ROC @ $30k DD | WF Sortino | LB ROC | LB Sortino | LB ex-top $ | perm pct | verdict |
|---|---|---|---|---|---|---|---|
| ORB R raw | 35.3 | 2.22 | 113.8 | 3.09 | 67,932 | - | twin (1,290 WF / 168 LB trades) |
| ORB RP causal risk parity | 34.9 | 2.18 | 110.5 | 3.52 | 65,770 | 71.0 | FAIL (WF ROC, WF Sortino, LB ROC, perm) |
| ORB TT time tilt | 25.6 | 2.00 | 102.1 | 2.88 | 117,818 | 15.2 | FAIL (all) |
| ORB RPTT both | 29.3 | 2.07 | 100.4 | 3.43 | 115,540 | 52.2 | FAIL (WF ROC, WF Sortino, LB ROC, perm) |
| TTM R raw | 29.3 | 2.41 | 239.6 | 9.08 | 16,050 | - | twin (144 WF / 12 LB trades) |
| TTM FX NOISE fixed package | 33.3 | 2.35 | 171.6 | 6.57 | 22,178 | 82.6 | FAIL |
| TTM EV FOMC half only | 29.7 | 2.45 | 239.6 | 9.08 | 16,050 | 78.2 | FAIL (fires on 8 trades) |
| TTM K KEEL v12 s42 | 33.1 | 2.74 | 267.7 | 11.76 | 41,063 | 75.8 | FAIL (LB trades 12 < 50, perm) |

- **ORB:** the July sizing overlay does not survive on crown #314. The morning tilt is now actively harmful
  (WF ROC 35.3 -> 25.6); risk parity is a wash. Its July win belonged to the voided ORB 3.x. Dead - ORB stays raw.
- **TTM:** no fixed part carries KEEL's walk-forward gain. Compression is on for 233 of 246 trades (TTM enters
  in squeezes), so FX is near-uniform leverage x Friday and loses Sortino; the FOMC rule touches 8 trades.
  KEEL's own WF gain sits at the 76th percentile of its sizes shuffled across the same trades, i.e. the WF
  edge is not distinguishable from its size SHAPE. The TTM shadow (docs/PREREG_ttm458_keel_shadow_2026-09-28.md)
  therefore stays two arms (raw vs KEEL); no fixed third arm is proposed, and expectations should be low.
