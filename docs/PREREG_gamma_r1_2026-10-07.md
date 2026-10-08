# PRE-REGISTRATION - GAMMA r1: is dealer gamma the ES day-type switch? ONE shared prereg, two arms (TTM's GEXEXP + DISC's GEXREV)

Drafted 2026-10-07 by the TTM lane (MANAGER #67: "ONE shared prereg for both gamma arms ... one pull, one family null
across both arms; whichever lane drafts it, the other reviews"). DRAFT for DISC's review and MANAGER's GO.

**OWNER GATE, stated first.** The owner parked a gamma-exposure idea on 2026-08-15 (memory: "a parked idea - do not start
building it unprompted"), and DISC's scope (docs/SCOPE_DISC_2026-10-06.md line 240) says GEXREV needs the owner's go via
MANAGER. This draft builds nothing into the engine and reads no direction. **Stage A runs only after MANAGER relays the
owner's go.**

- Computed so far: the photograph check, state-day COUNTS, GEXEXP trade counts and GEXEXP's power line from a coin-flip
  side. None of these involves a direction.
- Harness: `tools/gamma_r1_stageA.py`. It holds the shared frame and the GEXEXP arm. The GEXREV arm is wired in after
  DISC's review.

## The data: TV's catalogue row 15, with TV's five caveats written in
- **File:** C:\EdgeLog\_research_cache\squeezemetrics\DIX.csv, from https://squeezemetrics.com/monitor/static/DIX.csv
  (no account, no key). Fetched 2026-10-08T01:15:27Z (10-07 evening MST), 222,738 bytes, sha256 64910ffb94b58d65...
  (squeezemetrics_provenance.json).
- **Contents:** 3,882 trading days, 2011-05-02 .. 2026-10-07. Columns: date, price (S&P 500 close), dix, gex.
- **TV's caveats:**
  1. **A proprietary model:** the method is not public. GEX is a vendor ESTIMATE of dealers' net gamma, not an observed
     quantity.
  2. **S&P / SPX-based, not NDX:** it is used here on ES only.
  3. **The vendor may RECOMPUTE history:** this file is one photograph. A later pull is compared with it and never
     patched into it.
  4. **An end-of-day value with no stated publication time:** a session reads only the value dated strictly BEFORE it,
     so it acts no earlier than the next session.
  5. **The raw file runs to today:** the harness re-hashes the file, aborts on a mismatch, and drops every row after
     2025-06-29 on read.
- **Calendar check (10-07):** the GEX file has NO rows on the 71 CME US-holiday sessions in the ES data (stock market
  closed; the session ends with the 12:55 or 13:00 bar), so no drop-or-carry rule is needed. The CBOE VIX photograph,
  by contrast, carries rows on 23 of them from 2022 on.
- **Added here:** zero-days-to-expiry options grew sharply from 2022, and whether that changed what daily GEX measures is
  a prior. The 2016-21 and 2022-25 halves are printed apart for every arm.

## The state (shared by both arms)
- For each ES session d: p = the share of the 252 GEX days before g(d-1) that are below g(d-1), where g(d-1) is the
  latest GEX dated strictly before d.
- **Short-gamma day:** p <= 1/3 (bottom tercile). **Long-gamma day:** p >= 2/3 (top tercile).
- **Counts (WF 2016-07-01 .. 2025-06-29, no returns):** 2,240 sessions with a state.
  - Short-gamma: 637 days (71 a year); 358 in 2016-21, 279 in 2022-25.
  - Long-gamma: 944 days (105 a year); 599 in 2016-21, 345 in 2022-25.
  - The asymmetry comes from GEX's upward drift over the years. A trailing rank puts more days in the top tercile.
  - Raw GEX is below zero on 245 WF days.

## Mechanism (theory and literature)
- Dealers who are SHORT gamma must sell into declines and buy into rallies to stay hedged, which extends intraday moves.
- Dealers who are LONG gamma do the opposite, damping moves and pulling price back.
- Evidence:
  - Intraday momentum is strongest when hedgers are short gamma (Baltussen, Da, Lammers & Martens 2021 JFE).
  - "Gamma fragility" (Barbon & Buraschi 2020).
  - Stock-level pinning and reversal under long gamma (Ni, Pearson, Poteshman & White 2021 RFS).
- One switch, two arms: momentum on short-gamma days (GEXEXP) and reversion on long-gamma days (GEXREV).

## What is different (one line), and the dead families it is not
**No house row conditions on dealer gamma: the house held no options data until this photograph.**

Dead and not re-tested:
- Unconditioned versions of both arms: opening-range breakouts on ES (TRANSFER / SIPORB / RELAY); the VWAP family, fade
  and trend (MISC_SWEEP.md line 119); REVERT r1 / r2 (2.38, 2.41); r38 CHOP-FADE.
- VIX-state seats (2.59, 2.64), and IMPLIEDMOVE r1 (2.89: an implied-vol yardstick, dead).

## ARM A - GEXEXP (TTM; SCOPE_TTM rank 4), short-gamma days
- **Data:** ES 30m RTH no-adjust master (id 47), loaded with date_to 2025-06-29. Positions are intra-session only.
- **Range:** the high and low of the 10:00 and 10:30 bars (10:00-11:00).
- **Entry:** the FIRST 30m close beyond the range, from the 11:00 bar to the 15:00 bar. 1 ES in its direction at the
  next bar's open.
- **Exit:** the 15:30 bar's close. No stop. One trade a session.
- **Cost:** 0.363 pt a round trip, $50 a point.
- **Cells:**
  - PRIMARY = short-gamma days (bottom tercile): 582 WF trades (65 a year), long 333 / short 249. Per calendar year:
    2016 15, 2017 29, 2018 116, 2019 49, 2020 62, 2021 57, 2022 127, 2023 30, 2024 37, 2025 60.
  - Neighbour = bottom quartile.
- **Reported twins (not bars):** the same rule on ALL sessions, and on LONG-gamma days only. The gamma claim is that the
  primary beats both; the binding test of the conditioning is the family null.
- **Power line** (coin-flip sides on the primary's schedule, added to #463's WF daily, parity 93.81 / 3.816 asserted):
  VOL scale (x0.97) SD 9.0, minimum detectable 14.9, four in five 22.5; $30k own drawdown (x1.18) 10.4 / 17.2 / 25.9.
- **R days among its trade days:** 143.

## ARM B - GEXREV (DISC; SCOPE_DISC rank 5), long-gamma days - DISC's text (review #80, 2026-10-07 18:31), pasted in
1. **Data.**
   - ES 5m RTH no-adjust master 33 (NOADJ_ES_5m_RTH.csv, BALANCE's ES transfer), cut at 2025-06-29.
   - BALANCE's ES roll sessions are never traded.
   - $50 a point; cost 0.363 pt, stress 1.363.
2. **Rules = BALANCE r1 sections 3.2-3.7, unchanged except the day filter and the clock:**
   - #304's band (lookback 40, multipliers 0.75 up / 1.5 down) on ES's own bars;
   - NOISE's VWAP; the stretch x; the side toward VWAP;
   - entry at the next open;
   - target: a close at or through VWAP, filled at the next open;
   - stop: a close beyond the live band edge;
   - flat at 15:55; re-entry allowed when flat.
3. **Day filter.**
   - The long-gamma state (p >= 2/3, GEX dated strictly before d) REPLACES the noon classifier.
   - BALANCE 3.4's second half is KEPT: the day stays open only until its first raw break of either band (any bar from
     k = 1). From that close on, no new entry is taken.
   - A break is the damping failing: the state is a prior, the break is today's evidence.
4. **Clock.** Signal stamps 10:00 .. 15:25 (BALANCE's last fill is 15:30). The start is 10:00 so that VWAP has 6 bars.
   That is band geometry, chosen with no return seen.
5. **Cells.** B1 x >= 1/2 = PRIMARY; B2 x >= 2/3 = NEIGHBOUR (BALANCE's cells, for the same reasons).
6. **PARITY FIRST, before any gamma number.**
   - The harness imports tools/balance_r1_stageA.py's band / VWAP / walk; nothing is re-typed.
   - With BALANCE's noon classifier on ES, it must reproduce BALANCE r1's printed ES transfer exactly: B1 592 trades
     PF 0.99; B2 PF 0.995.
   - That transfer is already public, so this is not a new read.
7. **Counts.** >= 100 WF trades AND a 9-year mean >= 50 a year (MANAGER #41 Q3 withdrew the every-year reading).
   - Any July-June year under 25 is flagged thin (a report).
   - A count-only miss is a RESEARCH ROW.
8. **Twins (reports, like ARM A).** The same fade on ALL sessions and on SHORT-gamma days. The gamma claim is that
   long-gamma beats both. **Arms A and B sit on DISJOINT days by construction** (bottom vs top tercile).
9. **Power line for B.** Coin-flip sides on B1's real schedule, the same lines as ARM A, printed after the counts.
10. **Prior, written down now.**
    - BALANCE on ES was flat (PF 0.99), and the scope gives GEXREV a median ROC of 1, P(>= 15) 3%.
    - It is ~0 in March 2020 by design (those were short-gamma days), so the earner route is unlikely.
    - It runs because it is cheap, not because it is likely.
- R days among long-gamma days: 307 (schedule count). The owner gate stands: no Stage A before MANAGER relays the go.
- **ARM B wired (harness `--parity`, `--counts`, `--power`; 2026-10-07 evening; no gamma direction read):**
  - **Parity PASSED:** with BALANCE's noon classifier on ES, the harness reproduces BALANCE r1's published ES transfer:
    B1 592 trades, PF 0.992; B2 378, PF 0.995. Band parity holds on 5,452 decision bars (3,868 sessions, 61 roll
    switches). The harness asserts it and aborts on a mismatch.
  - **Long-gamma WF sessions traded:** 922. 63 are left out: 22 roll sessions and 41 without a 15:55 bar.
  - **B1 (PRIMARY):** 608 WF trades (67.6 a year) on 469 sessions, of which 139 are re-entries; long 247 / short 361.
    - Per July-June year: 98, 70, 35, 66, 95, 40, 58, 85, 61. None is thin, and the counts line is MET.
    - R days among its trade days: 147. On the 5m trading sessions R days among long-gamma days number 302 (307 on the
      30m sessions).
  - **B2 (neighbour):** 388 (43.1 a year); per July-June year 61, 50, 25, 40, 50, 29, 37, 58, 38. **It misses the
    counts line on the 9-year mean**, so it can be a research row at best. As A3's neighbour it is read only as "net > 0".
  - **Twins:** all sessions, B1 1,350; short-gamma days, B1 354. The code asserts that ARM A and ARM B never trade on the
    same day.
  - **ARM B power line** (coin-flip sides on B1's 608-trade schedule, seed 20261007):
    - VOL scale (x4.111 ES): SD 10.8, minimum detectable 17.8, four in five 26.9.
    - $30k own drawdown (x1.672): 5.0 / 8.2 / 12.5.
  - **Clock:** a 10:00 signal-bar START stamp (BALANCE's convention, which ends at 15:25). At its close, VWAP holds 7
    bars. The signal clock is switched only while ARM B's schedule runs, and the run asserts that it was restored.

## ONE family null (MANAGER #67)
- Within each calendar year, the session state labels (short / long / middle) are shuffled across that year's sessions,
  keeping each label's count.
- BOTH arms are re-run on the shuffled labels. 1,000 draws, seed 20261007.
- Statistic: the family MAX of own ROC@$30k over the four cells (two per arm).
- It keeps each arm's mechanics, trade density and year mix, and removes only the gamma timing.

## Stage A bars (walk-forward 2016-07-01 .. 2025-06-29; per arm; all must pass)
- **A1 standalone (house line #45):**
  - own ROC@$30k >= 15, OR the earner route;
  - PF > 1;
  - >= 100 trades and >= 50 a year;
  - >= 6 of 9 July-June years positive.
- **A1b:** the route holds without 2020.
- **A2:** the arm's primary own ROC@$30k > the family null's p95.
- **A3:** the arm's neighbour is net positive.
- **A4:** net > 0 without the best trade; net > 0 at 2x cost.
- **Counts:** >= 100 WF trades AND a 9-year mean >= 50 a year (MANAGER #41 Q3); any July-June year under 25 is flagged thin (a report). A cell that fails on count alone and clears the rest is a RESEARCH ROW, not a pass.
- **Every ROC @ $30k prints its DD5 beside it (#77).**
- The arms are judged apart. A pass in one arm is that arm's pass only, and does not license the other.
- No EARLY block: GEX starts in 2011-05, and the 252-day warm-up ends in mid-2012. 2012-06 .. 2016-06 is reported.

## Reported (no verdict)
- Addendum 2 diagnostics per arm:
  - the event path;
  - regime halves 2016-21 / 2022-25 (the zero-days-to-expiry question);
  - the cost curve at 0 / 5 / 10 / 20 bps;
  - per-year rows;
  - long vs short.
- The R-day sum and the dollars inside #463's worst WF drawdown.
- The book add at the VOL scale.
- Overlap with NOISE #422's and ORB's held bars. GEXEXP is an ES breakout on stress-leaning days, so its overlap with the
  NQ momentum legs is expected to be high and is printed first.

## What follows
- **PASS** (per arm): a plugin with a daily data input (the photograph), harness parity, then a WINDOW-PINNED Auto-Validate
  on a RANGED file (900 trials; lockbox veto-only), then a RUNBOARD row.
- **FAIL:** dead; no other source, state cut or window. Ledger row, lane notes, RUNBOARD research rows (family MISC).
- Nothing live or in the adopted book changes without the owner.
