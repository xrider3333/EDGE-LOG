# PRE-REGISTRATION — NOISE round 65: a two-hour time stop (2026-09-30)

Queue item after round 64 (owner ask via MANAGER, inbox #14: keep assessing NOISE improvements). Written and committed
before any time-stop trade was computed. Listed in round 63 as "cheap, low prior"; run now because it is the last exit
rule this family has never tried (trailing stops and the breakeven closed in round 52; exit-mode band/boundary searched).

Mechanism: a noise-band break that has neither reached its VWAP exit nor its stop two hours later has stalled; if
intraday momentum is realised early, those stale trades carry cost and drawdown for little expected gain, and closing
them frees the one position slot for the next break. Why it may fail: NOISE's money is the all-day trend trade, which is
exactly the kind that is still open after two hours.

Rule, fixed now: if a position is still open at the close of the 24th 5-minute bar after its entry bar, it exits at the
next bar's open (a normal queued exit). Everything else is #304's crown. Re-simulated inside the strategy (the freed
slot can take a new break), not post-processed. Neighbours reported for the plateau, never picked from: 12 and 36 bars.

Bases, data, stretches and bar exactly as round 63 (docs/PREREG_noise_r63_2026-09-28.md): #304 crown primary, #243
replication, NQ 5-minute no-adjust master to 2026-09-16, cost 0.533, WF 2016-06-30 .. 2025-07-16, LB .. 2026-07-16.
OWNER YARDSTICK on both bases: ROC %/yr at a $30k drawdown (daily) AND Sortino beat the plain twin in BOTH stretches,
100 WF / 50 LB trades, LB profitable without its biggest trade, and the 12- and 36-bar neighbours move the same way in
the walk-forward. A survivor gets a fenced Auto-Validate; a failure is recorded dead.
