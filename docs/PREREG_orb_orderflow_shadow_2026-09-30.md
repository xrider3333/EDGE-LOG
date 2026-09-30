# PRE-REGISTRATION — ORB order flow at the breakout, forward shadow (ORB lane, 2026-09-30)

Written and pushed before any P&L on this feature was read. Owner ask via MANAGER inbox #13: keep
assessing ORB improvements; first test = order flow at the opening range from the NinjaTrader 10-second
delta capture, whose history is short, so it goes straight to a forward shadow, never adoption.

## The mechanism

The crown (#314) enters when a 5-minute bar CLOSES beyond the opening range. Some of those breakouts are
real demand — buyers lifting the offer (or sellers hitting the bid) all through the breakout bar — and some
are stop runs that passive orders absorb at the range edge. Delta (aggressive buy volume minus aggressive
sell volume) on the breakout bar separates the two. If the mechanism is real, breakouts whose breakout-bar
delta points WITH the trade should earn more per trade than breakouts whose delta points AGAINST it.

## The data and its limits

`C:\EdgeLog\ohlc\NQ_10s.csv` — NinjaTrader 10-second NQ bars with `delta`, captured live since
2026-06-23 (70 RTH sessions to 2026-09-30). Coverage is patchy: 45 of 70 sessions have near-complete
delta, and some recent sessions are missing most of it (2026-09-22 4% of rows, 2026-09-25 37%). Rows are
stamped at the bar END (the house `_resample` convention).

## The feature (frozen)

For each crown trade, the **signal bar** is the 5-minute bar whose close triggered the entry (entry is
at that close, so the bar is finished at entry — nothing after the fill is read). Its 10-second rows are
those whose `time - 1` falls inside the bar.
- `F1` = the sum of `delta` over those rows. **Valid** only if at least 24 of the bar's 30 rows carry a
  non-zero delta; otherwise the trade is INVALID for this test.
- Secondary, reported only: `F2` = the summed delta of the two opening-range bars (09:30-09:40).

## The arm and its twin (frozen)

- **Twin** = #314 exactly as it trades (size 1).
- **Arm** = the same trades, sized **1.5x when F1 points with the trade, 0.5x when it points against,
  1x when F1 is zero or invalid.** Fixed sizes, nothing searched.
- Paper source: the crown's trades are regenerated with the engine on the house NQ 5m master (the paper
  leg `ORB_R6` is the same rules on the same master plus the fresh tail); `ORB_257` trades are scored the
  same way and reported, not gated.

## The forward test

- **Forward trades** = crown trades entered on or after **2026-10-01** with a VALID F1.
- **Paired sequential stop** (house rule, `docs/PREREG_paired_sequential_stop_2026-09-29.md`):
  d_i = (m_arm_i - c x m_twin_i) x u_i, with u_i the trade's one-contract P&L. Here c is the running mean
  of the arm's sizes over the forward trades read so far (outcome-blind, so the test is of AIM, not of
  size). Looks every 10 valid trades from 20; stop EARLY FAIL at t <= -3.0 (and <= -2.0 without the most
  extreme trade), EARLY PASS - read the final rule at t >= 3.0 (and >= 2.0 without it).
- **Final written rule**, read at 60 valid forward trades or on 2027-06-30, whichever comes first:
  PASS only if all of
  1. the paired mean d > 0 with one-sided t >= 1.645;
  2. the arm's ROC at a $30k worst drawdown over the forward trades beats the twin's;
  3. the arm's daily Sortino >= the twin's;
  4. the arm's gain over the twin stays positive without its single biggest trade.
  A PASS makes it a candidate for an owner decision on a real paper leg; it never adopts anything by itself.
- **The capture period (2026-06-23 to 2026-09-30) is DESCRIPTIVE ONLY.** It is printed once for context
  and can neither pass nor fail this test.

## How it could fool us

- Delta magnitudes in backfilled rows are approximate (Tick Replay); only the SIGN is used.
- Sessions with missing delta drop out; if capture gaps are not random (e.g. busy days), the valid set is
  biased. The scorer reports how many forward trades were invalid.
- The crown trades ~150 times a year but stands down on quiet tape; 60 valid trades may take 6-9 months.

Scorer: `tools/orb_orderflow_shadow.py` (run from the shared checkout; `--describe` prints the capture
period).
