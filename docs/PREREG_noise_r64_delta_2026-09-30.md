# PRE-REGISTRATION — NOISE round 64: order-flow delta at the breakout (2026-09-30)

Owner ask via MANAGER (inbox #14): keep assessing NOISE improvements as a queue; start with the NinjaTrader 10-second
buy/sell DELTA capture. Round 63 concluded new NOISE alpha needs new information - this is the first new information.
Written and committed BEFORE any NOISE trade outcome was split by delta. Only data QUALITY was read beforehand.

## The data (read before writing this; outcome-free)
`C:\EdgeLog\ohlc\NQ_10s.csv` (NinjaTrader chart indicator, front-month outright, bars stamped at their END, UTC): 70 RTH
sessions 2026-06-24 .. 2026-09-30. Delta is present on >= 80% of 10-second bars in 48 of them; the first three sessions
and several live sessions in late August / September carry little or no delta (a capture fault, routed to Paper: NT8).
5-minute bars rebuilt from it match the NQ 5-minute master bar for bar (return correlation 0.988, same sign 99.6%).
Tick-Replay backfill gets delta DIRECTION right and magnitudes only roughly, so this round uses SIGNS only.

## Mechanism
NOISE enters when a 5-minute close breaks the day's noise band. Order-flow research (e.g. Cont, Kukanov & Stoikov on
order-flow imbalance) finds aggressive net buying or selling predicts the next moves. A break made WITH aggressive
flow in its own direction should persist; a break made against the flow (price pushed through on passive fills while
aggressors lean the other way) should fail more often.

## The tag (computed at the SIGNAL bar - the 5-minute bar whose close triggered the entry; known before the fill)
BACKED = the sum of the 10-second deltas inside the signal bar has the same sign as the trade (positive for a long,
negative for a short). UNBACKED = the opposite sign. Zero or missing delta = untagged (excluded from both buckets).
Secondary, descriptive only: the session's cumulative delta from 09:30 to the signal bar's end, same sign rule.
Only sessions with delta on >= 80% of RTH 10-second bars and >= 2,000 RTH bars count.

## Base
NOISE #304's crown configuration (the family's raw twin) on the NQ 5-minute master, cost 0.533. Trades whose signal bar
lies in a usable session. The candidate variant is "#304, skipping UNBACKED trades".

## What this round can and cannot say
About 50 trades fall inside the usable sessions - far below the owner's 100 walk-forward / 50 lockbox minimums and far
too few to adopt anything. The historical read is DESCRIPTIVE: backed vs unbacked count, average $ per trade, win rate,
and the skip-unbacked variant's ROC at a $30k drawdown next to its twin, with a permutation of the tag within session
for scale. It decides only whether the forward shadow is worth running (it is run either way unless the capture cannot
support it).

## FORWARD SHADOW - the real test (bar fixed now)
From 2026-10-01 the capture keeps accumulating and the tag is computed after the fact from it; nothing live changes.
Read ONCE when 150 tagged forward trades exist on usable sessions (about six months), not before. The variant passes if
ALL hold on the forward trades alone:
1. "skip unbacked" beats plain #304 on ROC at a $30k drawdown (drawdown valued daily) AND on Sortino;
2. unbacked trades average less than backed trades, and fewer than 10% of 2,000 within-session tag permutations do as
   well (the tag must beat its own shape);
3. at least 50 trades in each bucket, and the variant stays profitable without its single biggest trade.
A pass earns a fenced Auto-Validate on the then-available capture and a paper shadow leg - still not an adoption.
Anything else found while reading (other thresholds, magnitudes, ES delta, other bases) is post-hoc and can only become
its own later pre-registration.
