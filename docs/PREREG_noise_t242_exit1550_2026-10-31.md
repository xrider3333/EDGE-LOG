# PREREG - test 242 (b): NOISE #382 exits one bar early (15:50 close instead of the 15:55 bar's close)

Written and locked 2026-10-31 BEFORE the engine check below is run. Owner of the test: NOISE lane. Ask: MANAGER #152.

## Where the idea came from - this check is NOT out of sample

MANAGER-AGENT's permutation test (C:\EdgeLog\_anatomy_cache\mfe_perm\report.md) ran on the SAME #382 walk-forward chain
trades this check uses (t74 rebuild, 2,345 trades). On the 620 trades that ride to the session close, the last 5-minute
bar went against the position 52% of the time (bars in random order: 43%), and leaving at the 15:50 bar's close instead of
the last bar's close was worth +862 pts x size over 9 years before cost (null -1,375, 95% band -2,241 to -508).

The lead was FOUND on these trades. Checking it again on the same trades with highs, lows and cost can only KILL it, not
confirm it. A pass here means "worth watching forward", nothing more. Only the lockbox or forward trades could confirm it,
and the lockbox stays unread (it is spent and veto-only).

## The one cell (no grid, no neighbours to choose from)

- Leg: NOISE #382 as it is (entry, stops, VWAP exit, everything unchanged).
- Change: a trade STILL OPEN at the close of the session's second-to-last 5-minute bar (the bar stamped 15:50 ET on a
  normal day, 12:50 on a half day) exits at that bar's close instead of riding into the last bar.
- Trades that exit before that point are untouched, including any protective stop or VWAP exit that triggers during the
  15:50 bar itself. A stop that would have hit inside the LAST bar stays counted for hold (hold = the leg as it is).
- Fill: the 15:50 bar's close, the same convention the engine uses for its own flat at the last bar's close. Both prices sit
  inside regular trading hours with the market's deepest close-of-day liquidity; no extra round trip, cost is unchanged
  (0.533 pts per contract per round trip, the house NQ cost, one round trip per trade on both arms).

## How it is measured

- Trades: the t74 rebuild of #382's walk-forward chain (tools/noise_t74_giveback.py `chain()`), NQ 5-minute RTH bars,
  #382's own master and window. Known caveat: the rebuild is ~0.5% off #382's stored trades on today's master; both arms
  use the same rebuilt trades, so the comparison is like for like.
- Numbers: walk-forward stretch only, daily dollars via augur_engine.drawdowns.four_numbers: ROC@$30k, DD5, DD% from peak,
  Sortino. Plus folds won (of 8), dollars per year difference, trades affected, and the share of affected trades the early
  exit helped.

## Reading rule (fixed now)

The 15:50 exit is a LIFT only if ALL hold:
1. It beats hold on walk-forward ROC@$30k AND walk-forward Sortino.
2. It wins at least 5 of the 8 folds (fold net dollars higher than hold's).
3. It is not one episode: its worst drawdown is no more than 1.3 x its DD5, or the flag is unchanged from hold's.

Anything else is NO LIFT and nothing changes. Even a LIFT changes nothing live: it goes to MANAGER as "watch forward".
Prior that it passes: about 25% (the shuffle test ranked it at the top of its null, but on closes only and before cost).
