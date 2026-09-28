# PRE-REGISTRATION — NOISE round 63: two new mechanisms for more alpha (2026-09-28)

Owner ask via MANAGER (inbox #13): brainstorm NOISE variations for more alpha, pre-register the top 1-2 on the owner's
yardstick, run the cheap triage. Written and committed BEFORE any trade of either variant was computed.

## Dead-hunt check (what these are NOT)
Not a geometry re-optimisation (lookback, bands, stop, skip, day-type, confirm bars: searched to death, rounds 1-57);
not a filter from the 2026-08-18 context scan (RSI, MACD, efficiency ratio, ATR / range percentile, gap, streaks, VIX -
nothing survived); not exit trailing / breakeven (round 52); not a re-entry cooldown (2026-09-22); not a calendar
(FOMC / BLS / earnings / witching / month-turn); not a learned model. Grep of NOISE.md and RESEARCH_LEDGER.md for
pyramid / scale-in / half-hour checkpoint: zero hits.

## Idea A — PYRAMID ON CONFIRMATION (a new sizing-inside-the-trade entry rule, no model)
Mechanism: NOISE's money is a fat right tail - trend days that run from the break to the close. A trade that has
already moved one risk unit in its favour is disproportionately one of those days (intraday momentum persists), so a
second contract added there spends exposure where the edge is, not uniformly.
Rule, fixed now: when price reaches entry + 1.0 x R in the trade's favour (R = entry to the trade's own protective
stop), add ONE more contract with a stop order at that level (filled at the level, or at the bar's open if it gapped
through). The add rides the original trade's exit exactly. At most one add. Costs 0.533 points on the add too.
Conservative intrabar rule: if the trigger and the stop both fall inside the exit bar, the add is counted as filled
and stopped. On a queued (next-open) exit the add can only trigger up to the bar before the exit.
Neighbours reported for the plateau, never picked from: 0.5 R and 1.5 R.

## Idea B — HALF-HOUR DECISION CHECKPOINTS (the published design of the mechanism)
Mechanism: the source paper for this mechanism checks the noise band only at HH:00 and HH:30; NOISE checks every
5-minute close, and a quarter of its trades are quick same-direction re-entries earning 39% of a normal trade. Sampling
the entry decision every 30 minutes should drop the whipsaw breaks while keeping the band's 5-minute resolution and
every 5-minute exit check.
Rule, fixed now: a new entry may only be signalled on a bar whose close is on the half hour (10:00, 10:30 .. 15:30);
everything else unchanged. Neighbour reported, never picked from: quarter-hour checkpoints.

## Bases, data, stretches
PRIMARY: NOISE #304's crown configuration (the family's raw twin). REPLICATION: retired crown #243. NQ 5-minute RTH,
no-adjust Databento master (NOISE is flat by the close, so rolls move it ~1%), cost 0.533, 2010-06-07 .. 2026-09-16
(last Databento bar). Stretches = the round-60 validates': WF 2016-06-30 .. 2025-07-16, LB 2025-07-16 .. 2026-07-16;
fresh tail after it reported only.

## The bar — OWNER YARDSTICK (2026-09-28), on BOTH bases, for each idea separately
1. ROC %/yr at a $30k worst drawdown (= 30 x MAR, drawdown valued DAILY on the $100k account) beats the raw twin in
   BOTH WF and LB;
2. Sortino beats the raw twin in BOTH WF and LB;
3. at least 100 WF trades and 50 LB trades;
4. the LB stays profitable without its single biggest trade;
5. PLATEAU: the neighbour setting(s) move the same way in WF (a lone winning cell is a spike, not a mechanism).
A triage survivor gets a fenced Auto-Validate (900 trials, pinned window) before anyone calls it adoptable; a failure
is recorded as dead in NOISE.md and RESEARCH_LEDGER.md. Nothing live moves in this round.

## Other ideas listed, not run now
Time stop (exit after 2 hours; low prior - cuts the fat right tail); crown transfer to ZN / 6E / CL / GC as book legs
(needs the owner's data key); volatility-targeted fixed sizing (Custom ML's lane - routed); daily-trend side alignment
and daily squeeze regime (mostly covered by the 08-18 context scan's MACD / efficiency / range-percentile features);
NOISE on ES as a book leg (ES-native NOISE is dead, 2026-08-22).
