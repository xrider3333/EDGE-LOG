# ENGU-Q ANATOMY r1 - PRE-REGISTRATION: what the crown actually is

Ordered by MANAGER's 10-05 assessment (item a). **REPORT ONLY: no filter, no knob, no candidate,
no pass or fail, and nothing here can be adopted.** Committed before any number below is read.

The assessment's verdict is the thing being tested: that ENGU-Q #335 is best read as **a long-only
NQ trend position sampled at one-minute entries**, which if true means BOOK #463 carries NQ trend
beta through this leg and seats should be priced against that rather than against a separate edge.

## Stretch, cell and conventions - fixed here

- Crown cell: `ENGUQ_1M_ETH_R2_1_0.py` at its `DEFAULT_PARAMS`, cost **0.783** points a round trip
  (the house cost, owner decision 10-05), multiplier $20, on **ADJ_NQ_1m_ETH** (source
  `db_adj_eth`, the registered roll-corrected master), 2010-06-07..2026-06-30.
- **WALK-FORWARD ONLY: 2016-10-01..2025-06-30. The sealed year is NOT read in this round.**
- Drawdown and the leg's daily series are **valued daily** (open positions marked at each day's
  close), the house convention for this family.
- Every ROC @ $30k figure, if any is printed, carries **DD5** beside it and the one-episode flag
  (rule 10-07, `augur_engine/drawdowns.dd5`).
- **Survivor = held 24 hours or more by elapsed time**, the definition pinned in
  `ENGUQ_R62_FORWARD_PREREG.md`. A trade still open at the stretch end is written `unresolved` and
  excluded from survivor comparisons, never counted as a death.

## (i) The survivors' signal-day state, and the hold path by year

Reported, not selected from. Both factors are the ones round 57 found era-stable, so this asks
what the survivors looked like at entry - it does **not** ask whether that is tradable, and under
the owner's 10-02 rule it cannot become an entry filter.

1. **Planned stop size**: the trade's initial risk in points (signal close minus the swing low over
   `tl_len` bars) and the same divided by the signal-bar ATR.
2. **Daily stretch above the 20-day average**: the signal day's PRIOR daily close minus the 20-day
   simple moving average of prior daily closes, as a percent of that average. Prior close only, so
   nothing from the signal day itself enters.

Printed as the median and quartiles for survivors against non-survivors, **split by era**
(2016-18, 2019-21, 2022-25), because round 57's lesson is that a separator living in one era is
that era's factor.

3. **Hold path by calendar year**: count, median hold hours, the 75th and 90th percentiles, and the
   share held past 24 hours and past 3 days.

## (ii) The DAILY-TREND TWIN, and the correlation that decides the verdict

A deliberately plain, **untuned** long-only daily NQ system, specified completely here so it cannot
be adjusted after seeing the answer:

- Daily bars built from **ADJ_NQ_5m_RTH** (the roll-corrected RTH master), one bar per session.
- **Entry**: at the close of any day whose close is the highest close of the last 20 sessions, when
  flat. One lot.
- **Exit**: whichever comes first - the close falls more than **2 x ATR(20, daily)** below the
  highest close since entry, or the close is the lowest close of the last 55 sessions.
- Cost 1.0 point a round trip, multiplier $20. No parameter is tuned and none will be changed.

**The comparison**: Pearson correlation of DAILY dollar P&L between the leg (valued daily) and the
twin - over the whole walk-forward, by calendar year, and restricted to the days inside **#463's
drawdown episodes** (the episode list comes from `drawdowns.dd5` run on #463's valued-daily series
over the same stretch, so the episodes are the same ones the yardstick sees). Also the twin's own
net, its daily hit rate, and the share of the leg's net earned on days the twin is long.

**How this answers the assessment**: if the twin tracks the leg closely and especially inside the
drawdown episodes, the book's exposure through this leg is NQ trend beta and nothing more exotic.
If the correlation is weak, the leg is doing something the plain trend system does not, and the
assessment's reading is wrong.

## (iii) Dollar beta to NQ on #463's drawdown days

Ordinary least squares of the leg's daily dollars on NQ's daily dollar change (daily close
difference x $20), restricted to the days inside #463's drawdown episodes, reporting the slope in
contract-equivalents, the intercept in dollars a day, and R-squared. The same regression over all
walk-forward days is printed beside it for contrast.

## How this report could mislead, written before the numbers

- **The leg's daily series is marked from NQ's closes while a position is open, so some correlation
  with any NQ series is definitional, not a finding.** The informative quantities are therefore the
  SIZE of the beta, the R-squared, and whether the correlation survives inside the drawdown
  episodes - not the mere existence of a positive correlation.
- **Sessions differ**: the leg trades the 23-hour ETH session at one-minute resolution, the twin
  the RTH session on daily bars. A day's P&L is aligned by calendar date only.
- **"Survivor" is an outcome label**, so part (i) is description, not a mechanism. Seven
  pre-registered entry filters have already failed in this family and the owner has closed that
  direction; nothing in part (i) reopens it.
- **One twin is one reading.** A weak correlation does not prove the leg is unique, because a
  different plain trend system might track it better. The claim being tested is only the
  assessment's: that THIS kind of exposure explains the leg.
