# ENGU-Q round 63 - PRE-REGISTRATION: entry-bar order flow as a survivor predictor

Written and committed before any order-flow number is read. Owner ask 2026-09-30 through the
MANAGER chat (inbox item #19): keep assessing ENGU-Q improvements as a queue, look for BETTER
SURVIVORS, never cut exposure to winners, and send short-history finds straight to a forward
shadow rather than adoption.

## The idea, and why it belongs to this family

The settled family finding (ENGUQ.md 2026-09-28): every dollar ENGU-Q has made comes from trades
that survive their first day. The 1,078 intraday deaths cost $493,422, almost exactly the whole
net, while the 270 trades held past three days made $634,270. Three separate mechanisms that
reduce exposure to winners have now failed their bars - the hold cap, the partial exit and the
cash-session gate - so the only direction left is to find **better survivors at entry**.

The NinjaTrader 10-second capture (`C:\EdgeLog\ohlc\NQ_10s.csv`) carries `delta`, `buy_vol`,
`sell_vol` and `tick_count` per bar. Nothing in this family has ever used them. The mechanism
being proposed is plain: a breakout printed into genuine buying pressure should hold, and one
printed into selling pressure should fail the same day. That is exactly the survivor question.

## The sample problem, stated BEFORE any hypothesis is read

The capture carries real order flow on **80 trading days, 2026-06-26 to 2026-09-30**. Over that
window the crown leg takes **33 trades: 8 survived day one, 25 died the same day** (its
cash-session shadow arm takes 22: 7 and 15). Measured before writing this bar, deliberately.

**Eight survivors cannot support a rule.** Any threshold fitted on 33 points is curve-fitting, and
no two-group comparison at 8-vs-25 has the power to detect anything short of a separation far
larger than the 25-point effect the cash-session gate showed. So this round CANNOT produce an
adoption, a validate or a candidate, and nothing below may be quoted as evidence for one.

## What this round therefore does

1. **A descriptive baseline, published with its uncertainty and labelled as not evidence.** The
   signal-bar order-flow imbalance of the 8 survivors against the 25 deaths, with a confidence
   interval wide enough to make the point. It exists to be looked back on, not acted on.
2. **Instrumentation, which is the real deliverable.** A tool that records the entry-bar
   order-flow reading for every ENGU-Q shadow trade from here on, so the sample accumulates
   instead of being re-argued from 33 points every month.

## The forward bar - fixed now, read once

- **PREDICTOR, fixed here and not tuned:** the signal bar's order-flow imbalance, defined as the
  minute's `delta` divided by its `volume`, aggregated from the 10-second rows stamped inside that
  minute. One number. No threshold is chosen in this round, on purpose.
- **CHECKPOINT:** read ONCE, when the accumulated forward sample reaches **60 survivors AND 60
  same-day deaths**. Not before, and not continuously - reading as it accrues and stopping on a
  good look is peeking.
- **THE BAR:** the survivors' median imbalance must exceed the deaths' by **at least 0.10** (ten
  percentage points of the bar's own volume) with a rank-sum p below 0.05.
- **IF IT CLEARS:** the threshold implied by that sample defines an entry filter, and that filter
  goes to a **pre-registered forward shadow** - never a backtest adoption, because the threshold
  would have been fitted on the data that justified it.
- **IF IT FAILS:** entry-bar order flow is written up dead for this family and not re-cut.

## Constraints this round inherits, stated so they are not quietly broken

- **Entry only.** Any rule that comes out of this may decline a signal. It may never cap a hold,
  scale out, tighten a trail or otherwise reduce exposure to a trade that is winning.
- **Signal bar, never the fill bar.** About 45% of this file's fills land 2-10 bars after the
  signal; a condition read at the fill bar leaks.
- **The capture is a live tail, not a certified master.** It starts 2026-06-26, it is
  NinjaTrader's own stamping, and it has no roll correction. Nothing from it may be mixed into a
  figure quoted against the 2010-2026 history.

## How this could fool us

- **Survivorship in the predictor itself.** A bar with large positive delta is usually a bar with
  large volume and a big range, which is also when ENGU-Q's stop is widest. Any separation found
  may be the volatility factor round 57 already identified, not order flow. At the checkpoint the
  comparison must therefore be repeated with the bar's range held fixed.
- **One regime.** Everything in the capture and everything the forward sample will add comes from
  a single stretch of market. A result that holds is consistent with the mechanism; it does not
  establish it.
- **Thin nights.** Order flow outside the cash session is a handful of contracts, so the imbalance
  ratio is noisy exactly where the cash-session arm already says the trades are worthless.
