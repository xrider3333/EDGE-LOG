# ENGU-Q round 64 - PRE-REGISTRATION: does entry-bar order flow carry ANY survivor information?

Committed before a single number is read. Follows round 63 (`ENGUQ_R63_OFLOW_PREREG.md`, ENGUQ.md
2026-09-30), which could not test the idea at all: the 10-second capture yields only 3 day-one
survivors on the crown leg, and its 60-and-60 checkpoint is about twenty months away.

## Why the obvious fix does not work, measured before proposing this round

The natural rescue is to count SIGNALS instead of filled trades - every bar that clears the entry
filters, whether or not the resting limit fills it. Measured over the full 2010-2026 history on
the roll-corrected tape: **2,766 signals against 2,053 filled trades, a 74% fill rate**. That is
0.56 signals a trading day against 0.41 trades, so eighty days of capture would give about 44
signals instead of 33 trades. **A 1.3x gain is not a rescue**, so the signal-unit round that
round 63 proposed as "round 64" is abandoned here rather than run.

## What this round asks instead

Drop the requirement that the bar be an ENGU-Q signal, and ask the question that has to be true
underneath it: **on this tape, does a bar's order-flow imbalance predict whether its move persists
to the next day at all?** If the answer is no on thousands of bars, it is certainly no on
forty-four, and the idea is finished without waiting twenty months. If the answer is yes, that
does not adopt anything - it justifies letting the round-63 ledger accrue toward its checkpoint.

**Population.** Every 1-minute bar inside the capture window (2026-06-26 to 2026-09-30) that is an
upward breakout in the crown's cheapest sense: close above open, and close above the previous
bar's high. No trendline, regime, moving-average, volume or efficiency filter - those are what
make signals scarce, and they are not what is being tested. Bars whose capture minute carries no
order flow are excluded and counted.

**Predictor.** The bar's own order-flow imbalance, `delta / volume`, from the 10-second rows
stamped inside that minute. Fixed here, not tuned.

**Outcome.** Day-one persistence: the close 1,440 minutes later is above this bar's close. A plain
forward-path question with no strategy machinery, no stop and no trail, so nothing about ENGU-Q's
exits can contaminate it.

## The bar - written before the numbers, read once

1. **PRIMARY.** Sort the population into quintiles by imbalance. The top quintile's persistence
   rate must exceed the bottom quintile's by **at least 10 percentage points**, with a chi-square
   p below **0.01**. The sample is in the thousands, so a strict p costs nothing and a loose one
   would be meaningless.
2. **CONFOUND CLAUSE, and it is not optional.** Round 57 established that the only era-stable
   separators of ENGU-Q winners are volatility and planned stop size. A bar with large positive
   delta is usually a bar with large volume and a wide range. So the quintile comparison must be
   repeated **within terciles of the bar's own range**, and the 10-point gap must survive in the
   majority of them. If the effect lives only in the widest-range bars, it is the volatility
   factor already known, not order flow, and clause 1 does not count.
3. **FAILURE.** If either clause fails, entry-bar order flow carries no survivor information on
   this tape, the round-63 ledger is left accruing but expectations are written down, and the idea
   is recorded as tested rather than merely untested.
4. **WHAT A PASS IS NOT.** A pass does not create a candidate, a validate or a filter. The
   population is not ENGU-Q's, the window is one regime, and the capture is holed. A pass means
   only that the round-63 checkpoint is worth waiting for.

## How this could fool us - declared in advance

- **The capture is holed**, worse than expected: the median day holds 5,883 ten-second bars
  against the ~8,280 a full session gives, 25 of 80 days hold under 2,000, and 2026-08-27 holds
  42. Excluded bars will be counted and reported, and if exclusion correlates with time of day the
  surviving sample is not a random subset of the tape.
- **Overlapping outcomes.** Consecutive breakout bars share almost all of their forward path, so
  the effective sample is far smaller than the bar count and the p-value is optimistic. That is
  why the primary clause carries an effect-size floor of 10 points and not just a p-value.
- **One regime, three months.** Whatever this finds describes summer and early autumn 2026.
- **Night bars.** Outside the cash session the imbalance ratio is computed on a handful of
  contracts and is mostly noise; the range-tercile split partly absorbs this, and the cash-session
  breakdown will be reported beside the headline.
