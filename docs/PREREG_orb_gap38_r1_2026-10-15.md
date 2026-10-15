# PREREG: ORB GAP38 r1 - does ORB do better when its breakout goes WITH the opening gap? (ORB lane, 2026-10-15)

**Why.** Reading shelf No. 38 ("Price gap anomaly in the US stock market: The whole story"), taken by the ORB lane on MANAGER #93's restock.
The shelf's test: bucket days by the RTH opening gap, compare ORB trades whose breakout agrees with the gap against those that fight it, and
see whether skipping or shrinking the against-gap trades lifts ORB at $30k.

**Draft read (pre-walk-forward rows only, 2010-06-07 .. 2016-06-30; script `C:\EdgeLog\_anatomy_cache\orb_gap38\orb_gap38_draft.py`).**
- With the gap +$50 a trade (n 355); against it -$35 (n 474); difference $85 (95% +22 .. +148) = 0.18 of a trade's sd.
- ORB trades against the gap 57% of the time.
- Power: the walk-forward has 1,281 trades; the minimum detectable difference at 80% power is 0.16 of a trade's sd, so the prior just clears it.
- Map warning: 13 of the pre-walk-forward top-26 money days traded AGAINST the gap, and the prior comes from ORB's flat era
  (net $188 a year). Skipping against-gap trades may cut ORB's tail, hence a half-size arm.

**Trades.** Walk-forward only: trades ENTERED 2016-07-01 .. 2025-06-27. The lockbox is not read.
- The ORB crown #314 settings = `api.cloud_signal.CROWN_LEGS["ORB_R6"]` (strategy file and params as they are), on the NQ 5m RTH back-adjusted
  master `ADJ_NQ_5m_RTH.csv` (source db_adj_rth, the book's ORB source), cost 0.533 points a round trip, $20 a point, one contract.
- The engine runs from 2010-05-01 so every indicator is warm; only walk-forward entries are scored.

**The gap (known at the open).** gap = (the day's first RTH open - the prior session's last RTH close) / the mean (high - low) of the prior 10
sessions. A trade AGREES when side x gap > 0 and is AGAINST when side x gap < 0; a zero gap is neutral (kept at full size in every arm).

**Verdict (set now), on the walk-forward:** each trade's return in % of its entry price (points / entry price; era-neutral), mean(AGREE) minus
mean(AGAINST), Welch 95% interval.
- **"WITH THE GAP PAYS"**: the interval is above 0.
- **"AGAINST THE GAP PAYS"**: the interval is below 0.
- **"NO GAP EFFECT"**: otherwise.

**Arms, reported with the four numbers** (ROC @ $30k, DD5 at $30k, DD % from peak at $30k from $100k, Sortino; daily $ by exit day, every RTH
session in the window a row):
- A: #314 as is.
- B: against-gap trades skipped.
- C: against-gap trades at half size (research sizing; at 1 contract this is not tradeable, at 2+ it is).

B - A and C - A ROC @ $30k with a 90% block-bootstrap interval (20-session blocks, 2,000 draws, seed 7, the same draws for every arm). An arm
LIFTS only if its 90% interval is above 0 AND the verdict is "WITH THE GAP PAYS". The one-episode flag (worst drawdown > 1.3x the 5th worst) is
printed per arm.

**Also printed, not part of the verdict:** the same split for |gap| >= 0.25 of the range; the share of the walk-forward's top-26 money days whose
trade went against the gap; trades a year per arm.

Report-only: no rule, size or live change, #314 untouched, the book untouched. Harness: `tools/orb_gap38_r1.py`, which checks this note's LF
sha256 at start and stops on a mismatch.
