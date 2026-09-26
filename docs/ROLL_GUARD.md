# The contract-roll guard on the data refresh (2026-09-26)

## What problem this solves

Our NQ and ES non-adjusted masters stop being Databento on 2026-06-05 and are Yahoo
`NQ=F` / `ES=F` from there on. Yahoo serves a continuous front-month series and changes
which contract it is quoting whenever it likes, including in the middle of a session,
without marking it. Twice in 2026 the change landed **inside a single bar**, so one bar
opened on the expiring contract and closed on the next one:

| When (ET) | Masters | Bar | Contract carry |
|---|---|---|---|
| 2026-06-15 03:30 | NQ 1m and 5m, 24-hour | open 30,252.00 → close 30,563.00 | about +293 |
| 2026-06-15 05:30 | ES 1m and 5m, 24-hour | open 7,521.50 → close 7,584.50 | about +64 |
| 2026-09-14 11:30 | every Yahoo-fed NQ/ES 1m and 5m master, RTH and 24-hour | NQ 29,077.00 → 29,454.50 (5m), ES 7,612.00 → 7,691.50 | about +295 / +68 |

A bar like that is not a price. Anything holding through it books the carry as profit,
its range trips stops and trailing exits that never happened, and every indicator with a
lookback over it reads a move that did not occur. `ROLL_AUDIT.md` section 2.7 has the
full event list and section 4 the measured damage.

The next quarterly roll is **December 2026, expiry Friday 2026-12-18**. Without a guard
the same thing happens again, most likely on the Monday of expiry week.

## What the guard does

`augur_engine/roll_guard.py` is a **refusal, not a repair**. When a refresh is about to
append a bar that looks like an in-bar contract switch, the append stops at the last
clean bar, prints why, and writes a small JSON record under `C:\EdgeLog\roll_alerts\`.
Nothing is fabricated, nothing already stored is touched, and no bar is lost - the bars
after the suspect one are seen again on the next refresh, once a human has either
confirmed the roll or cleared the false alarm.

A bar is refused only when all three of these hold:

1. **Calendar.** Its ET date falls in the ten days before a quarterly expiry (the third
   Friday of March, June, September or December). All 128 switches in the raw Databento
   history came 4-8 days before expiry, and so did both 2026 splices. Outside that
   window the guard is silent, so ordinary news bars are never touched.
2. **Size against the carry.** The body is at least half the expected carry between
   contracts, which has run about 0.9% of price per quarter (NQ +0.97% in June and
   +1.02% in September; ES +0.83% and +0.89%). Scaling to price rather than a fixed
   number of points keeps one rule working from 2010 prices to today's.
3. **Size against its own noise.** The body is at least ten standard deviations of the
   preceding bars' bodies, so the same rule works on a 1-minute bar and a 30-minute bar
   without tuning per timeframe.

...and the bar has to move **up**, the way a roll moves price while financing costs more
than the index pays in dividends. All four splices stepped up. This halves the false
alarms, because what otherwise trips the test is Federal Reserve 14:00 ET decisions and
08:30 ET inflation prints inside expiry week, which go either way.

## Where it runs

- `tools/refresh_noadj_yahoo.py` - the tool that tops up the 1m and 5m NOADJ masters.
- `optimizer.py` `auto_refresh_masters`, between the merge and the save. This is the path
  the headless runner executes through `api/augur_refresh.py` about every half hour while
  `--watch` is running, so it is the one that matters most.
- `tools/refresh_resampled_masters.py`, which rebuilds the 15m/30m/60m/2m masters from
  those parents. It asks the PARENT, for the reason in the next section.

All three call the same functions, so they cannot drift. `tests/test_roll_guard.py` pins
the wiring as well as the arithmetic: a guard nothing calls is not a guard.

## It has to be asked at 1m or 5m, not on a coarse bar

The "is this an extreme move for this bar size" test loses its bite as bars get coarser. A
30-minute bar's ordinary body is already large enough that a carry-sized jump no longer
stands ten standard deviations clear of it. Measured on the real 2026-09-14 buckets: ES 30m,
ES 60m and NQ 2m are caught, and **NQ 30m and NQ 60m sail through** - their preceding
bodies have a spread wide enough to put the ten-sigma floor above 400 points, and the
splice bucket's body is 377.50.

That is fine where the guard actually sits, because both data-refresh paths write 1m and 5m
masters, and at those sizes a carry-sized jump is unmistakable. For the resampled masters
the rule is: run the guard on the parent's 1m or 5m bars, then refuse any bucket whose
window covers a flagged parent bar, and everything after it. That is the same "propagate a
mixed bar to coarser bars" rule `ROLL_AUDIT.md` section 6.2 describes. Do not test a coarse
bar's own body and conclude it is clean.

## Proof it works, and what it costs

`python tools/roll_guard_scan.py` runs the guard over each master's whole history and
prints every bar it would refuse. Output committed as `docs/ROLL_GUARD_SCAN.md`.

| Master | Bars | Would be refused | Known splices caught |
|---|---|---|---|
| NQ 1m RTH | 1,603,331 | 11 | yes |
| ES 1m RTH | 1,598,881 | 9 | yes |
| NQ 5m RTH | 321,802 | 11 | yes |
| ES 5m RTH | 321,805 | 9 | yes |
| NQ 5m 24h | 1,144,059 | 29 | yes |
| ES 5m 24h | 1,145,886 | 23 | yes |

Every known splice is caught on every master that contains it. The false alarms are
between nine and twenty-nine bars across sixteen years - under two a year on the busiest
master - and every one of them is an FOMC or inflation-print bar inside expiry week.
Since they fall on the same days across masters, the real running cost is roughly one or
two paused appends a year.

**The ten-sigma threshold cannot be raised.** On the real data the 2026-06-15 03:30 NQ
splice clears its own floor by only 1.08x, because the two volatile sessions before it
inflate the spread. Raising the multiple would miss that splice.

## What this deliberately does not do

- **It does not tell a roll from a big news bar.** That is the cheap side of the trade: a
  false alarm costs a paused append and one look, a missed splice quietly poisons every
  backtest that reads the tail. Each alert reports the bar's volume against its recent
  median, which settles most cases at a glance.
- **It does not use "the other root did not move."** The two roots often roll in the same
  window, and in June 2026 they rolled two hours apart, so that signal is not dependable.
  The other root's body is recorded as evidence, never gated on.
- **It does not repair the two splices already in the masters.** The one consequence worth
  naming: because the 15m/30m/60m/2m masters end 2026-06-30 and the September splice is
  after that, bringing them current stops at 2026-09-14 rather than 2026-09-25. They go from
  63 weekdays stale to a little over a week, and the rest appends by itself once the parent
  is repaired. ES 30m RTH is read by the live paper book, so adding a known-bad bar to it
  was not an acceptable price for eight more days of tail.
   Those bars are stored and
  the guard ignores bars at or before the master's last stored timestamp - otherwise every
  refresh would stall forever. Repairing them is `ROLL_AUDIT.md` section 6.3, which needs
  a roll table and, for an exact rather than estimated offset, a Databento re-pull.
- **It does not back-adjust anything.** No strategy changes source, and no master's
  existing rows are rewritten.
- **It does not cover the paper stack's own capture loader.** `api/paper.py` appends
  NinjaTrader capture bars to its shadow series and can take a tail on a different
  contract; `ROLL_AUDIT.md` section 6.6 proposes a contract label from the capture add-on
  for that, which is separate work in the paper lane.

## Open owner calls this does not settle

1. **Repair the two stored splices** (June 2026 and September 2026) - and whether to
   re-pull Databento for 2026-06..09 to get an exact offset instead of the estimated
   +293 / +64 / +295 / +68. `ROLL_AUDIT.md` 6.3 and 7.2.
2. **Build back-adjusted masters and re-validate the crowns on them.** `ROLL_AUDIT.md`
   6.7 lists the runs; that is heavy runner work, outside market hours.
3. **What to do when the guard fires in December.** The append pauses and waits for a
   person. If nobody looks, the master stops updating, which stops the paper and live
   stacks getting fresh bars. The safer default is deliberate but it is a decision: the
   alternative is to let the splice through and flag it, which is what we have now.
