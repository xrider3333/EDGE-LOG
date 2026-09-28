# PRE-REGISTRATION — forward shadow test of KEEL v12 on TTM #458 (2026-09-28)

Committed before the first shadow trade is scored. Nothing below changes once scoring starts.

## Why
Owner, via MANAGER (inbox #24): "shadow TTM KEEL". On TTM #458 (the fixed-code re-validation of #455) KEEL v12
beat raw in the walk-forward on the owner's yardstick - 32.9 vs 29.1 %/yr at a $30k drawdown, Sortino 2.73 vs
2.40, 144 trades - but the lockbox has only 12 trades, under the 50-trade minimum (tools/book_legs_export/,
README Round 3). KEEL's learned part was tuned on NOISE, so on TTM it is closer to out-of-sample than on NOISE;
its compression tilt came from the TTM squeeze study itself, so that part is not.

## The arms (same signals and fills, only the size differs)
- **R  TTM #458 raw**: TTMSQZ_3_0_ES30SSOF2R347.py at #458's crowned settings (kc_mult 1.5, eod_cutoff 5),
  including the file's own ladder (3 / 4 / 7 whole ES contracts). ES 30m RTH.
- **K  TTM #458 + KEEL v12**: R x the KEEL v12 multiplier.
Each forward trade's P&L per arm = the leg's actual fill P&L x that arm's multiplier (1.0 for R). Scored on the
UNROUNDED multiplier so whole-contract rounding cannot favour an arm; the rounded-contract P&L is reported
beside it. No shadow orders.

## The exact KEEL build (what Frontier's #28 scored and what the shadow must run)
- augur_engine/ml_keel.py at commit 85be1b8 or later (gap_atr look-ahead fixed), CFG "v12", seed 42.
- Features: ml_keel.keel_features(arrays) on the ES 30m RTH NO-ADJUST master (db_noadj_rth; the file removes
  rolls itself), the same arrays the leg trades on.
- Trades: #458's own trade list, sorted by entry bar, P&L including the file's ladder.
- Live form: nightly ml_keel.keel_build_state(arrays, all resolved #458 trades, feats, seed=42, version="v12");
  each new entry sized by ml_keel.keel_score_from_state(state, arrays, entry_bar, feats=...)[0], which is capped
  at 3.0 by v12. The lane logs the multiplier per signal; contracts = ladder contracts x multiplier, rounded.
- Backtest reproduction: tools/book_legs_export/step7_ttm458.py (reproduces #458's stored blocks to the cent).

## Yardstick and decision rule (owner rule 2026-09-28)
- ROC %/yr at a $30k worst drawdown (30 x annual net / max drawdown, drawdown valued DAILY - TTM can hold overnight,
  so open trades are marked at each session close, as step7 does) and Sortino (per trade, annualised).
- K earns its keep only if it beats R on BOTH, and stays profitable without its single biggest trade.
- **Trade-count honesty:** #458 traded 16 times a year in the walk-forward and about 10 in the lockbox. The
  owner's 100-trade minimum would take 6-10 years and the 50-trade lockbox minimum 3-5. So: an informational read every 15 trades; the
  FIRST verdict at 50 forward trades; nothing earlier is a verdict. If the owner wants an answer sooner, the
  only honest faster evidence is another market or timeframe the rule was never tuned on - not a shorter test.

## Window and data rules
- Starts with the first #458 signal after the TTM / paper lane confirms the shadow multiplier is logged.
- ES contract rolls inside the window are logged; the file's own roll handling is what is scored.
- Scoring: the Custom ML chat, from the lane's log plus a same-day backtest replay cross-check. Nothing live
  changes on this test's say-so.
