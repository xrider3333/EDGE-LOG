# PREREG: CTXSHORT r1 - the owner's CBD / ENGD shorts as a frozen NQ 1-minute scan WITH his context filter (DISC, 2026-10-17)

**Why.** Owner 10-17 via MANAGER #111; scope GO in MANAGER #112. Three should-have-traded NQ 1m shorts were deep-dived in
docs/SHOULD_HAVE_TRADED_2026-10-12_14_16.md: 10-12 CBD 10:06, 10-14 ENGD 09:57 and 10-16 ENGD 10:51. The owner asks how to keep
trading them, how to improve them and which parameters to use.
- **What the three share** is not the candle or the point score (the best one scored 5/9). It is the context:
  - below yesterday's CLOSE (MANAGER #112 hold 1: never below yesterday's LOW; 10-16 was 271 points above it);
  - below the 5m and 30m 200 SMA;
  - falling 5m and 30m 20 EMAs;
  - three red 30m bars.
- This note freezes that context, the two trigger shapes and three exit rules before any outcome is read. It is the ALGO_SCOPE item-2
  box-breakout scan, short side, with the context filter it never had. Study tag CTXSHORT; family CBU-Q (owner setups automated).

**What is already dead, and what is different** (setups/ALGO_SCOPE.md, RESEARCH_LEDGER):
- Rounds 37-38: 0 of 59 NQ 1m short-hold cells, including box break; fixed targets lose at house cost.
- The ALGO_SCOPE box-breakout scan (2018-25, both sides) sat near break-even before costs.
- SETUPS round 1: CBD / ENGD on NQ are tail-only. The ENGU-Q short mirror: 0 of 61.
- **New here:** (a) the 5m/30m downtrend context filter, which none of those had; (b) the 09:45-11:30 window; (c) exits in R from the
  signal-bar stop.
- **E1 is a fixed 2R target.** That is close to the standing "do not re-test 1m fixed-target scalps" rule. It is read here only
  because it is the owner's bracket from the deep dive, and only with the context filter, which rounds 37-38 did not have.
- The standing worry is also tested: a short on a down-trend day can be a crown shadow (NOISE #382, ORB #314), the way CBU-Q was.

## Data and window
- **One master: NQ 1-minute ETH, back-adjusted** (`ADJ_NQ_1m_ETH.csv`, id 66). The harness asserts the filename and id and records the fingerprint.
  - Its 09:30-15:59 slice is the RTH series. It equals `ADJ_NQ_1m_RTH.csv` (id 68) bar for bar: 99,192 bars in 2015, every OHLCV
    difference 0.
  - Signals, C1 and trades use the RTH slice. The 5m / 30m context bars use all ETH minutes, as the deep dive and tools/point_score.py
    do (the owner's NQ1! chart).
  - P&L is in points, which is exact for an intraday trade.
- **Walk-forward years only:** sessions 2016-07-01 .. 2025-06-29 (BOOK.md: the lockbox starts 2025-06-30). Warm-up bars from 2016-03-01.
  No outcome is read on any lockbox day.
- **Regular sessions only.** A session whose last RTH bar starts before 13:10 is a holiday stub, as is any listed CME holiday
  (tools/point_score.py's list).
  - A stub never carries a signal and never counts as "yesterday": C1 uses the last REGULAR session's close.
  - Its minutes still feed the ETH 5m / 30m bars.
  - Early closes that end at 13:14 are regular sessions.
- **Answer key** (Stage 2, flags only, after the WF read). 2026 bars (2025-11 .. 2026-10-16, lockbox era and later) are loaded only to
  compute flags on these days. NQ for NQ / MNQ; ES (`ADJ_ES_1m_ETH.csv`, id 58) for MES.
  - **The owner's 3 dates are DESIGN EXAMPLES, not held-out tests.** The rule's numbers were drawn from them:
    - the 2.0x body and 1.5x volume sit just under their 2.3-8.0x and 1.65-1.7x;
    - K = 4 admits the 10-12 base (62 points, about 3.35 x ATR14).

    Recall there is in-sample.
  - **The journal's real CBD / ENGD futures trades** are 6 rows but 5 distinct signals (n32 / n33 share 2026-06-12 09:45), all MES.
    - 3 of the 5 are outside the 09:45-11:29 window and are not reachable by construction: 05-04 12:07, 05-07 14:09 and 05-13 09:30.
    - Reachable: 04-28 10:35 CBD and 06-12 09:45 CBD.

## The rule (one cell; nothing is searched)
At the close of a 1-minute RTH bar whose START is 09:45-11:29 ET, on a regular session, using only bars closed by then. The 5m and 30m
bars are clock-anchored on ETH minutes (5m: :00, :05, ...; 30m: :00 / :30, the same edges as 09:30 anchoring). A 5m or 30m bar counts
only once it has ended (its end <= the 1m bar's close).

**Context, all four:**
- C1: close < the prior regular session's RTH close (its 15:59 bar, or the last bar of an early close).
- C2: close < the 200 SMA of the last completed 5m bars AND < the 200 SMA of the last completed 30m bars.
- C3, for both the 5m and the 30m: the 20 EMA of the last completed bar < that of the bar before, AND close < it.
- C4: the last three completed 30m bars are red (close < open).

**Trigger.** A red signal bar whose body |close - open| is >= 2.0x the mean |close - open| of the prior 10 RTH bars, green ones included,
and whose volume is >= 1.5x their mean volume. Plus one of:
- **CBD:** the prior 15 RTH bars of the session span (highest high - lowest low) <= 4.0 x ATR14 (1m, the prior 14 bars), and the close is
  below their lowest low. The 15 bars must all be in this session, so 09:45 can fire.
  - **Disclosed:** K = 4 was set to admit the owner's 10-12 base. It is double the ALGO_SCOPE box scan's K <= 2, and on 2015 window bars
    58% pass it, so it is a loose box, not a tight base.
- **ENGD:** the close is below the lowest low of the prior 3 bars, AND the prior 10 bars made no new session high. That is, their highest
  high is below the RTH session high made before them, through bar i-11; the session runs from 09:30.
  - This is plainly "no new session high in 10 bars", not a swing-pivot lower high.

**Overlap, disclosed from the pre-WF flag census (2015, no outcomes).**
- Bare triggers: CBD 256, ENGD 537, both on one bar 237.
- With the context on: CBD 23, ENGD 42, and all 23 CBD bars are also ENGD bars.
- So trades are labelled three ways, CBD only / ENGD only / BOTH. The shape reads are "any CBD" (CBD + BOTH), "any ENGD" (ENGD + BOTH)
  and BOTH. They overlap, and nothing is dropped by label order.

**Trade:**
- Entry at the next bar's open. Stop at the signal bar's high; R = stop - entry.
- If that open is at or above the signal high, the signal is skipped; it does not use a slot.
- A stop gapped through fills at the open.
- One position at a time; a signal on a trade's exit bar is not taken.
- At most 2 entries a session; flat at the session's last bar close.

**Exits, three rules run side by side on the same signals:**
- **E1:** a 2R bracket (target at entry - 2R; a bar that touches both counts as stopped).
- **E2 (PRIMARY; the deep dive's recommendation):** half off at 2R, then the rest's stop moves to breakeven and trails under the highest
  high of the last five completed ETH 5m bars (read at each bar's open).
  - If the bar that fills the half also trades back to the entry, the runner is out at breakeven on that bar (conservative).
  - Booked per contract: two half-contracts, one round-trip cost per contract.
- **E3:** hold to the close with the signal-high stop.

**Costs and units:**
- 0.783 points a round trip (house NQ). Stresses: +1 tick a side (+0.5 point) and the MNQ cost of 1.44 points.
- **$ curve:** $20 a point, 1 contract, booked on the day.
  - **Disclosed deviation:** the deep dive says "size by the stop". A fixed lot gives a 63-point-stop trade twice the weight of a 31-point
    one, and late, higher-priced years more weight.
  - So a **risk-normalised R curve** is reported beside it: net R x $500 a trade, i.e. a fixed $ risk.

## Stage 0 (printed before any outcome): census and power line
- **Selftest first** on synthetic bars; the run stops on a failure. It checks:
  - bar stamps (5m 09:30 ends 09:35; 30m 09:30 ends 10:00);
  - the 5m-trail timing;
  - CBD at 09:45;
  - E2's same-bar breakeven;
  - an empty-trade frame.
- **Census:** signal bars per year in the WF window (CBD only / ENGD only / BOTH, plus the bare triggers) and context sessions.
- **Power line per exit:**
  - n = the sum over WF sessions of min(signal bars, 2). This is an outcome-free upper bound on trades.
  - MDE (80%, two-sided 5%) = 2.8 x SD / sqrt(n).
  - SDs set now:
    - E1 1.4 R, about the most a -1 / +2 bracket can have;
    - E2 1.6 R;
    - E3 4.0 R, a guess for a one-bar stop held to the close (the owner's three gave -1.0, +4.6 and +12.0 R).
  - Prior: +0.10 R a trade (round 37's best ride exit, PF about 1.19).
- **If the prior is below the MDE, the read is stamped UNDERPOWERED.**
  - A FAIL then means "not shown", not "dead".
  - At 2015's capped rate (35 signals a year, about 315 over the WF years), every exit is expected to be UNDERPOWERED (MDE 0.22 / 0.25 /
    0.63 R). So this is a descriptive DISC read for the owner first. The Auto-Validate route below is kept only for the case where the
    trade rate and the result clear the house bars.

## Stage 1: the reads, per exit rule
- **The house four numbers** on the WF daily curve, from `augur_engine.drawdowns.four_numbers`: ROC @ $30k, DD5, DD % from peak and
  Sortino. Every regular session is a row, zero days included.
  - These are given for the $ curve and the R curve.
- **Also:**
  - trades a year and win rate;
  - average win / average loss in points;
  - gross points a trade vs the round-trip cost;
  - mean R gross and net;
  - block-bootstrap t of the daily mean (20-session blocks, 2,000 draws, seed 20261017) on the R curve (the gate) and on the $ curve
    (reported).
- **The same reads for:**
  - the two cost stresses;
  - the halves 2016-07..2020-12 and 2021-01..2025-06-29;
  - excluding Feb-Apr 2020;
  - excluding the 3 best trades;
  - any CBD, any ENGD and BOTH.
- **Crown shadow, both crowns** (NOISE #382 and ORB #314, each re-run from its run doc: strategy, params, master and cost, by the
  queue_guard loader as in tools/setups_r1_overlap.py):
  - per crown, the trades on its short days, its long-only days and its flat days (each read apart);
  - the share of entries made while that crown's short is open at the entry minute;
  - the read on days both crowns are flat.

## Verdicts (set now; per exit rule, at NQ cost; checked in this order)
1. **FAIL** unless all of these hold:
   - gross points a trade > the 0.783 round trip;
   - net ROC @ $30k > 0;
   - not one episode (worst drawdown <= 1.3 x DD5);
   - >= 100 trades;
   - net > 0 in both halves.
2. **CROWN SHADOW** if it fails the precedent shadow test (tools/setups_r1_overlap.py). The test is: on EACH crown's flat days
   (#382 and #314 separately), net > 0 and >= 30% of the rule's own net. No book value; a discretionary aid only.
3. **PASS - EDGE** if the R-curve bootstrap t >= 2.0 for E2 (primary), or >= 2.4 for E1 or E3 (secondary, Bonferroni over 3).
   - Route: **Auto-Validate candidate** only if trades a year >= 50 AND ROC @ $30k >= 15 (the MDL bar). That means a ranged CBU-Q
     strategy file, window + master pinned, 900 trials, for MANAGER's GO. Otherwise the route is a discretionary aid.
4. **PASS - MANAGER's bar, edge not shown** otherwise; a discretionary aid.

- The summary prints how many of the 3 exits pass.
- If more than one passes, E2 goes forward when it is among them; otherwise the higher t.
- **Answer key (Stage 2, report only, flags only):**
  - for each key signal, whether it is reachable by construction;
  - whether the frozen rule (context AND trigger) fires within 5 minutes of it;
  - trigger-only fires (context off) are listed apart;
  - which of C1-C4 held at the owner's candle.
- Nothing here changes a rule, a size or a live leg.

Harness: `tools/disc_ctxshort_r1.py`. It embeds this note's LF sha256 and stops on a mismatch; both hashes go to MANAGER before the run.
