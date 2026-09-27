# PRE-REGISTRATION — forward paper test of ORB #314's learned tree sizing (2026-09-27)

Committed before the first forward trade is scored. Nothing below changes once scoring starts; anything
learned afterwards goes in a POST-HOC section.

## Why
Of every learned ML sizing measured on 2026-09-27 (tools/book_legs_export/, C:\EdgeLog\book_legs), ORB #314's
HYBRID DD tree is the one that beat raw in BOTH stretches after a walk-forward pick, with its lockbox scored
by a model frozen at the lockbox start: return per drawdown WF 1.41 vs raw 1.18, LB 4.45 vs 3.80; at raw's
lockbox drawdown $102,087 vs $87,132. It added nothing inside Frontier's book (round 61: 137.4 vs raw 145.8
at matched drawdown). One lockbox year of ~150 trades cannot separate that from luck. Only data it has never
seen can.

## What is sized (fixed now, nothing tuned forward)
- Base: ORB #314 = ORB_3_6_R6.py at run #314's settings - the existing paper leg ORB_R6 and its REAL fills.
- Overlay: augur_engine/ml_gate.py's hybrid rule for model "tree": the gate's win probability p from the
  tree model fitted on ORB #314's own resolved trades (entry_features_causal, |pnl|-weighted, refit every 25
  resolved trades exactly as gate_trades does); SKIP when p < 0.45 (the crowned gate's cut-off); otherwise
  weight w = clip(1 + 4 (p - 0.5), 0.25, 3.0), divided by the mean weight of run #314's PRE-LOCKBOX
  survivors (a fixed number: tools/book_legs_export/step3_hybrid.py computes it deterministically from
  pre-lockbox data only, and it is recorded in the first scoring report), capped at 3.0, times the
  walk-forward drawdown factor 1.2785 (frozen; C:\EdgeLog\book_legs\_summary_ORB314_hybdd_tree.json).
- SHADOW ONLY. No second order is placed. The tree-sized P&L of each forward trade = the paper leg's actual
  fill P&L x w (0 when skipped). Same fills, same slippage, so execution cannot decide the test.

## Window and stopping rule
- Starts with the first ORB_R6 paper trade entered on or after 2026-09-28. Ends at the earlier of 120
  forward trades or 2027-06-30. No verdict is read before 60 trades; the 60-trade read is informational.

## Pass bar (all three at the end)
1. At matched drawdown the tree beats raw: tree net x (raw max DD / tree max DD) > raw net.
2. Sortino (augur_engine.analytics.sortino_from_pnls, per trade, annualised) tree >= raw.
3. The skips earn their keep: the summed raw P&L of skipped trades is <= 0.
PASS -> the tree sizing becomes a candidate for a live ORB size layer (owner decision). FAIL on any -> ORB
stays raw; the lockbox result is filed as not forward-confirmed.

## Who does what
- Scoring: the Custom ML chat, offline, from the ORB_R6 paper blotter plus a same-day backtest replay as a
  cross-check (any trade the replay cannot match is reported, never silently dropped). Nothing live changes.
- A contract roll inside the window (December 2026) is scored as the paper leg traded it, and flagged.
