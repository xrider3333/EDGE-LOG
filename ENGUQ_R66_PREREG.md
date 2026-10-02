# ENGU-Q round 66 - PRE-REGISTRATION: initial risk width as the long-hold selector

Committed before any hold length, survival rate or profit number is read. This round answers the
condition MANAGER set after round 65: **a rule must say IN ADVANCE why it would keep the 35-day
trade and drop ordinary survivors**, rather than merely lift the day-one survival rate.

## Why this rule keeps the 35-day trade, argued from the exit rule rather than from data

This is arithmetic about how ENGU-Q exits, not an empirical claim, so it can be stated before any
measurement:

- The trade is closed by a trailing stop that rides **`trail_frac` x `risk`** below the running
  high, where `risk` is the entry close minus the swing low over the previous `tl_len` bars. That
  distance is fixed **in points, at entry**, and never widens.
- A trade therefore survives exactly as long as the market never retraces `trail_frac x risk`
  from its best level. Retracements scale with volatility, so the number of days a trade can
  survive is an increasing function of **`risk / ATR` at the signal bar**.
- The 35-day hold that is ENGU-Q's entire sealed year did not survive 35 days by luck of the
  entry; it survived because its trail was wide enough in volatility terms to absorb five weeks
  of retracement. **Ordinary survivors - the ones round 65 showed are too common to be worth
  selecting - are trades with ordinary trails that get taken out in days.**
- `risk` and `ATR` are both known at the signal bar, so this is a legitimate entry filter and
  nothing about the exits, the hold or the position size changes.

**The inverse experiment has already been run and it supports this.** `ENGUQ_1M_RC_1_0` capped
initial risk at k x ATR and FAILED hard - net $453,532 collapsing to -$75,905 at the tightest cap
- and that round was written up with the conclusion "ENGU-Q's profit LIVES in the wide stop". If
capping risk destroys the edge, selecting for wide risk is the natural experiment nobody ran.

## What changes

One new knob on a research sibling of the crown's file, `min_risk_atr`: a signal is taken only
when `(signal close - swing low over tl_len bars) / ATR >= min_risk_atr`. Entry filter only;
exits, stops, trailing, the limit scan and the hold are the crown's, untouched.

**Thresholds are distributional landmarks, fixed before any outcome is read.** Measured as design
groundwork over the crown's 1,999 recoverable entries, risk at entry runs from 3.2 to 64.6 ATR
with a median of **8.83** and quartiles of 7.12 and 11.53 - the lookback is 170 bars, so these are
much wider than a one-bar reading would suggest. **PRIMARY = 8.83 ATR, the population median**,
chosen because it splits the population in half and is tied to no outcome. The quartile (7.12),
the 75th (11.53) and the 90th (15.02) are reported as a plateau and never selected from.

## The bar - all six clauses, against the RAW TWIN (this file with the filter off)

One continuous run per cell on ADJ_NQ_1m_ETH, 2010-06-07..2026-06-30, sealed split 2025-06-30,
cost 0.783 x $20, drawdown valued daily.

1. **ROC per year at a $30,000 worst drawdown beats the raw twin in BOTH stretches.**
2. **Sortino beats the raw twin in BOTH stretches.**
3. At least **100 walk-forward trades** and **50 sealed trades**.
4. **The sealed year stays profitable without its single biggest trade** (the live cell fails this
   at -$16,283).
5. **The long-hold claim must be true, and this clause is new this round:** among the trades the
   filter KEEPS, the share held longer than three days must be at least **1.5x** the share among
   the trades it removes, in each of the four eras. This is the clause that tests the stated
   mechanism rather than a side effect of it; day-one survival is explicitly NOT the test, because
   round 65 showed it is too common to matter.
6. **Harness gate:** with the filter off the file returns a trade list identical to
   `ENGUQ_1M_ETH_R2_1_0.py`, and a test asserts every threshold above lands on the declared search
   lattice - the defect that would have made an Auto-Validate of round 62 meaningless.

**If all six clear, this goes to the house Auto-Validate** (pinned window, the 900-trial budget,
ranges fenced, auto-expand off) and then onto the RUNBOARD watch list, and only then is it
compared against BOOK #463's reference of WF 93.8 / LB 155.5. Any failure means dead, no validate.
The bar does not move afterwards.

## How this could fool us

- **It raises the average loss by construction.** A wide stop loses more when it is hit, so this
  must pay for itself through the holds it keeps. Clause 1 is where that shows up.
- **It may be a volatility filter wearing a different hat.** A high `risk / ATR` means the swing
  low is far away relative to current volatility, which happens when volatility is compressed.
  Round 57 found volatility is one of only two era-stable separators of ENGU-Q winners, so clause
  5's era split is the guard: an effect living in one era is that factor, not this mechanism.
- **The refill effect killed four previous entry filters** - a declined signal frees the slot and
  the walk takes a later, worse signal of the same move, and those refills win 14-23%. Judged in
  the engine, never on a filtered trade list.
- **Partly circular by construction**, and said plainly: wide risk means a wide trail means longer
  holds almost definitionally. Clause 5 confirms the mechanism works; clauses 1 to 4 are what
  decide whether it is worth anything, and round 65 is the warning that a real, era-stable
  mechanism can still be worth nothing.
