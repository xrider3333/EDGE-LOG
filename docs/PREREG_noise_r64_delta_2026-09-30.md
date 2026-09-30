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

## ADDENDUM 2026-09-30, written AFTER the historical read (commit of the read: see NOISE.md round 64)
The historical read showed the pre-registered SIGNAL-BAR tag barely separates anything: 25 of 29 breakouts are backed by
their own bar's delta (a bar that closes through the band usually carries same-sign flow), so skipping the 4 unbacked
trades cannot move much. The session CUMULATIVE delta split (descriptive) pointed the right way on 7 unbacked trades.
Because that was SEEN on the historical 30 trades, it is added here as a SECOND forward shadow only - its historical read
counts for nothing. Same forward bar, same read point (150 tagged forward trades from 2026-10-01), read together with the
first; with two shadows read at once, the permutation line for either is tightened to fewer than 5% of shuffles.
Tag: CUM-BACKED = the session's cumulative 10-second delta from 09:30 to the signal bar's end has the trade's sign.

## ADDENDUM 2 - 2026-09-30 evening: audit of the build (owner ask via MANAGER inbox #16), before any forward trade
1. Stamps: the 10-second rows are stamped at bar END. Rebuilt 5-minute bars match the master's close exactly on 92% of
   bars under the END mapping and on 3% under a START mapping (open 92% vs 3%); the capture writes true UTC seconds.
2. No look-ahead: a trade's first field is its fill bar (entry price = that bar's open on all 309 trades since 2025-06),
   the signal bar is the one before it on the same day, and both tags use only 10-second bars that end by the signal
   bar's close. Time zones are converted from UTC to New York, so the 2026-11-01 clock change is handled; the guard below
   would also catch any shifted stamp.
3. Reproduction: the tool read whatever capture existed, so re-running it later changed the sample. It is now pinned to
   the recorded last session (2026-09-29) and reproduces the recorded numbers exactly.
4. One data error: on 2026-09-14 the capture was already on the December contract while the price master was still on
   September (about a 298-point gap, 31% of closes matching). A PRICE GUARD now applies to every read, the forward
   shadows included: a session counts only if at least 80% of its rebuilt 5-minute closes equal the master's exactly
   (median session 96%). It drops 09-14 and 08-19 (59%, partly back-filled). Guarded read (r37_results/
   r64_delta_read_guarded.txt): 29 trades; signal-bar tag 74% of shuffles (no signal, unchanged); cumulative delta 7
   unbacked lost $3,159, 16% of shuffles (unchanged conclusion). Nothing else in this pre-registration changes.
