# PREREG - BALANCE r1 (NQ range-day VWAP fade on no-NOISE-break-by-noon days) - DRAFT for MANAGER review (2026-10-06)

Drafted 2026-10-06 by the DISCRECTIONALRY-TO-ALGO lane. The research id stays under MISC until something passes
(docs/SCOPE_DISC_2026-10-06.md line 8). **Written BEFORE any return is read.** It follows SCOPE_DISC 87ac032c (rank 2),
accepted by MANAGER #39 with ruling (b).
- No BALANCE trade, P&L, coin-flip leg or null draw exists yet.
- The only numbers below are published house figures, each cited, and session COUNTS from a read-only band-parity check.
  That check read no P&L (section 4).
- Code waits for MANAGER's GO. The harness `tools/balance_r1_stageA.py` is not written. It runs `--counts`, then
  `--power`, then the real run. Their output is appended here as AMENDMENT 1 before the real run. AMENDMENT 1 cannot
  change sections 3, 6 or 8.
  - `--counts` prints only numbers that do not depend on any BALANCE exit (section 4).
  - `--power` and the overlap test use the real schedule. Re-entry follows only a TARGET exit, so the schedule's trade
    count and holding times reveal a lower bound on target hits. This is disclosed, as house practice (section 5).

## AMENDMENT 0 - MANAGER #40 review (2026-10-06 10:02), applied before any number
Source: C:\EdgeLog\chat_inbox\DISCRECTIONALRY-TO-ALGO.jsonl #40, reviewing this prereg at c2f6346a.
- **Verdict: GO WITH EDITS.** Write the harness now. Run `--counts`, then `--power`, then the real run under the
  60-minute rule. AMENDMENT 1 cannot touch sections 3, 6 or 8.
- **Applied before any number.** No BALANCE trade, P&L, coin-flip leg or null draw existed when this amendment was
  written. The body edits listed below are part of the frozen prereg.
- **The five sign-offs and two edits, in MANAGER's numbering:**
  1. **RAW band-break classifier: ACCEPTED** (section 3.3). The #304-eligible version stays a crosswalk count, never a
     cell. The choice, made after seeing counts and before any return, is disclosed. No body change.
  2. **Roll sessions never traded: ACCEPTED,** frozen (36 WF sessions, section 3.1). `--counts` prints how many
     BALANCE-labelled roll sessions had a first signal, as section 4 (i) planned. No body change.
  3. **"Before any return": reading CONFIRMED** (section 4). The three-way split with #304's and L's dollars, and the
     one share, print in `--counts`. The BALANCE-side co-loss shares print after the run, as defined now. No body
     change.
  4. **In-sample band: screen framing ACCEPTED.** The Auto-Validate lockbox is the first clean read (house rule,
     lockbox veto-only). **Edit:** three REPORTED twins of B1, with band settings NOT fit on any return:
     (lookback 20, 1.0 / 1.0), (40, 1.0 / 1.0) and (60, 1.0 / 1.0). Same rules, printed beside B1, no verdict. If B1's
     WF net sign flips on any twin, the pass is written 'fragile' and only the Auto-Validate lockbox can clear it.
     Body: sections 1, 8 (reports and verdict), 10, 11 and 12.
  5. **The >= 50 trades a year bar STAYS** (bar 6). **Edit:** a cell that fails on count alone and clears the other 12
     bars is a RESEARCH ROW on the RUNBOARD (as TTM r24), not a pass, with no variants. Body: sections 4, 8, 10 and 11.
  6. **Edit: the Auto-Validate space is declared now,** before any number, with at least 6 configs so the report has
     its surfaces (never a pinned file): stretch 6 / 7 / 8 / 9 twelfths x last fill 15:00 / 15:30 = 8 configs, window
     pinned to WF, 900 trials, lockbox veto-only. It replaces the earlier stretch-only space (`stretch_12ths` 6..8).
     Body: sections 3.6 (a pointer), 11 and 12.
  7. **Edit: the drafting counts are superseded.** The `--counts` stamp-based reprint on the cut load supersedes the
     drafting counts (914 / 1,078) everywhere they are quoted. Body: sections 4 and 10.
- **Unchanged, as written:** the zero-overlap assertion by construction (section 7), the family null on both cells
  (section 6), the power line and null p95s reprinted before the cell rows (section 5), the fixed seeds and the EARLY
  bar (bar 12).

## 0. The frame: MANAGER #39, ruling (b)
Source: C:\EdgeLog\chat_inbox\DISCRECTIONALRY-TO-ALGO.jsonl #39, 2026-10-06.
- This is a ONE-prereg exception, not a reopening. NQ/ES intraday belongs to STRATEGY-BEATING (MANAGER #30), and its
  10-05 scope closed that ground. MANAGER tells STRATEGY-BEATING.
- **Earner route ONLY.** The standalone tail cannot reach 15. A cell with own ROC >= 15 that fails the R bars still fails.
- The work is fixed:
  - the 2 cells as written (1 classifier x 2 stretch thresholds);
  - ES as a transfer report;
  - the three-way split of #304's held days, with the co-loss share, BEFORE any return;
  - the family null.
- Zero passes = dead. The VWAP family stays closed, with no variants and no second NQ item from this lane.
- Drafts may go on main labelled DRAFT; code waits for GO.

## 1. Mechanism, and what is different
- **Mechanism.** Moves inside NOISE's noise area are noise (Zarattini, Aziz & Barbon 2024, the paper NOISE implements).
  - If price has not left the area by noon, the afternoon is a balance day, and stretches away from VWAP should revert.
  - Short-lived order imbalances revert (Grossman & Miller 1988, Journal of Finance). This is an analogy only.
- **Owner grounding.** ENGU bought inside the range: new high 2 of 16 (setups/ALGO_SCOPE.md line 88). This is grounding,
  not evidence.
- **What differs, in one line:** **only the session VWAP anchor and flat by the close are shared with VWAP_FADE 1.0.
  Everything else differs: (1) the day filter is #304's own band unbroken by 12:00; (2) the clock is afternoon-only;
  (3) the stretch is a fraction of the room from VWAP to the band edge, not vwsigma units; (4) entry is the next bar's
  open, not the signal close; (5) the target is a close at or through VWAP filled next open, not an intrabar touch of
  the prior bar's VWAP; (6) the stop is the live band edge on closes, not a fixed 2.5 vwsigma intrabar stop, so every
  stop is a raw #304 band break** (VWAP_FADE_1_0.py lines 189-216 and 251-254).
- **Dead, not re-tested, and not read as support:**
  - VWAP_FADE 1.0 / 2.0: FAIL / weak (BACKTESTING_STACK.md line 720; PARAM_LIBRARY.md line 310). Version 2.0 was
    archived on 2026-08-12 as leak-compromised (BACKTESTING_STACK.md line 2334).
  - The VWAP family is closed, fade and trend (MISC_SWEEP.md line 119).
  - REVERT r1, the failed new-high/low fade, loses before cost: about -1.4 NQ points a trade gross (ledger 2.38).
  - r38 CHOP-FADE, a 1m range-compression fade: gross about 0.00 points a trade. Its round went 0 of 20
    (BACKTESTING_STACK.md line 1887; tools/r16_results/r38_scalpers.log lines 18-21).
  - MISC 10 o'clock fade: gross -2.2 to -4.6 points a trade (MISC_SWEEP.md line 76).
  - VWAP trend pullback: PF 1.01 (MISC_SWEEP.md line 104).
  - Hourly mean reversion: pooled PF 1.004 (MISC_SWEEP.md lines 227-228).
  - ORB failed-break fade: PF 0.74-0.93 (ORB.md lines 967-973).
  - "Chop is not identifiable before entry" (ORB.md line 980).
  - Intraday continuation beats reversion in both windows (ledger 2.5).
  - The only positive house reversal gross is REVERT r2's +0.2 / +0.5 NQ points (ledger 2.41). It runs on the
    post-close auction clock, so it is an analogy, not a measurement of this trade.
- **Against it, stated now.** BALANCE's stop is #304's entry when #304 is eligible (gates open, k <= m-2).
  - BALANCE is short the afternoon break that the crown is long. It is NOT an earner by construction.
  - It loses on whipsaw-break days that #304 also loses on: first breaks in multi-break sessions lose about $205 a
    trade (ledger 2.82).
- **The band was chosen in sample.** Lookback 40 and multipliers 0.75 / 1.5 set both the classifier and the stop. They
  were picked on #231's and #304's NQ returns over 2010-06-07 .. 2025-02-10 (NOISE.md lines 1644 and 2211-2215; line
  598). That covers all of EARLY and WF except 2025-02-11 .. 06-29. Only the stretch threshold is free of a return.
  Stage A, bar 12 (EARLY) included, is read as an in-sample screen for the band. The Auto-Validate lockbox is the
  first clean read of anything that depends on it.
  - Three REPORTED twins of B1 use band settings fit on no return (lookback 20 / 40 / 60, multipliers 1.0 / 1.0). They
    print beside B1 with no verdict, and a WF net sign flip on any twin makes a pass 'fragile' (section 8; AMENDMENT 0
    item 4).

## 2. Map placement and prior
- **Map.** Earner route only (docs/MDL_MAP_R1.md lines 5 and 10; SCOPE_DISC lines 58-63 and row 2).
  - The binding window is R: the 762 days of L's 45 drawdown episodes, where L = #463 + 0.264 x RES (ledger 2.79).
  - #463's 460 drawdown days and its worst drawdown, 2020-03-03 .. 2020-03-27 inclusive ($44,849; the peak day
    2020-03-02 excluded, C:\EdgeLog\_anatomy_cache\q19\episodes.csv row 1), are reported, not barred.
- **Prior.** Judgment, written before any return:
  - own WF ROC @ $30k between -8 and 8, median -1;
  - P(>= 5) 10%, P(>= 15) under 2%;
  - R-day sum median about $0, with P(above the family null's 95th percentile) about 5%;
  - prior t median about 0;
  - P(Stage A pass) about 4%.
- **Gross needed.** Well above 0.533 NQ points a trade (1.20 on MNQ). The best house-measured reversal is +0.2 to +0.5
  points (ledger 2.41).

## 3. Rules (frozen)

### 3.1 Data
- **NQ master.** NQ 5m RTH no-adjust master, registry id 37 (augur_uploads\NOADJ_NQ_5m_RTH.csv, source db_noadj_rth).
  - Load: `load_master_arrays(find_master("NQ","5m","rth","db_noadj_rth"), date_from="2010-06-07", date_to="2025-06-29")`.
  - Assert the last bar is on or before 2025-06-29, or abort with "a bar after 2025-06-29 is in memory - abort"
    (tools/halfhour_r1_stageA.py line 47). Nothing later is in memory.
  - NOISE bands never run on an ADJ master (ledger 2.71).
- **ES master.** `load_master_arrays(find_master("ES","5m","rth","db_noadj_rth"), date_from="2010-06-07",
  date_to="2025-06-29")`, with the same abort on a later bar. The file runs to 2026-10-05.
- **Every other input is cut to dates on or before 2025-06-29 on load, before any use,** and the driver asserts each
  cut. That covers the four crown trade files (#304's is NOISE422), TTM's ES 30m master (section 7), R's day file, the
  line L, the RES file and open_bars.csv (pulled to 2026-09-30, tools/rocfrontier/r5_nqbrd.py line 110; cut to
  day <= 2025-06-29 before DISP is computed). No lockbox row is read.
- **Bar stamps.** Bars are START-stamped in US/Eastern: augur_engine/data.py line 170 converts the UTC epoch.
  - A full session runs 09:30 .. 15:55, 78 bars. A bar stamped t closes at t + 5 minutes.
  - "The 11:55 bar" therefore closes at 12:00.
- **Session and position.** A session is one ET date (data.py line 177). Bar position k = 0, 1, 2, ... inside it
  (NOISE_1_0.py `_session_bounds`, lines 330-338).
  - Band and VWAP arrays are POSITIONAL, exactly as in the engine.
  - Clock rules (the noon cut and the entry window) use the bar's STAMP.
- **Trading sessions** are the sessions that contain a bar stamped 15:55, minus warm-up and roll sessions.
  - Half days, the 14 short 2010-12 days, 2020-02-28 (18 bars) and 2020-06-30 (9 bars) are never traded.
  - **Warm-up:** the first 40 sessions of the array (session index si < 40, NOISE_1_0.py line 570) are neither trading
    sessions nor BALANCE days in any count. Asserted.
  - **Roll sessions:** the first master session whose first bar is stamped after a switch_et in
    tools/data/rolls_NQ.csv (rolls_ES.csv for ES), rows of kind other than `not_a_roll`. prev_close crosses the
    contract there on the no-adjust master (line 777), so one band sits out by the roll spread (+114 to +297 NQ points
    from 2022-12 to 2025-06). Frozen choice: they are never traded. NQ has 36 switches in WF.
  - All of these still feed sigma and prev_close for later sessions exactly as in the engine, for parity with #304.
- **Stretches.**
  - WF = sessions dated 2016-07-01 .. 2025-06-29.
  - EARLY = 2010-06-07 .. 2016-06-30. Its first 40 sessions are warm-up, so the first possible trade is in 2010-08.
- **ES transfer report.** ES 5m RTH no-adjust master, registry id 33 (augur_uploads\NOADJ_ES_5m_RTH.csv).
  - Same rules, $50 a point, cost 0.363 points a round trip (api/book_shadow.py line 40).
  - 2020-02-28 and 2020-06-30 are skipped, as DDW did (tools/rocfrontier/PREREG_DDW_R1.txt, pre-data addendum 1). Both
    lack a 15:55 bar, so the trading-session rule already drops them.

### 3.2 The #304 band (augur_strategies/NOISE_1_0.py, with #304's settings)
- **Settings.** The `_FROZEN` dict in augur_strategies/NOISE_1_8_CT304.py lines 82-89: lookback 40, band_mult_long
  0.75, band_mult_short 1.5.
  - Never use NOISE_1_0's signature defaults (14, 1.5 / 1.5).
  - Never use NOISE_1_1_NBHD's `_CHAMP`, which is #243.
- **AD[s,k]** = |C[s,k] - O[s,0]| / O[s,0]: the move from the session's 09:30 open to bar k's close.
- **sigma[s,k]** = nanmean of AD over the 40 sessions immediately before s, at the same position k (`_sigma_matrix`,
  lines 341-353). Today is excluded.
- **Anchors.**
  - prev_close = the close of the previous session's last bar in the array (line 777).
  - ref_hi = max(O[s,0], prev_close); ref_lo = min(O[s,0], prev_close).
- **Bands** (lines 576-581):
  - UB[k] = ref_hi x (1 + 0.75 x sigma[s,k]);
  - LB[k] = ref_lo x (1 - 1.5 x sigma[s,k]).
- **Warm-up.** There are no bands, and no BALANCE trade, in the first 40 sessions of the array (line 570; section 3.1).
- **Re-typed, then checked.** NOISE_1_0 exposes only `_session_bounds` and `_sigma_matrix`; the driver imports those.
  prev_close, ref_hi / ref_lo, UB / LB (lines 570-581, 777) and VWAP (lines 600-606) are inline in `run_backtest`, so
  the driver re-types them from those lines. Two parity asserts run before anything else (section 4):
  - against `return_decisions`: at every WF #304 entry-decision and exit-decision bar, the driver's UB[k], LB[k] and
    V[k] equal the record's `upper`, `lower` and `vwap` within 1e-9 points;
  - the #304-eligible first break equals #304's first entry bar on every session loaded.

### 3.3 Raw break
- A raw break at bar k means k >= 1 and either C[k] > UB[k] or C[k] < LB[k].
  - The inequalities are strict, as in #304's STEP D (lines 747-766). A NaN band never breaks.
  - k = 0, the 09:30 bar, never counts, as in #304.
- **Raw, not #304-eligible.** #304's entry rules are dropped here: the vol skip at the 95th percentile, skip_bot_short,
  flat-only, and no entry on the last bar (STEP D, `1 <= k <= m - 2`, line 748).
  - Reason: the mechanism is price leaving the noise area. A session whose price closed beyond a band is a trend day,
    even when #304's rules kept #304 out of it.
  - **For MANAGER's sign-off at GO:** this is a reading. The accepted scope's row 2 says "#304 core band break (5m
    close)" but also "whether the crown's own trigger has fired by noon". The raw break is the one classifier; it was
    chosen after the session counts in section 4 were seen, and before any return.
  - The #304-eligible version (= no #304 trade signalled by 11:55) prints as a count crosswalk only. It is never a cell.

### 3.4 The classifier (one)
- **BALANCE day** = a trading session with no raw break on any bar with k >= 1 and stamp <= 11:55 (bars closed by 12:00).
- **It is known at 12:00:00 from data closed by 12:00.**
  - sigma and prev_close use prior sessions only.
  - The reference uses today's 09:30 open.
  - Each test uses only its own bar's close.
- **After noon, the day stays open only until its first raw break,** on either band, at any bar stamped 12:00 or later.
  - From that bar's close on, no new entry is taken that session.
  - An open position is handled by the stop rule.

### 3.5 VWAP
- **NOISE's own VWAP** (NOISE_1_0.py lines 600-606):
  - typical price TP[k] = (H[k] + L[k] + C[k]) / 3;
  - V[k] = sum over j = 0..k of TP[j] x Vol[j], divided by the sum over j = 0..k of Vol[j];
  - Vol is the master's volume column.
- It is anchored at the 09:30 bar and reset each session. V[k] includes bar k and is known at bar k's close.
- If the cumulative volume is 0, V[k] is NaN, and that bar gives no signal and no target test.

### 3.6 Stretch and the two cells
- **Stretch.** At bar k's close, with C = C[k] and V = V[k]:
  - **above VWAP (C > V):** E = UB[k] and x = (C - V) / (UB[k] - V);
  - **below VWAP (C < V):** E = LB[k] and x = (V - C) / (V - LB[k]);
  - there is no signal if C = V, if the denominator is <= 0, or if any input is NaN.
- **Room.** D = |E - V|, in points. At the signal close, the reward to VWAP is x·D and the risk to the edge is (1 - x)·D.
  These are nominal.
- **Cells.**
  - **B1 (PRIMARY): signal when x >= 1/2.**
  - **B2: signal when x >= 2/3.**
  - With no raw break at bar k, x <= 1.
- **Why these two values (band geometry only; no return has been seen):**
  - x = 1/2 is the midpoint between VWAP and the band edge. It is the shallowest entry where the nominal reward to VWAP
    is at least the nominal risk to the edge (1:1). Below 1/2, the entry is closer to VWAP than to the edge: no stretch.
  - x = 2/3 is nominal reward twice the risk: the house's own pre-registered 2R convention (tools/r38_scalpers.py lines
    14-19, the IGNITION and BOX-BREAK exits).
  - No null hit rate is claimed. The edge is live (sigma varies by position), VWAP moves and includes the current bar,
    tests are on closes with next-open fills, and stops overshoot. So 1 - x is not the driftless hit rate. The hit rate
    prints only beside realised R by exit type (section 9) and is never compared with 1 - x.
  - Not deeper than 2/3. At 3/4 and beyond, under a quarter of the room is left as stop. The entry then sits against an
    imminent #304 trigger, and the overshoot of a close-based stop would swamp the nominal risk.
    - This limits the Stage A cells only. MANAGER #40 puts 9/12 = 3/4 in the declared Auto-Validate space (section 11;
      AMENDMENT 0 item 6).
  - Where VWAP sits at the reference, x = 1/2 is about 0.375 sigma x ref above VWAP for shorts and 0.75 sigma x ref
    below for longs. x = 2/3 is 0.5 and 1.0 sigma x ref.
  - The bands are asymmetric (0.75 up, 1.5 down), so short fades get about half the room of long fades. Longs and
    shorts are reported apart.

### 3.7 Trade
- **Side.** Fade toward VWAP: short when C > V, long when C < V.
- **Signal bar.** All of the following hold:
  - the stamp is 11:55 .. 15:25;
  - the BALANCE day is still open at bar k (no raw break on any bar from k = 1 through k);
  - the trade is flat at the bar's close (no position and no exit pending);
  - x >= the cell's threshold.
- **Entry.** At the open of the next bar in the session.
  - The first possible fill is 12:00 (signal: the 11:55 bar's close, the first moment the classifier is known).
  - The last possible fill is 15:30 (signal: the 15:25 bar).
  - Reason for the last time: every trade gets at least 30 minutes to reach VWAP. The closing half-hour is the
    closing-flow clock (ledger 2.14 and 2.41; SCOPE_DISC line 156), which this mechanism does not claim.
- **Size, points and cost.**
  - 1 NQ contract at $20 a point. Gross points = side x (exit price - entry price).
  - House cost is 0.533 points a round trip ($10.66), charged once per trade (BOOK.md line 72; api/book_shadow.py
    line 42). Net $ = 20 x gross points - 10.66.
  - Stress cost = +2 ticks a side = +1.0 point = 1.533 points a round trip.
- **Exits.** Tested at every bar close from the fill bar's close onward, in this order:
  1. **STOP = any raw break, LIVE.** C[j] > UB[j] or C[j] < LB[j] (section 3.3), on either band.
     - The band is read at bar j (position j), not frozen at entry. The exit fills at the next bar's open.
     - On the edge used at entry (short: C[j] > UB[j]; long: C[j] < LB[j]) the exit reason is STOP.
     - On the opposite edge the reason is TARGET if C[j] is at or through V[j], else OPP-BREAK. OPP-BREAK can happen
       only when V sits outside [LB, UB] (VWAP includes the 09:30 bar and bar highs and lows). Such exits are counted.
     - So BALANCE is always flat at the open where #304 fills, and the zero-overlap assertion (section 7) holds by
       construction.
  2. **TARGET.**
     - Short: C[j] <= V[j]. Long: C[j] >= V[j]. The exit fills at the next bar's open.
     - This is #304's own VWAP-exit convention (STEP C, lines 708-737): close-based, with a next-open fill.
     - There are no touch fills and no limit-queue assumption. The same-bar VWAP leak that compromised VWAP_FADE
       (BACKTESTING_STACK.md line 2334) cannot occur.
     - If a bar meets both STOP and TARGET (a degenerate band and VWAP geometry), STOP wins.
  3. **FLAT** at the close of the 15:55 bar, the session's last bar (the 16:00 print), as #304's STEP E (lines
     768-775).
     - A stop or target signalled at the 15:55 bar's close also exits at that close.
     - Trade files stamp that exit 15:55 (the convention of C:\EdgeLog\book_legs\NOISE422_raw_trades.csv).
  - There is no intrabar stop and no other exit. Overshoot past the band and any open gap are paid as they come.
- **Positions and re-entry.**
  - One position at a time.
  - After a TARGET exit, a new signal may come at any later bar close while flat. The earliest is the close of the bar
    whose open filled the exit.
  - After a STOP, an OPP-BREAK, or a TARGET on an opposite-band close, the day has had a raw break, so there are no
    more trades that session.
  - There is no numeric cap on trades a session. The distribution, and P&L by trade order, are reported.
- **Dates.** Every trade opens and closes inside one session and is dated by it.
- **Initial risk (for R reports only).** R0 = |E_k - entry price|, where E_k is the stop-side band at the signal bar.
  - Realised R = gross points / R0.
  - A trade filled at or beyond E_k (R0 <= 0, or the fill outside the band) keeps its P&L but is left out of R reports
    and counted.

### 3.8 ROC @ $30k and the day index
- **Daily series x.** The leg's net $ per session at 1 NQ, reindexed onto #463's WF day index with 0 on days with no
  trade.
  - The index comes from `api.book_shadow.book463_valued_daily("2010-06-07", "2025-06-29")`, cut to 2016-07-01 ..
    2025-06-29: 2,626 rows, including 280 UTC-Sunday rows.
  - Parity is asserted first: ROC 93.81 +/- 0.05 and Sortino 3.816 +/- 0.005 (tools/halfhour_r1_stageA.py lines
    116-122).
  - An RTH session's ET date equals its UTC date. Assert that every BALANCE session date is in the index.
- **own ROC @ $30k** = 30 x MAR = 30 x (net / years) / max drawdown (tools/rocfrontier/r11_risk.py `stats`, lines
  278-293; memory edgelog-frontier-yardstick-roc30.md).
  - The drawdown is valued daily, with the peak starting at 0.
  - years = (last row - first row).days / 365.25 = 3,285 / 365.25 = 8.994, computed, not typed
    (tools/halfhour_r1_stageA.py line 277). Sortino is computed as in r11.
- **EARLY** uses the same formula on its own index: every NQ trading session 2010-06-07 .. 2016-06-30.
- **July-June years.** Y = 2016 .. 2024: rows with Y-07-01 <= date < (Y+1)-07-01 (tools/halfhour_r1_stageA.py line 298).

## 4. Counts FIRST (before any return): `--counts`
Nothing in this mode reads a BALANCE P&L or runs a BALANCE exit.
- **Parity, asserted.** NOISE_1_0 is re-run with `_FROZEN` on master 37 (2010-06-07 .. 2025-06-29), with
  `return_trades` and `return_decisions`.
  - Its trades must equal the WF rows of C:\EdgeLog\book_legs\NOISE422_raw_trades.csv (entry, exit and side) on all
    2,797 trades with signal dates 2016-07-01 .. 2025-06-29 (ledger 2.82). Signal bar = the bar before the fill bar in
    the array.
  - The band and VWAP parity of section 3.2 is asserted here too. Any mismatch aborts.
- **(i) Sessions per July-June year,** for the 9 WF years and the EARLY years 2010-11 .. 2015-16:
  - trading sessions, and the warm-up and roll sessions left out;
  - BALANCE days, and BALANCE-labelled roll sessions (not traded) with their first signals;
  - #304-eligible no-break days (crosswalk);
  - per cell: sessions with a FIRST signal, and first signals by side. A first signal does not depend on any exit.
  - Total trades, re-entries and trades per session are NOT printed here. They reveal a lower bound on target hits
    (re-entry follows only a TARGET exit), so they print in the real run, where bar 6 is tested.
- **Seen while drafting.** A read-only parity check, no P&L read: scratchpad band_parity.py, master 37 loaded to
  2026-09-16 for the full trade file.
  - The classifier was computed in memory on every session to 2026-09-16, lockbox included. Only WF-session counts
    were printed. No BALANCE signal, trade or P&L exists for any date.
  - **SUPERSEDED drafting counts (MANAGER #40 item 7; AMENDMENT 0):** across all 2,318 WF sessions (half days
    included), 914 had no raw break by 12:00, about 102 a year. 1,078 had no #304-eligible break. These are POSITIONAL
    (noon = k <= 29) and from an uncut load. On 2020-03-09, 03-12 and 03-16 (missing early bars) k = 29 is the 12:00
    or 12:05 bar, which is past the cut.
  - The eligible-break rebuild matched #304's first entry bar on 2,318 of 2,318 sessions.
  - **The `--counts` stamp-based reprint, on the cut load and trading sessions only, supersedes these figures
    everywhere they are quoted.** Only the reprint is cited after it exists.
  - Consequence, stated before any return on the superseded drafting count: the >= 50 trades a year bar needs a signal
    on about half of BALANCE days, or re-entries. B2 is the cell at risk. The bar stays (MANAGER #40 item 5); a cell
    that fails on count alone and clears the other 12 bars is a RUNBOARD research row, not a pass (section 8).
- **(ii) The three-way split of WF BALANCE days.** Source: #304's held WF trade list (NOISE422_raw_trades.csv, unit $ =
  pnl_usd / size).
  - **QUIET:** no #304 trade that session.
  - **BREAK-WIN:** the session's FIRST #304 trade has unit $ > 0. Its signal bar is 12:00 or later by construction; this
    is asserted.
  - **BREAK-LOSS:** the session's first #304 trade has unit $ <= 0.
  - **Sub-counts printed:**
    - QUIET split three ways: no raw break all day; a raw break that #304's gates blocked (vol skip, skip_bot_short);
      a raw break only on the last bar (k = m-1, which STEP D never enters). Asserted to sum to QUIET.
    - BREAK-LOSS split by #304's exit (VWAP, bandwidth stop, 15:55 flat), from the engine's own decision records
      (NOISE_1_0.py lines 803-824).
  - **The scope's three groups** (SCOPE_DISC line 223) are sub-rows of these: "no NOISE break all day" = QUIET with no
    raw break all day; "a later break that wins" = BREAK-WIN; "a later break that loses at VWAP" = BREAK-LOSS with a
    VWAP exit. They print as rows wherever the groups print.
  - Counts per group and year are printed, with #304's unit net per group (a #304 figure, not a BALANCE one).
- **Co-loss exposure, before any return** (MANAGER #39: "the three-way split ... with the co-loss share BEFORE any
  return"). Per group and scope sub-row, on WF BALANCE days:
  - days, and days in R;
  - L's net and L's losing dollars (the sum of L's daily P&L where < 0; C:\EdgeLog\_anatomy_cache\q19\line.csv, column
    `line`);
  - #304's losing unit dollars.
  - Plus one share: L's losing dollars on BREAK-LOSS days / L's losing dollars on all WF BALANCE days.
  - These are #304 and L figures only. The BALANCE-side shares below need BALANCE P&L and wait for the run. MANAGER
    confirms this reading of "BEFORE any return" at GO.
- **Defined now, printed after the real run (per cell):**
  - BALANCE's trades, net and PF in each of QUIET / BREAK-WIN / BREAK-LOSS and in each sub-row.
  - **Co-loss share vs #304** = the sum of |session net| over BALANCE losing sessions (session net < 0 at house cost)
    that are BREAK-LOSS days, divided by the sum of |session net| over all BALANCE losing sessions. Printed in dollars
    and in counts.
  - **Co-loss share vs L** = the same ratio, with "L's daily P&L < 0 that day" in place of BREAK-LOSS (L from
    C:\EdgeLog\_anatomy_cache\q19\line.csv, column `line`).
  - Both co-loss shares print on all WF days and inside R's 762 days, beside the R-day sum.

## 5. Power line (before any real-direction run): `--power`
- **Coin-flip leg.** The PRIMARY B1's real WF trade schedule (its entry and exit bars, exactly as the rules produce
  them).
  - Each trade's side is replaced by `np.random.default_rng(20261006).choice([-1, 1], size=n)`, in trade order.
  - Net $ = coin x (exit - entry) x 20 - 10.66.
- **Sizes.**
  - c = 0.25 x SD(#463 daily) / SD(coin leg daily), both over WF rows 2016-07-01 .. 2018-06-30 with ddof 1
    (tools/halfhour_r1_stageA.py lines 135-144; SCOPE_DISC lines 200-202).
  - The $30k-own-DD twin = 30,000 / the coin leg's own WF max drawdown.
- **Lines.** `tools/power_line.py` `power_line(cand, twin, years, block=20, draws=1000, seed=20261005)`, which never
  prints a lead.
  - Cand = #463 + size x coin leg, twin = #463, at c and at the $30k twin: the house pair (tools/halfhour_r1_stageA.py
    lines 156-164).
  - The same at c with L as the base (cand = L + c x coin leg, twin = L).
  - Each prints the SD, the 5% line (minimum detectable) and the 80% line (four in five).
- **Also printed in this mode, before the cell:** the family null's 95th percentiles (section 6) of max t, max R-sum
  and max own ROC, and the null SD of B1's R-sum.
  - The null flips the signs of real trades' gross, so its distribution does not depend on the real direction.
- **Also run in this mode:** the overlap test (section 7). Its output goes into AMENDMENT 1.
- **Disclosed.** The schedule and the trade sizes in points come from the real rules, so re-entries depend on real
  target exits: the schedule's n and holding times reveal a lower bound on target hits. Only the side is random. This
  is house practice for exits that depend on the path (docs/PREREG_noise_iwm_r1_2026-10-06.md lines 28-29 and 49-53).
- **The real run's stdout reprints the power lines and the null p95s before the cell rows** (NOISE.jsonl #45: "The
  power line is still written first and printed with the result").

## 6. Family null
- **Family.** Both NQ cells, B1 and B2. ES is not in it.
- **Draws.** 1,000 draws from one `np.random.default_rng(20261006)`, made in a fixed order. For draw d = 1 .. 1,000, cell
  B1 then B2: coins = `rng.choice([-1, 1], size=n_cell)`.
  - Trade net $ = coin x gross $ - 10.66.
  - Coins are independent across cells. That is conservative: the max of two independent cells sits at least as high as
    the max of two linked ones.
- **What it keeps and removes.** It keeps every entry, exit, holding time, trade density, the clock and the cost. It
  removes only the fade direction ("a coin-flip side on the real schedule", SCOPE_DISC line 226).
- **Statistics per draw and cell** (definitions in section 8): own ROC @ $30k, t, and the R-sum. The family statistic
  is the MAX across the 2 cells.
  - The p95 is `numpy.percentile(..., 95)` over the 1,000 maxima.
- **Use.** Bars 4 and 8 bind on the t and R-sum p95s. The ROC p95 prints as a report.

## 7. Overlap test (before any real-direction run; run in `--power`): positions only
- **Crowns:**
  - NOISE #382 (C:\EdgeLog\book_legs\NOISE382_raw_trades.csv);
  - NOISE #422 (NOISE422_raw_trades.csv, with the same timing);
  - ORB #314 (ORB314_raw_trades.csv);
  - ENGU-Q #335 (ENGUQ335_raw_trades.csv, 1m ETH; only RTH minutes count);
  - TTM #459 at 3 ES: TTMSQZ_3_0_ES30SSOF2 with its BOOK463_LEGS params (api/book_shadow.py lines 29-43) through
    `augur_engine.engine.run_backtest(..., return_trades=True)` on the ES 30m `db_adj_rth` master, date_to 2025-06-29,
    as tools/halfhour_r1_stageA.py lines 225-230 do for the NQ legs. Entry and exit bar indices map to ET stamps
    through the master's index. (`augur_engine.book._leg_trades` returns exit days and dollars only, so it is not used.)
- **Time zones.** NOISE files are naive US/Eastern (README_ml_legs_NOISE.md line 37; stamps run 09:30-15:55; asserted).
  ORB and ENGU-Q stamps carry offsets; they are converted with tz_convert("US/Eastern") then tz_localize(None) before
  any join.
- **Held interval** = the half-open ET range [entry fill time, exit fill time). A clock minute t is held if t is in it.
  - BALANCE and the NOISE files: the fill time is the fill bar's stamp (next-open fills and #304's intrabar stops); an
    exit stamped 15:55 is the 15:55 bar's close, so it ends at 16:00.
  - ORB #314 and ENGU-Q #335: the exit stamp as written; an ORB exit stamped 15:55 ends at 16:00.
  - TTM: [stamp(e0), stamp(e1) + 30 minutes). The whole exit bar counts as held; this can only overstate TTM overlap.
- **RES, before the run.** Per cell: RES's sum and its losing dollars (resmom_cells_daily_wf.csv, column RES) on the
  cell's first-signal sessions, the share of RES's WF losing dollars that falls on them, and the share of WF days they
  are.
- **Per crown, on B1's and B2's WF schedules** (positions held by clock minute, 09:30-16:00 ET):
  - the share of BALANCE trade sessions that are CROWN-FLAT days (the crown holds no position at any RTH minute), and
    the share that are flat for all five crowns at once;
  - the share of BALANCE's held minutes on which the crown also holds a position;
  - of those minutes, the share on the SAME side.
- **#304 by construction.** #304 enters only after a raw break; any raw break exits BALANCE at the same open (3.7) and
  ends its day. Under the half-open interval, held overlap with NOISE #382/#422 must be 0. This is asserted; a non-zero
  value is a bug. A unit test covers a synthetic stop-then-#304-entry session.
- **After the run:** BALANCE's net on each crown's flat days and on all-flat days.

## 8. Stage A bars (earner route ONLY; WF unless named; a cell passes only if all 13 hold)
Statistics are at 1 NQ and house cost unless stated.
1. **Own ROC.** Own WF ROC @ $30k >= 5.
2. **R-sum.** The leg's sum over R's 762 days > 0.
   - R = rows with `in_R` True in C:\EdgeLog\_anatomy_cache\q19\residual_days.csv (sha256 bfe64d87...; L's 45 house-rule
     episodes, ledger 2.79, BOOK.md 10ab lines 1268-1293).
3. **R-sum without its 3 best days.** That sum is still > 0 with the leg's 3 largest daily P&Ls on R days removed.
4. **R-sum vs null.** The R-sum is above the family null's p95 of the max R-sum.
5. **PF >= 1.05.** PF = the sum of positive trade net $ divided by |the sum of negative trade net $|.
6. **Trades.** >= 100 WF trades, and >= 50 a year on average: n / years >= 50 (years from section 3.8), as in
   tools/halfhour_r1_stageA.py `standalone()`. Per-year counts, total trades, re-entries and trades per session print
   here, in the real run. This bar stays (MANAGER #40 item 5); a fail on count alone is handled under the verdict.
7. **Years.** At least 6 of the 9 July-June years have net > 0.
8. **t.** t >= 2.0 AND above the family null's p95 of the max t.
   - t = mean / (SD / sqrt(N)), with ddof 1, over the session nets of the N WF sessions with at least one trade.
9. **Stress cost.** Net > 0 at stress cost (1.533 points a round trip).
10. **Best day and best trade.** Net > 0 without its best day (the largest daily P&L), and net > 0 without its best trade.
11. **No crash window.** Net > 0 without the days 2020-02-15 .. 2020-04-30, inclusive. No-2022 (calendar 2022 removed)
    is reported.
12. **EARLY.** Net > 0 over 2010-06-07 .. 2016-06-30 at house cost.
13. **Neighbour.** The other cell's WF net > 0 at house cost.

- **Verdict.** Stage A PASSES if at least one cell clears bars 1-13.
  - B1 goes forward if it passes; otherwise B2 does.
  - The binding route is the scope's R route as accepted by MANAGER #39. For this lane it supersedes HALFHOUR
    amendment 1's worst-drawdown route (docs/PREREG_halfhour_r1_2026-10-05.md lines 114-118).
  - **'Fragile' (MANAGER #40 item 4).** If B1's WF net sign flips on any of the three band twins below (one WF net is
    above 0 and the other is not, at 1 NQ and house cost), the pass is written 'fragile'. Only the Auto-Validate
    lockbox can clear it (section 11); no Stage A number can.
  - **Count-only fail (MANAGER #40 item 5).** A cell that fails bar 6 alone and clears the other 12 bars is a RESEARCH
    ROW on the RUNBOARD (as TTM r24), not a pass, with no variants (section 11).
- **Band twins of B1 (MANAGER #40 item 4; reports, never bars, never cells, not in the family null).** Three twins
  with band settings not fit on any return: lookback / band_mult_long / band_mult_short = (20, 1.0 / 1.0),
  (40, 1.0 / 1.0) and (60, 1.0 / 1.0).
  - Each twin's bands are computed the same way as #304's (section 3.2), with that twin's settings in place of
    `_FROZEN`'s: sigma over the `lookback` sessions before s, UB = ref_hi x (1 + 1.0 x sigma), LB = ref_lo x
    (1 - 1.0 x sigma), and no band while si < lookback (NOISE_1_0.py line 570).
  - Everything else is B1's: the twin's own band drives the raw break, the BALANCE-day classifier, the stretch
    (x >= 1/2), entry, stop and exits (sections 3.3-3.7), on the same trading sessions, at 1 NQ and house cost.
  - Each twin prints B1's section 8 statistics as one row beside B1's, with no bar marks and no verdict.
- **Reports beside the verdict (never bars):**
  - #463's 460 drawdown days (C:\EdgeLog\_anatomy_cache\q19\episodes.csv, 28 episodes);
  - the HALFHOUR form: the leg's P&L in #463's worst WF drawdown, 2020-03-03 .. 2020-03-27 inclusive, with and without
    its 3 best days there, and net without calendar 2020;
  - the R-sum without its best R episode (BOOK.md 10ab line 1292);
  - **drift control, beside bars 4 and 8:** the long / short share of trades and of held minutes, and the gross minus
    each trade's side x the mean NQ move between the same fill stamps over all WF trading sessions (as a fraction of
    price, times the trade's entry price).
- **Book-add REPORT (house line #45; never a bar).** MANAGER, NOISE.jsonl #45; SCOPE_DISC lines 200-202.
  - c = 0.25 x SD(#463 daily) / SD(x), both over WF rows 2016-07-01 .. 2018-06-30, ddof 1.
  - Rows at c, 0.5c, 2c and the $30k-own-DD twin:
    - #463 + size x x against 93.81 / 3.816, with the reference bars 98.50 / 3.816 / p5 > 0
      (tools/rocfrontier/PREREG_MDL_R1.txt line 19);
    - incremental L + size x x against 120.82 / 3.916, with L's parity asserted (|ROC - 120.82| < 0.05).
  - **Judged at c on the incremental row** (SCOPE_DISC lines 200-202; MANAGER #35 item 4): L + c x x against L, with
    ROC >= 1.05 x 120.82 = 126.86, Sortino >= 3.916 and a paired-bootstrap p5 of the lead > 0 (the house 1.05 x base
    rule of PREREG_MDL_R1.txt line 19, applied to L). All other rows are reports.
  - The paired bootstrap p5 of the lead uses `PL.stationary_indices(n, 1000, 20, default_rng(20261005))`.
  - It decides only whether a forward BOOK shadow line is also opened, through MANAGER's #70 gate (standing-order
    addendum 2 item 4, MANAGER #35).

## 9. Diagnostics (printed with the verdict; never bars)
All per cell, on NQ; ES gets the same rows as a transfer report.
- **Event-time path.** Mean R by minute from entry, 0 .. +390, in 5-minute steps.
  - Each trade is marked at each bar close from the fill (side x (close - entry) / R0) and frozen at its realised R
    after exit.
  - Rows past +240 repeat the final value: no afternoon trade can hold longer.
- **Regime halves.** 2016-07-01 .. 2021-12-31 and 2022-01-01 .. 2025-06-29.
- **Cost curve.** Net at gross 0, house 0.533, +1 tick a side (1.033), MNQ 1.20 points per NQ-equivalent
  (tools/rocfrontier/PREREG_RISK_R1.txt line 105) and +2 ticks a side (1.533). Also the break-even cost = mean gross
  points a trade.
- **Per-year rows.** For each July-June year: trades, net, PF and long/short counts.
- **Episode rows.** P&L in each of R's 45 episodes (C:\EdgeLog\_anatomy_cache\q19\a2.json, `line_episodes`) and in each
  of #463's 28 episodes.
- **Correlations.** Daily correlation with each #463 leg (ORB, ENGU-Q, TTM, NOISE, per leg from the book build) and
  with RES (C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf.csv, column RES), on all WF days and on
  R's days.
- **Long and short apart.** Trades, net, PF and mean realised R.
- **Concentration.** The top-10 share of net (trades, and days). Net without the best day and without the best trade.
- **Exits.** Exit-reason shares and P&L (target, stop, opp-break, flat), with the hit rate and mean realised R per exit
  type. The mean realised R of stops shows the overshoot past the nominal -1.
- **Trades per session.** The distribution, and net by trade order (1st, 2nd, 3rd+).
- **Day groups.** P&L in the three day groups and the two co-loss shares (section 4).
- **Room.** P&L by tercile of D at the signal (tercile cut points from the cell's own WF trades). This is a report and
  never a gate (a D gate would be a third cell).
- **VWAP_FADE crosswalk.** The stretch at the signal close in VWAP_FADE's vwsigma units (VWAP_FADE_1_0.py lines
  110-135: sqrt(sum(TP^2 x Vol) / sum(Vol) - VWAP^2), cumulative from 09:30). Printed: the share of BALANCE entries at
  >= 2.0 vwsigma (that file's default) and their net. This is entry-stretch overlap only; fills, target and stop
  differ (section 1).
- **DISPERSE split** (scope rank 10). A reported split, never a cell, and not in the null.
  - DISP = the cross-sectional SD (ddof 1) of Nasdaq-100 members' returns from the 09:30 bar's open to the 09:55 bar's
    close, C:\EdgeLog\alpaca_cache\nqbrd\open_bars.csv (point-in-time members).
  - A day counts only if >= 80% of members have both prices, NQBRD's coverage guard (tools/rocfrontier/r5_nqbrd.py
    `breadth`).
  - Terciles by DISP's percentile among the prior 252 sessions (at least 60 needed, or "unlabelled"). Net per tercile.
- **No-2020 and no-2022 reads.** No-2020 = without 2020-02-15 .. 2020-04-30 inclusive (bar 11; SCOPE_DISC line 320).
  No-2022 = without calendar 2022. Calendar-2020-removed is in the section 8 reports.
- **Data notes.**
  - Roll sessions (section 3.1) are listed per year with their switch, offset and BALANCE label.
  - The 2014-06-12/13 sessions are absent from master 37 (EARLY window). 2014-06-16's prev_close is 2014-06-11's close,
    as in the engine.
  - On 2020-03-02 and 2020-07-01, prev_close is the early last bar of the hole day before (10:55 / 10:10), as in #304.
  - On 2020-03-09, 03-12 and 03-16 (missing early bars) and 2020-03-18 (missing 13:00 / 13:05), position k is not the
    clock slot. Bands stay positional for parity, and the affected trades are listed.
  - Zero-volume bars and sessions with NaN VWAP are counted.

## 10. What could fool us
- **A classifier that peeks.** It does not: sigma, prev_close and the gates use prior sessions, the reference uses the
  09:30 open, and each test uses its own closed bar.
  - The harness test (section 12) perturbs every bar after a cut and asserts that no signal or label before it changes.
- **A VWAP leak.** The target compares a closed bar's close with that bar's VWAP, and the exit fills at the next open.
  No intrabar touch is assumed.
- **Fade luck.** Every fade on file died (section 1), so a positive cell is more likely luck than usual.
  - The null covers both cells. No cell, threshold, time or exit is added after a number exists.
- **Nominal 1:1 and 2:1.** The close-based stop overshoots the band, and the fill is the next open. Realised R is
  reported, and stress cost binds.
- **Room smaller than cost.** On days with small D, the 0.533-point round trip is a large share of the nominal reward
  x·D. The D terciles show it. They are never a gate.
- **A band tuned on returns.** The band was chosen on #231's and #304's returns over EARLY and most of WF (section 1).
  The bias can run either way. Stage A is an in-sample screen for the band; the Auto-Validate lockbox is the first
  clean read. The three band twins of B1 (section 8), at settings fit on no return, print beside B1; a WF net sign flip
  on any of them writes a pass 'fragile'.
- **A rebadged dead fade.** The vwsigma crosswalk shows the entry-stretch overlap with VWAP_FADE 1.0, nothing more.
- **Drift dressed as reversion.** The bands are asymmetric, so the side mix can be lopsided while the null is 50/50.
  The drift control beside bars 4 and 8 (section 8) shows it.
- **A co-loser called an earner.** The R-sum bar binds. The co-loss shares and the three-way split show whether the
  losses sit on #304's own whipsaw days.
- **One crash window.** Bar 11 removes 2020-02-15 .. 04-30. No-2022 is reported.
- **Few BALANCE days.** About 102 a year on the superseded drafting count (section 4; the `--counts` reprint replaces
  it) puts bar 6 at risk. This is known before any return and is not fixed by adding re-entries or cells after a
  number. A fail on count alone is a RUNBOARD research row, not a pass (section 8).
- **Reading a fail as a verdict on the owner's eye.** A fail says only that this proxy of his day-type read does not pay.

## 11. What follows
- **PASS** (at least one cell clears bars 1-13):
  - a plugin built to trade-by-trade harness parity, its file name and family set by the owner via MANAGER (MISC until
    then);
  - then, the same day, a window-pinned Auto-Validate of 900 trials on that file, date_from 2010-06-07 and date_to
    2026-07-16 as HALFHOUR (docs/PREREG_halfhour_r1_2026-10-05.md line 106). MANAGER #40 wrote "window pinned to WF";
    these dates are this draft's and are flagged for MANAGER's confirmation. **Its search is declared now (MANAGER #40
    item 6; AMENDMENT 0), 8 configs, never a pinned file:**
    - the stretch threshold as an int in twelfths: `stretch_12ths`, min 6, max 9, step 1 (x = k/12: 6 = 1/2 = B1,
      7 = 7/12, 8 = 2/3 = B2, 9 = 3/4);
    - the last fill as an int in minutes after 09:30: `last_fill_min`, min 330, max 360, step 30 (330 = 15:00, signal
      bar 14:55; 360 = 15:30, signal bar 15:25, section 3.7's);
    - 4 x 2 = 8 configs. Default = the passing cell's stretch with last fill 15:30;
    - everything else pinned to section 3. Any other knob needs a new prereg. Nothing measured in section 9 (D, DISP,
      side, trade order, hour) may become a knob, gate or range edge; the last-fill knob is MANAGER #40's, declared
      before any number;
    - a test asserts all 8 configs, the passing cell's included, are reachable on the lattice exactly as
      `augur_engine/auto.py` samples an int knob (lines 271-273 and 293-297);
  - its lockbox is the leg's own first look (MANAGER #40) and is veto-only: it can stop the leg, never promote it. It
    is also the only read that can clear a 'fragile' pass (section 8);
  - a RUNBOARD row the same day (tools/runboard_watch.py) and a RESEARCH_LEDGER row.
- **FAIL:**
  - BALANCE is dead, with no variants: no other threshold, classifier, clock, exit, room gate or market.
  - A RESEARCH_LEDGER row in the format of rows 2.72-2.74, and a RUNBOARD research verdict with ROC @ $30k and DD%.
  - **Count-only fail (MANAGER #40 item 5):** if no cell passes and a cell fails bar 6 alone while clearing the other
    12 bars, that cell is a RESEARCH ROW on the RUNBOARD (as TTM r24). It is not a pass: no plugin, no Auto-Validate,
    no variants.
- **Either way** (MANAGER #39):
  - this is a one-prereg exception; this lane takes no second NQ item;
  - the VWAP family stays closed. A PASS opens only this leg's plugin and Auto-Validate, not the family;
  - the ES transfer stays a report. Nothing live or in the adopted book changes without the owner.

## 12. Files the Stage A driver will write (after GO)
- **Code:**
  - `tools/balance_r1_stageA.py`, with modes `--counts`, `--power` and the default real run;
  - `tests/test_balance_r1.py`, covering:
    - band and VWAP parity with NOISE_1_0's decision records;
    - the stretch, the exit order (including OPP-BREAK) and the re-entry rule on synthetic sessions;
    - the no-lookahead perturbation;
    - the noon cut by stamp on a session with missing early bars;
    - warm-up and roll sessions never traded;
    - the held interval and the #304 zero-overlap assertion on a synthetic stop-then-#304-entry session;
    - the Auto-Validate lattice reachability of all 8 declared configs (`stretch_12ths` 6..9 x `last_fill_min` 330 /
      360; section 11);
    - the band twins of B1 built with their own settings (section 8).
- **Stdout:** `tools/r37_results/balance_r1_stageA_counts.txt`, `..._power.txt` and `balance_r1_stageA.txt` (the real
  run).
- **Cache: C:\EdgeLog\_anatomy_cache\balance_r1\**
  - `counts_by_year.csv`;
  - `split3_days.csv` (date, group, #304's first-trade exit reason);
  - `trades_{NQ,ES}_{B1,B2}.csv` (session, signal stamp, fill stamp, exit stamp, side, entry, exit, E, V, D, x, R0, exit
    reason, gross points, net $);
  - `daily_{NQ,ES}_{B1,B2}.csv`;
  - `trades_NQ_B1_twin{20,40,60}.csv` and `daily_NQ_B1_twin{20,40,60}.csv` (the band twins, section 8);
  - `null_maxima.csv` (draw, max ROC, max t, max R-sum);
  - `power.json` and `overlap.csv`;
  - `manifest.json`: the sha256 of every input (both masters, the ES 30m master, the four crown trade files,
    rolls_NQ.csv, rolls_ES.csv, residual_days.csv, line.csv, a2.json, episodes.csv, resmom_cells_daily_wf.csv,
    open_bars.csv) and of this prereg at its GO commit.

## AMENDMENT 1 - --counts and --power output, and how the harness reads this prereg (2026-10-06 ~12:00 MST, before the real run)
Written after `--counts` and `--power` ran and BEFORE the real run. It does not touch sections 3, 6 or 8; the harness
asserts their hash (db495f4d...) on every run. Harness: `tools/balance_r1_stageA.py` (59 synthetic tests,
`tests/test_balance_r1.py`). Full output: `C:\EdgeLog\_anatomy_cache\balance_r1\`.

**Parity and inputs (both modes).**
- BOOK #463 WF 93.81 / 3.816 and L = #463 + 0.264 x RES 120.82 / 3.916, both reproduced; years 8.9938; R = 762 days in
  45 episodes; #463's drawdown days 460 in 28 episodes.
- NOISE #304 (NOISE_1_0 + _FROZEN on master 37): 2,797 of 2,797 WF trades matched NOISE422_raw_trades.csv; band and
  VWAP at 5,594 decision bars, max difference 0; the eligible first break equals #304's first entry on 3,868 of 3,868
  sessions.
- Rolls: 36 WF switches on NQ (and on ES), 36 WF roll sessions never traded.
- Every input is cut to 2025-06-29 (NOISE files drop 344 rows, ORB314 184, ENGUQ335 129 plus 1 trade that exits after
  the cut).

**--counts (no BALANCE exit was run).** These supersede the drafting counts (914 / 1,078) everywhere (AMENDMENT 0 item 7).
- WF: 2,204 trading sessions, 832 BALANCE days (75-111 a year), 18 BALANCE-labelled roll sessions (never traded; 12 with
  a B1 first signal, 9 with a B2 one). EARLY: 1,447 trading sessions, 587 BALANCE days. The #304-eligible crosswalk
  (never a cell) counts 993 WF days.
- Sessions with a FIRST signal, WF: B1 489 (41-65 a year; 191 long, 298 short); B2 326 (24-46 a year). B2 sits under
  the 50-a-year line on first signals alone in every year; re-entries print only in the real run.
- Three-way split of the 832 WF BALANCE days (by #304's held trades): QUIET 689 (662 with no raw break all day, 21
  blocked by #304's gates, 6 broken only on the last bar), BREAK-WIN 82, BREAK-LOSS 61 (21 at VWAP, 6 at the stop, 34
  flat at the close).
- Co-loss exposure, before any BALANCE return: L nets -$301,860 on the 689 QUIET days (206 of R's 762 days fall on
  them) and +$305,459 on BREAK-WIN days; on all 832 BALANCE days L nets -$109,724 and loses $863,702. The one share:
  0.166 of L's losing dollars on BALANCE days falls on BREAK-LOSS days.

**--power (coin-flip sides on B1's real WF schedule: 531 trades).** The schedule's count and holds bound target hits
from below (disclosed in section 5).
- Book-add power lines (reports): #463 + c x coin (x2.716 NQ) - SD of the lead 17.83, 5% line 29.33, 80% line 44.34;
  $30k twin (x2.025) - 14.69 / 24.16 / 36.53; L + c x coin - 17.26 / 28.39 / 42.93.
- Family null (B1 + B2, 1,000 draws, seed 20261006), the p95s the bars use: t 1.739; R-day sum $25,402; own ROC @ $30k
  9.46 (report). Null SD of B1's R-sum $14,885.
- Overlap, B1 (held minutes, half-open): NOISE #382 / #422 0 minutes (asserted, by construction); ORB #314 0.446 of
  B1's held minutes (same side 0.227); ENGU-Q #335 0.806 (same side 0.320); TTM #459 0.067. All five crowns flat on
  0.027 of WF days. B2 alike (ORB 0.444, ENGU-Q 0.783).
- RES on B1 first-signal sessions: 489 sessions (0.186 of WF days) carry 0.205 of RES's WF losing dollars.

**How the harness reads this prereg (disclosures; no rule changed).**
1. Besides `_session_bounds` and `_sigma_matrix` (section 3.2), it imports NOISE_1_0's `_vol_percentile` and
   `_daytype_pos`; they feed only the #304-eligible crosswalk and the QUIET sub-split, never a band, label or trade.
2. A BALANCE hold ends at its real fill time: an exit signalled on the 15:50 bar fills at the 15:55 open, so the hold
   ends at 15:55; only an exit at the 15:55 bar's close ends at 16:00. Read literally, section 7 would add 5 minutes of
   NOISE overlap to a 15:50 break and trip the zero-overlap assertion; tested.
3. Crown files are cut on entry AND exit (a trade that exits after 2025-06-29 is dropped and counted).
4. A fill exactly at E counts as beyond the band; such trades stay in P&L and are left out of every R figure.
5. "#304's losing unit dollars" are summed at session level; BREAK-WIN / BREAK-LOSS use #304's FIRST trade of the day.
6. ES: there is no ES #304 crown file, so the ES day groups use NOISE_1_0 with #304's settings on ES (unit $ = 50 x
   points - 50 x 0.363); ES stress cost = 0.363 + 1.0 = 1.363 points; ES rows use their own cost ladder.
7. 'Fragile' is applied to whichever cell passes; each twin trades on B1's trading sessions minus its own warm-up
   (twin60 also skips sessions 40-59).
8. The real run aborts unless `--power` wrote `power.json`, and asserts that its recomputed power lines and null p95s
   equal that file.
9. DISPERSE ranks each day among the prior 252 sessions whose DISP passed the coverage guard (at least 60 needed).
10. Hit rate per exit type = gross points above 0, before cost.
