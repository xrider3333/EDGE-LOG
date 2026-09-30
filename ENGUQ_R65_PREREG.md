# ENGU-Q round 65 - PRE-REGISTRATION: distance below the recent high as a survivor predictor

Committed before any survival or profit number is read. Owner ask 2026-09-30 through the MANAGER
chat: keep the improvement queue running, mechanism first, find better survivors, never cut
exposure to winners, and auto-validate anything that clears its triage.

## The idea came out of a design check, and here is exactly how

Round 65 began as the opposite idea - **overhead supply**. The mechanism was that a breakout into
a nearby prior high stalls and dies the same day, while one with clear air above runs, so requiring
"room to run" should select survivors. That idea is **dead at the design stage, before any outcome
was read**, because the measure never binds: over the 2,053 entries of the crown's own cell, the
distance from the entry close up to the highest high of the previous ETH session has a median of
**12.5 ATR** and a lower quartile of **6.95 ATR**, while the trade only needs about 2.5 ATR to
activate its trail and become a runner. There is essentially no overhead-supply problem to filter.

What that coverage check did show is something else, and it is worth a round: **ENGU-Q typically
enters about twelve ATR BELOW the recent session high.** It is buying a bounce inside a decline,
not a breakout into clear air. So the interesting quantity is the same number read the other way -
**how far below the recent high the entry sits** - and the mechanism reverses with it: an entry
near the prior high is a market that has already repaired its damage and is pressing, while an
entry twelve ATR below is a falling-knife bounce that the prevailing move can simply resume
through. If survivors are the near-the-high entries, this finds better survivors without touching
a single exit.

**Declared honestly:** this hypothesis was formed AFTER seeing the coverage distribution above. It
was not formed after seeing any survival rate, any profit and loss, or any split of outcomes by
that distance - none of which has been computed at the time of writing. The direction is
pre-declared here so it cannot be chosen later to fit.

## What changes

One new knob on a research sibling of the crown's file, `max_room_atr`: a signal is taken only
when `(highest high of the previous 1,380 bars - signal close) / ATR <= max_room_atr`. Entry
filter only. Exits, stops, trailing, the limit scan and the hold are the crown's, untouched - the
family rule that nothing may reduce exposure to a winning trade is not bent here.

- **Lookback fixed on mechanism at 1,380 bars** - one 24-hour ETH session, the most recent
  structure - and not tuned.
- **PRIMARY threshold fixed on mechanism at 8.0 ATR**, about three times the ~2.5 ATR the trade
  must travel to activate its trail. Neighbours 4 / 6 / 12 / 16 are reported as a plateau and
  never selected from.
- OFF is a very large threshold, which must reproduce the parent exactly.

## The bar - all six clauses, judged against the RAW TWIN (this file with the filter off)

One continuous run per cell on ADJ_NQ_1m_ETH, 2010-06-07..2026-06-30, sealed split 2025-06-30,
cost 0.783 x $20 (the paper cell's own cost), drawdown valued daily.

1. **ROC per year at a $30,000 worst drawdown beats the raw twin in BOTH stretches**, walk-forward
   and sealed shown separately.
2. **Sortino beats the raw twin in BOTH stretches.**
3. At least **100 walk-forward trades** and **50 sealed trades**.
4. **The sealed year stays profitable without its single biggest trade** - the clause the live cell
   fails today at -$16,283, and the one that decides whether this does what was asked.
5. **Era stability:** the day-one survival rate of kept entries must beat that of the entries the
   filter removes in all four eras 2010-14, 2015-18, 2019-22, 2023-26.
6. **Harness gate:** with the filter off the file returns a trade list identical to
   `ENGUQ_1M_ETH_R2_1_0.py` at the same parameters.

**If all six clear, this goes to the house Auto-Validate** on the runner - pinned window, the 900
trial budget, ranges fenced with auto-expand off - and then onto the RUNBOARD watch list. If any
clause fails, it is written up dead and no validate is queued. The bar does not move afterwards;
the round-57 stretch cap was left dead on a 0.34-point miss and round 62 on a 0.07 Sortino miss.

## How this could fool us

- **The refill effect is the reason four entry filters have already died here.** A declined signal
  frees the slot and the walk takes a later, worse signal of the same move, and those refills win
  only 14-23%. That is why this is judged in the engine and never on a filtered trade list.
- **This is close to a trend filter, and trend gates are a closed family** - battery U killed the
  regime gate on five cells, and a genuine ten-day regime filter is worse than no filter at all.
  The distinction being claimed is that this measures distance to a PRICE LEVEL, not the slope of
  an average; if it dies the same way, that distinction was not real.
- **ATR is in the denominator**, and round 57 found volatility is one of only two era-stable
  separators of winners here. A filter on "distance in ATRs" can therefore be a volatility filter
  wearing a different hat. Clause 5's era split is the guard; if the effect lives in one era it is
  not the mechanism.
- **One tape, one instrument.** ES is CLOSED-NO by owner decision, so there is no cross-instrument
  check available for this round.
