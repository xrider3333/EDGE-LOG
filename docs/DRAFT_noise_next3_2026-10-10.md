# NOISE next three - CLOSED AT DRAFT (MANAGER #83, 2026-10-10)

MANAGER #83: land the three rows (ledger 2.151-2.153); GAMMA-SORT and MIRROR closed; HALVES = no alarm, GO as a report
line in the weekly NOISE read (`tools/noise_halves_read.py`). The $706 cost-scaling footnote is routed to ORB (roll-guard owner).

## The draft as sent (MANAGER #864)

# DRAFT - NOISE next three (MANAGER #82, 2026-10-10): the failed-break half, power-first

Drafted 2026-10-10 by the NOISE lane. Nothing has run beyond the power lines below, which read no candidate result: coin-flip
sides, a within-year label shuffle, and the WF spread of #422's own (already seen, ledger 2.82) exits. No GO is asked for
items that close at draft.

Base: #422 = NOISE_1_8_CT304H (gate 20 / 1.15, 1.75x), NQ 5m RTH no-adjust master, cost 0.533 pt, $20 a point. Walk-
forward signal dates 2016-07-01 .. 2025-06-29. 2,803 trades; exit kinds 745 held to close / 1,949 VWAP / 109 stops (this
matches the anatomy's 745 / 1,943 / 109; the master has been restated since). Own WF ROC@30k 87.79, max DD $17,012.
Scripts: `tools/noise_next3_power.py` and `tools/noise_next3_share_calib.py`; output `tools/r37_results/noise_next3_power.txt`. Seed 20261010, 2,000 draws.

MDE = the true edge at which the median draw clears its bar, in $ a year at a $30k drawdown (= ROC points x $1,000).

## N1 GAMMA-SORT - does dealer gamma pick #422's failed-break days? CLOSES AT DRAFT
- **What:** #422 sized 1.5x on short-gamma days and 0.5x on long-gamma days, with GAMMA r1's state, unchanged (p = trailing
  252-day rank of the latest GEX dated strictly before the session; <= 1/3 short, >= 2/3 long). The mechanism is
  Baltussen-Da-Lammers-Martens (2021): dealers who are long gamma damp intraday moves, so breaks fail. This is new
  information, not a refit of #422. It would share GAMMA r1's photograph (DIX.csv sha256 64910ffb...) and its owner gate.
- **Map / power:**
  - The null shuffles the state labels within each July-June year, keeping the counts. Only the counts are read here.
  - Mean size is 0.930: GEX drifts upward over the years, so long-gamma days outnumber short-gamma days.
  - Delta ROC (tilt minus #422): null median -9.81, p95 21.90, SD 18.20.
  - **MDE 50% = 31.7 ROC points = $31,700 a year at a $30k DD; 80% = $47,000.** The ROC of a leg already at 87.8 has a
    drawdown set by one episode, so random re-weighting swings it widely.
- **Prior, written now:**
  - Delta ROC median about +2 (about $2,000 a year), and P(delta >= 31.7) under 5%.
  - Basis: the VIX-state seats are dead (2.59, 2.64); the anatomy's high-volatility tercile and every day tag sat inside
    their bands (2.82); no sized leg aimed in both WF and LB (ML shuffle audit); GEX moves with volatility.
- **Verdict: prior < MDE. Close at draft, one ledger line.**

## N2 HALVES - a scale-free forward read of the failed-break share. CLOSES AT DRAFT (a report line at most)
- **What:** read #422's failed-break SHARE on the forward rows. The share is a count, so it does not grow with NQ's price
  (Q35's sizing flaw). Each exit kind is also read in band units: the signed move over sigma x entry, cost included.
- **WF band units:**
  - All trades: +0.152 (SD 1.47).
  - Held to close: +1.48 (26.6% of trades).
  - VWAP exits: -0.26 (69.5%).
  - Stops: -1.47 (3.9%).
  - A 10-point rise in the failed share erases the edge by itself (0.166 x 1.48 - 0.795 x 0.26 - 0.06 = about -0.02).
- **Power:**
  - On iid trades, a +10-point share rise shows in 120 trades (4.6 months). But the share swings by year (2016 0.80,
    2019 0.78, 2021 0.60), so the alarm has to be calibrated on WF windows:
    - in a 120-trade window, a +10 rise clears the WF p97.5 (0.833) only 27% of the time;
    - in a 240-trade window (9.2 months), 40% of the time.
  - In band units, "edge gone" needs 582 trades (22 months) on iid trades; "edge halved" needs 90 months.
  - FRONTIER's harm monitor (option 2) already has 99% power on NOISE by 36 months.
- **Prior:** n/a (a monitor). **Verdict: under-powered next to the harm monitor, so no new alarm.** At most, the weekly
  forward ranking prints the share as a report line with its WF year range beside it, with no rule attached.

## N3 MIRROR - trade the failed break's other side. CLOSES AT DRAFT
- **What:** after the session's FIRST #422 VWAP exit, take the opposite side at the same next-open fill and hold it to
  the session close, with no stop. It is a new leg that trades bars #422 is flat on, so it is not a refit.
- **Map / power:**
  - Schedule: 938 WF trades (104 a year), median |move| to the close 40.4 pt.
  - Coin-flip null ROC@30k: median -0.37, p95 7.18, so the bar is ROC 15.
  - **MDE 50% = 11.0 pt a trade ($219 at 1 NQ) = $15,850 a year at a $30k DD; 80% = $25,600.**
  - So the reversal must win 27% of the median move on average. No house NQ intraday rule except NOISE itself shows a
    skew that large.
- **Prior, written now:** about $1,000-2,000 a year (ROC 1-2), P(ROC >= 15) about 3%.
  - The VWAP family is dead in both its fade and trend forms (MISC_SWEEP line 119).
  - r38 sweep-reclaim is 0 of 20 and flat before cost.
  - BALANCE's NOISE-band fade on ES has PF 0.99; the TLT fade (ledger 2.109) is flat before cost.
  - The opposite-band continuation after a failed break is already traded by #422's own re-entries (+$93 a trade, 2.82).
- **Verdict: prior < MDE. Close at draft, one ledger line.**

## Also ruled out before drafting (not counted as items)
- A "room to pay" entry filter (09-22 idea): the anatomy already printed the nearest-VWAP tercile ($23 a trade). Any
  room cut would be mined from a seen table (ledger 2.1), i.e. a refit.
- Order-flow confirmation of the break: Custom ML's order-flow r1 shadow already sizes #422 on 10s delta. The capture has
  zero-delta sessions (TV QA 10-10: 8 of 25 NQ sessions). History starts in 2026, so the power is nil.
- Overnight carry of the held-to-close trade: gap continuation, ONDRIFT, DD-WEEK overnight and GAPGO are dead or
  retracted. The NQ overnight SD makes the MDE larger than N3's.

## Engine footnote (found while building the power lines; harmless, disclosed)
- Since the 10-08 roll guard, the engine runs signals on a ratio-adjusted series and fills at raw prices.
  - Consequence 1: it books #422 at 4,855 trades over 2010-26 against the strategy's direct 4,847.
  - Consequence 2: the wrapper's extra-size cost term is divided by the adjust ratio k, so each 1.75x trade is charged
    (s - 1) x 0.533 x (1 - 1/k) too little. Measured on the WF: 542 sized trades, $0.38-1.55 each, $706 in all (0.16% of the sized $447,740).
- **Trap:** unit P&L can no longer be backed out of the engine's sized pnl as pnl / size. Run the #304 core instead (done
  here).
