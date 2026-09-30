# PRE-REGISTRATION — NOISE round 66: ES confirmation of the NQ break (2026-09-30)

Queue item after the round-64 audit (owner ask via MANAGER, inbox #16: keep testing NOISE, auto-validate anything
promising). Written and committed before any confirmed/unconfirmed trade split was computed. The only thing looked at
first was data availability: the ES 5-minute RTH no-adjust master has a bar at every NQ bar's timestamp, 2010-06-07 ..
2026-09-16, 4,180 common sessions.

Why this one: rounds 63-65 closed entry timing, in-trade sizing and exits; new alpha for this family needs new
information. ES has never been used inside NOISE (ES-native NOISE died on 2026-08-22; the 2.5 NQ-vs-ES spread was a
stand-alone mechanism). Mechanism: intraday momentum is a market-wide effect (hedging and late-informed flow); an NQ
break that ES does not share is more likely a few mega-cap names moving on their own, which reverts more often. Why it
may fail: NQ and ES move together most of the time, so nearly every break may be "confirmed" (the round-64 trap: a tag
redundant with the break itself), or the unconfirmed breaks are tech-led trend days - the best NOISE trades.

Rule, fixed now: at the close of NQ's signal bar, compute ES's own noise band on ES's own bars with the crown's formula
and knobs (lookback, band_mult_long, band_mult_short; reference max/min of ES's session open and prior close). A long is
CONFIRMED when ES's close on the same bar is above ES's upper band; a short when below ES's lower band. Unconfirmed
signals are skipped, re-simulated inside the strategy (the flat slot can take a later confirmed break). Only bars that
have closed are read (same bar as NQ's signal, fill at NQ's next open as always). Neighbours reported, never picked
from: ES band at 0.5x and 1.5x the crown's multipliers. Descriptive only: the share of breaks confirmed and ES's move
since its open having the trade's sign.

Bases, data, stretches and bar exactly as rounds 63/65: #304 crown primary, #243 replication, NQ 5-minute no-adjust
master to 2026-09-16, cost 0.533, WF 2016-06-30 .. 2025-07-16, LB .. 2026-07-16. OWNER YARDSTICK on both bases: ROC
%/yr at a $30k drawdown (valued daily) AND Sortino beat the plain twin in BOTH stretches, 100 WF / 50 LB trades, LB
profitable without its biggest trade, and both neighbours beat the twin's WF ROC at $30k. A survivor gets a fenced
house Auto-Validate (pinned date_from/date_to, 900 trials) then the RUNBOARD watch list; a failure is recorded dead.
