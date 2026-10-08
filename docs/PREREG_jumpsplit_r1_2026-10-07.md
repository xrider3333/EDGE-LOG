# PRE-REGISTRATION - JUMPSPLIT r1: does a diffusive morning continue into the close? NQ and ES apart (TTM scope rank 8, opened by MANAGER 2026-10-07)

Drafted 2026-10-07 evening by the TTM lane BEFORE any real-direction number exists. DRAFT for MANAGER's ADVERSARIAL REVIEW;
no Stage A before that review and a GO.
- Computed so far: state-day and trade COUNTS per arm, and each arm's power line from a coin-flip side. None of these
  involves a direction.
- Harness: `tools/jumpsplit_r1_stageA.py` (`--counts`, `--power`). It reuses HALFHOUR r1's book and power-line code.

## THE PRIOR, written down first: LOW
- Scope prior (SCOPE_TTM rank 8): ROC -5..10 at $30k, median 0, P(>= 15) 3%. It is the lowest-ranked drafted item.
- **It conditions on the same OHLCV as the dead first-hour-to-close momentum** (LDM, DRIVE; SCOPE_TTM dead-list point 1).
  The only new thing is the jump/diffusion split of the morning's variance.
- **Power is poor:** the minimum detectable book-add lead is 19.2 points (NQ) and 17.3 (ES) at the VOL scale.
- **Expected overlap with NOISE #422** on NQ trend days is high and is printed first.

## Mechanism (theory and literature)
- Realized variance splits into a continuous (diffusive) part and a jump part. Bipower variation, the sum of products of
  adjacent absolute returns, estimates the continuous part and is robust to jumps (Barndorff-Nielsen & Shephard 2004,
  2006). The relative jump (RV - BV) / RV is the jump share (Huang & Tauchen 2005).
- A move built from many small same-sign steps reflects order flow and information arriving gradually, which tends to
  persist. A move made in one jump is a discrete repricing that is already done (Lee & Mykland 2008 RFS on jump timing;
  the intraday-momentum literature: Gao, Han, Li & Zhou 2018 JFE).
- The hypothesis: the morning's direction carries into the close only on DIFFUSIVE mornings.

## What is different (one line), and the dead families it is not
**No house row has split the morning's variance into jump and diffusion: LDM / DRIVE took the morning's direction on every
day or on size filters.**

Dead and not re-tested:
- LDM and DRIVE (first-hour-to-close momentum).
- The MISC round-16 compression breakouts; NR7 / NR4.
- Wide-range-bar continuation (NOISE's mechanism; the ES transfer and re-tune are dead).

## Rules (frozen; one arm per instrument, NQ and ES judged APART)
**Data.**
- NQ 5m RTH no-adjust master (id 37) and ES 5m RTH no-adjust master (id 33), loaded 2010-06-07 .. 2025-06-29.
- Positions are intra-session only, so the no-adjust prices are exact.
- Full 78-bar sessions only: half-days and the ES holes are skipped. That leaves 3,746 sessions per arm.

**The morning (known at 12:00 ET).**
- r = the 30 5m log returns of 09:30-12:00: the first from the 09:30 open to the 09:30 bar's close, then close to close
  through the 11:55 bar.
- RV = sum r^2.
- BV = (pi/2) x (30/29) x sum |r_i| |r_i-1|.
- **RJ = (RV - BV) / RV, NOT truncated at zero, so there are no ties.** RJ is below zero on 43% (NQ) and 41% (ES) of WF
  sessions.
- p = the share of the 252 prior full sessions' RJ (same instrument) below today's.
- Direction = the sign of (the 11:55 bar's close - the 09:30 open). A zero move means no trade.

**Trade.**
- **DIFFUSIVE morning:** p <= 1/3 (the bottom tercile of the relative jump).
- Enter 1 contract in the morning's direction at the 12:00 bar's open; out at the 15:55 bar's close. No stop. One trade a
  session.
- Cost: NQ 0.533 pt x $20; ES 0.363 pt x $50.

**Cells and counts (schedule only).**
- **NQ:**
  - PRIMARY, bottom tercile: 760 WF trades (85 a year), long 429 / short 331, 211 R days. Per calendar year: 2016 44,
    2017 82, 2018 79, 2019 86, 2020 87, 2021 83, 2022 86, 2023 83, 2024 82, 2025 48.
  - Neighbour, bottom quartile: 560 (62 a year).
- **ES:**
  - PRIMARY: 743 WF trades (83 a year), long 401 / short 342, 208 R days. Per calendar year: 2016 36, 2017 79, 2018 87,
    2019 85, 2020 85, 2021 89, 2022 69, 2023 88, 2024 79, 2025 46.
  - Neighbour: 555 (62 a year).
- **Reported twins (not bars):** the same trade on ALL sessions (NQ 2,232 / ES 2,219 WF) and on the TOP-tercile (jump)
  mornings (742 / 735). The claim is that diffusive beats both. Jump mornings are the opposite pole of the hypothesis, so
  they should be the worst.

## "Per stretch" (MANAGER 10-07), as the TTM lane reads it
Every figure is printed separately for each STRETCH, each one sized on its own drawdown, NQ and ES never pooled:
- EARLY 2011-07-01 .. 2016-06-30 (the first year is the 252-session warm-up): NQ 424 / ES 421 primary trades.
- WF 2016-07-01 .. 2025-06-29: 760 / 743.
- WF 2016-21: 461 / 461. WF 2022-25: 299 / 282.

**The stretches also BIND (bar A5):** net > 0 in EARLY, in WF 2016-21 and in WF 2022-25, per arm. MANAGER: please correct
this reading in review if "per stretch" meant something else.

## The family null (binding for A2)
- Within each calendar year, each arm's session state labels (bottom tercile / bottom quartile / other) are shuffled across
  that year's sessions with a state, keeping counts. Each session keeps its own morning direction and P&L.
- 1,000 draws, seed 20261007.
- **Statistic:** the family MAX of own ROC@$30k over the FOUR cells (two arms x two cells). The arms are judged apart, but
  each is charged for both arms having been tried.
- The RJ state is weakly persistent day to day, so a within-year shuffle is the right null here (unlike VRPES's monthly
  state).

## POWER LINES (house rule MANAGER #37; coin-flip sides on each arm's primary schedule, added to #463's WF daily, parity 93.81 / 3.816 asserted)
- **NQ:** VOL scale (x0.975) SD 11.7, minimum detectable 19.2, four in five 29.1; $30k own drawdown (x0.842) 10.4 / 17.2 /
  25.9.
- **ES:** VOL scale (x1.294) SD 10.5, minimum detectable 17.3, four in five 26.1; $30k own drawdown (x0.469) 4.8 / 7.9 /
  11.9.

## Stage A bars (per arm; walk-forward 2016-07-01 .. 2025-06-29; all must pass)
- **A1 standalone (house line #45):**
  - own ROC@$30k >= 15, OR the earner route (>= 5 plus the R-day sum above the null's p95);
  - PF > 1;
  - >= 100 trades and >= 50 a year (MANAGER #41 Q3); any July-June year under 25 is flagged thin;
  - >= 6 of 9 July-June years positive.
- **A1b:** the route holds without 2020.
- **A2:** the arm's primary own ROC@$30k > the family null's p95.
- **A3:** the arm's neighbour is net positive.
- **A4:**
  - net > 0 without the best trade;
  - net > 0 at 2x cost;
  - net > 0 without 2020-02-15 .. 04-30.
- **A5 (per stretch):** net > 0 in EARLY, in WF 2016-21 and in WF 2022-25.
- **Every ROC @ $30k prints its DD5 beside it (#77).** A worst drawdown > 1.3 x DD5 is flagged "driven by one episode".
- A pass in one arm is that arm's pass only, and does not license the other.

## Reported (no verdict)
- Addendum 2 diagnostics per arm:
  - the event path (30m marks 12:00 .. 16:00);
  - regime halves;
  - the cost curve at 0 / 5 / 10 / 20 bps;
  - per-year rows;
  - long vs short.
- The twins (all sessions; jump mornings), each with ROC and DD5 per stretch.
- **Overlap with NOISE #422's and ORB's held bars, printed FIRST.**
- The R-day sum and the dollars inside #463's worst WF drawdown.
- The book add at the VOL scale and the $30k twin.

## What follows
- **PASS** (per arm): a JUMPSPLIT_1_0 plugin, harness parity to the trade first, then a WINDOW-PINNED Auto-Validate on a
  RANGED file (900 trials over the tercile cut, the morning window and the exit bar; lockbox veto-only), then a RUNBOARD
  row.
- **FAIL:** dead; no other window, estimator (truncated RJ, the Lee-Mykland test, tri-power) or instrument. Ledger row,
  TTM.md note, RUNBOARD research rows (family MISC, with --wf-dd5).
- Nothing live or in the adopted book changes without the owner.
