# PRE-REGISTRATION — ORB expiry-week ("roll week") size tilt: FORWARD READ ONLY (2026-10-04)

**Status: REVIEWED - MANAGER GO as written (inbox #32, 2026-10-04 16:46).** Two conditions:
(1) no backtest number on this calendar definition, ever, unless a separate pre-registration says so;
(2) the read is one line in ORB.md, not a round.

MANAGER assignment (standing order, inbox #30 (a)). This is a forward read with the bar written now. **No backtest of
this calendar may be run**: its in-sample figure was seen by accident in the round 65 smoke run and disclosed there.

## What was seen, and why the calendar must be re-defined before anything is read

Round 65's first smoke run printed #314's walk-forward PF in "the 5 sessions after each contract switch" (the switch
dates in `tools/data/rolls_NQ.csv`): **PF 2.14 on 97 trades, $544 a trade, against PF 1.35 otherwise** (#234: PF 1.57
on 116 trades).

**That figure mixes two different calendars,** because the house's switch convention changed in the data:
- 2016-2019 and 2021-12: the switch is the CME roll Thursday, 8 days before expiry. "The 5 sessions after" is then the
  Friday-to-Thursday window BEFORE expiry week.
- 2020-2025 (most rows): the switch is the Sunday (or Monday) that opens expiry week. "The 5 sessions after" is then
  expiry week itself, Monday to the quarterly third Friday (quad witching).

So the 2.14 is not the effect of any one calendar. The live calendar has to be pre-known from the exchange calendar,
not from a data vendor's switch row.

## The rule (frozen)

- **Calendar E (primary) = quarterly EXPIRY WEEK.** The five sessions Monday to Friday of the week containing the third
  Friday of March, June, September and December, known years in advance. Every switch row since 2022 falls at its
  start, so this is the house's current convention.
  - Mechanism candidates: quarterly options and futures expiry (dealer hedging and pinning into the third Friday, then
    its release), index rebalancing on the third Friday, and contract-roll liquidity.
  - The sign is not obvious from the mechanism: pinning should hurt a breakout strategy, the release should help it.
    That is one more reason this is a read, not a belief.
- **Arm** = crown #314's trades (the ORB_R6 rules, regenerated on the house NQ 5-minute master like the order-flow
  scorer) sized 1.5x in calendar E and 1x otherwise. **Twin** = the same trades at 1x.
- **Reported only, no bar:**
  - calendar R, the CME roll week (the five sessions after the roll Thursday 8 days before expiry);
  - the same rule on #234, #257 and #239.

## The forward test

- **Forward trades** = #314 trades entered on or after **2026-10-05**. The first calendar-E week is **2026-12-14..12-18**.
  About 4 weeks a year x 5 sessions x about 56% of sessions traded gives about 11 calendar-E trades a year.
- **Read at 50 forward calendar-E trades** (about 4.5 years), or on 2031-12-31, whichever comes first.
- **Paired sequential stop** (house rule, `docs/PREREG_paired_sequential_stop_2026-09-29.md`):
  - d_i = (m_i - c) x u_i over ALL forward #314 trades, with c = the running mean size;
  - looks every 10 calendar-E trades from 20;
  - EARLY FAIL at t <= -3.0 (and <= -2.0 without the most extreme trade); EARLY PASS = read the final rule now.

**Final rule — PASS only if all five hold:**
1. **Family-aware calendar null.** S = mean $ a trade inside calendar E minus mean $ a trade outside it, over the
   forward trades. The null is 1,000 random calendars of the same shape: one random 5-session block per calendar
   quarter, placed uniformly among that quarter's sessions, scored on the same forward trades. S must beat the
   **98.3rd percentile** (95% split three ways, for the three regime lenses looked at in that smoke run: realised
   volatility, the day after a stand-down, roll week).
2. The paired mean d > 0 with one-sided t >= 1.645.
3. The arm's ROC at a $30k worst drawdown over the forward trades beats the twin's, and its daily Sortino is not lower.
4. The arm's gain over the twin stays positive without its single biggest calendar-E trade.
5. **Breadth:** the gain is positive in at least 60% of the forward calendar years that hold 5 or more calendar-E
   trades.

A PASS makes it a candidate for an owner call on a sized paper leg. It never adopts anything by itself.

## Stated before any forward data: power and value

- **Power is low.** With about 50 calendar-E trades and a per-trade spread of about $2,500, the standard error of the
  in-calendar mean is about $350. The seen gap (about $330, on the mixed calendar) would be about one standard error.
  The read will most likely be inconclusive: it can kill a large negative effect or confirm a very large positive one.
- **Book value is small even if real.** About 11 trades a year, x 0.5 extra size, x about $330 extra edge, is about
  **$1.8k a year**. That is far below the MDL map's $15k a year at a $30k drawdown, so **on the map rule this cannot
  move BOOK #463.** It is drafted because MANAGER assigned it as a cheap, honest forward read: it answers whether
  calendars matter to ORB at all.
- **Scorer:** `tools/orb_rollweek_forward.py`, to be written before 2026-12-14 (the first calendar-E week). It reads
  the same engine trades as `tools/orb_orderflow_shadow.py`, and prints counts only until a look is due.
