# PRE-REGISTRATION — NOISE round 67: the break must clear the overnight extreme (2026-09-30)

Queue item after round 66 (owner ask via MANAGER, inbox #16: keep testing NOISE, auto-validate anything promising).
Written and committed before any cleared/uncleared trade split was computed. Looked at first, data availability only: the
NQ 5-minute ETH no-adjust master (restored 42c78faf) covers 2010-06-06 18:00 .. 2026-09-16 and contains every RTH bar of
the RTH master with the same close on 99.98% of bars.

Why this one: NOISE has never used the overnight session - its band is anchored on the RTH open and the prior RTH close
only. Mechanism: the overnight high and low are the most-watched intraday levels; a band break that is still inside the
overnight range runs into the sellers (buyers) who capped it overnight, while a break beyond the overnight extreme
triggers the resting stops and breakout orders parked there and gets fuel. Why it may fail: the band may usually sit
beyond the overnight extreme already (the tag redundant with the break, the round-64 trap), or the extreme is a magnet
that is reached and then fades, or the best trend days start inside the overnight range.

Rule, fixed now: OVERNIGHT = every ETH bar from the previous RTH session's close (16:00) to this session's 09:30. A long
is CLEARED when the signal bar's close is above the overnight high; a short when below the overnight low. Uncleared
signals are skipped, re-simulated inside the strategy (the flat slot can take a later cleared break). The overnight
range is complete before 09:30, so nothing after the signal bar is read. Neighbours reported, never picked from: the
level moved out by 10% of the overnight range (stricter) and in by 10% (looser). Descriptive only: the share of breaks
already cleared.

Bases, data, stretches and bar exactly as rounds 63/65/66: #304 crown primary, #243 replication, NQ 5-minute RTH
no-adjust master to 2026-09-16, cost 0.533, WF 2016-06-30 .. 2025-07-16, LB .. 2026-07-16. OWNER YARDSTICK on both
bases: ROC %/yr at a $30k drawdown (valued daily) AND Sortino beat the plain twin in BOTH stretches, 100 WF / 50 LB
trades, LB profitable without its biggest trade, and both neighbours beat the twin's WF ROC at $30k. A survivor gets a
fenced house Auto-Validate (pinned date_from/date_to, 900 trials) then the RUNBOARD watch list; a failure is recorded
dead.
