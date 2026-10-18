# PREREG: CTXSHORT r2 - the owner's CBD / ENGD shorts, taken only while NOISE #382 is short (DISC, 2026-10-18)

**A discretionary-aid read, never a book candidate.** Ordered by the owner 10-18 via MANAGER #116 ("more testing on things that are
promising").

## Why, and the two specs this note resolves
- **CTXSHORT r1** (ledger 2.190; docs/RESULTS_disc_ctxshort_r1_2026-10-17.md) ran the owner's CBD / ENGD context shorts as a frozen scan.
  - 0 of 3 exits passed, every read UNDERPOWERED.
  - The money was on NOISE #382 short days: E2 made +$19.6k on 141 trades. Every exit lost on #382-flat days (E2 -$12.6k on 75).
  - Only about 40% of r1's entries came while a NOISE short was already open, so "a NOISE short day" was not something a trader knew
    at the entry.
- **MANAGER #115 (10-17), verbatim:** "r2 is APPROVED as a discretionary-aid shadow read only (forming-bar context + NOISE #382
  short-already-open gate), frozen first, run TOMORROW after the quota reset, never a book candidate."
- **MANAGER #116 (10-18, the later spec), verbatim:** "run it as Stage A on the WF years, 09:45-11:30, COMPLETED bars only (the
  forming-bar trap), the owner's 3 dates + the journal's 6 real CBD/ENGD trades held out as the answer key; four numbers per exit rule.
  bar = gross/trade >= cost AND net ROC@30k > 0 AND not one episode AND MDL path; four numbers per arm".
- **The conflict:** #115 asks for the forming-bar context, #116 for completed bars only.
- **The resolution** (posted to MANAGER as #1444 before the freeze):
  - both readings run as arms with the gate, and #116's completed-bar arm (A) is the cell named first, because #116 is the later spec;
  - the forming reading (B) is defined so that it uses nothing after the signal close. It reads the bar holding the signal minute "so
    far". The r1 trap was a reference that measured with the forming bar without saying so; the prereg had then copied it as completed
    bars.

## What is different from r1
Triggers, window, entries, stops, the three exits, costs, masters, WF window, holiday rule and the read code are r1's frozen code
(`tools/disc_ctxshort_r1.py`, imported unchanged; its LF sha256 640fe08a...82a4 is asserted at start). r2 changes four things:
1. **The NOISE-short-open gate.**
   - A signal is taken only if a NOISE #382 SHORT is already open at the entry time: the open of the bar after the signal.
   - NOISE #382 is re-run from its run doc (strategy, params, NOADJ_NQ_5m_RTH id 37, cost), as in r1, on NQ 5m bars.
   - "Already open" means:
     - its fill (the open of its entry bar; the plugin decides on the bar before) is STRICTLY before the entry time;
     - and its exit bar has not yet opened.
   - A NOISE long never opens the gate.
   - **Disclosed:** NOISE's VWAP exits are decided a bar early and fill at the exit bar's open, so closing the gate there is exact. On
     the rare NOISE stop bars (about 1 in 400 shorts pre-WF), closing the gate at that bar's open is a slight look-ahead in CTXSHORT's
     favour. It drops entries made just before the rally to NOISE's stop. It is immaterial at that rate and is stated, not fixed.
   - **Disclosed:** the live Webull NOISE_382 leg trades the same rules on QQQ 5m bars, so its position can differ from this NQ gate,
     and how often they agree is unmeasured. A trader using the aid needs #382's NQ signal, not the Webull position.
2. **Arm B's bar-so-far context.**
   - The 5m / 30m bar that holds the signal minute is read through the signal bar's close. Its open is its first ETH minute's open;
     its close is the signal bar's close. The bars before it are completed.
   - It uses nothing after the signal close. The selftest truncates and perturbs every later bar, and checks that it catches three
     planted look-ahead edits.
   - In formulas (EMA alpha = 2/21):
     - **C3** (each of 5m and 30m): "the 20 EMA so far is below the last completed one, and the close is below it" is the same as
       close < the last completed bar's 20 EMA.
     - **C2** (each of 5m and 30m): "close < the 200 SMA so far" is the same as close < the mean of the last 199 completed closes.
     - **C4:** the 30m bar so far is red (close < its open) AND the two completed 30m bars before it are red.
     - **C1** is unchanged: close < the prior regular session's close.
   - **Disclosed:** at minute 0 of a 30m bar (10:00, 10:30, 11:00), the bar so far IS the signal candle, which the trigger already
     requires to be red. So B's C4 there reads "two completed red 30m bars". The same holds for the 5m legs at :00 / :05. The census
     prints B's signals by the 30m bar's age (0, 1-9, 10-19, 20-29 minutes).
3. **The verdict.**
   - MANAGER's #116 bar (with the MDL path) is applied as the house bar. It is expected to FAIL on the gated arms by construction (see
     Stage 0).
   - The owner-facing **aid read** is this lane's proposal, for MANAGER's OK. Against r1 it:
     - moves gross from > cost to >= cost, as #116 has it;
     - cuts the trade minimum from 100 to 30;
     - drops the bootstrap-t gate and the crown-shadow test. The trades are NOISE-short minutes by construction, so they are a shadow
       by design.
4. **The answer key** keeps r1's key days and r1's +/-5-minute time test, with trigger-only fires listed apart. Its gate is a NOISE #382
   re-run warmed from 2024-06-01 (more than 300 sessions before the first key date). It is applied to the MES rows too: the trader reads
   NQ's NOISE.

## Arms (same triggers; each arm has its own context and gate; four numbers per arm x exit)
- **A: completed-bar context (r1's C1-C4; MANAGER #116) + the gate. A / E2 is the cell named first.**
- **B: bar-so-far context (MANAGER #115, the deep dive's reading) + the gate.**
- **B0: bar-so-far context, no gate.** Report only, no verdict.
  - It is split into entries with the NOISE short open vs not open at entry.
  - Caveat for reading it: B0's ungated trades take the one-position and 2-a-session slots. So B's trades are not exactly B0's "open"
    subset; B is read against all of B0.
- E2 (half at 2R + 5m trail) is the primary exit. E1 (2R bracket) and E3 (hold to the close) are secondary.

## Data and window (as r1)
- Masters: ADJ_NQ_1m_ETH (id 66; its RTH slice = id 68), NOISE #382 on NOADJ_NQ_5m_RTH (id 37), and ORB #314 for the second-crown read.
- WF sessions 2016-07-01 .. 2025-06-29 only, with warm-up from 2016-03-01 (crowns from 2015-01-01). No outcome is read on a lockbox day.
- **The answer key** (Stage 2, flags only, after the WF read):
  - the owner's 3 design dates, in-sample by construction;
  - the journal's 5 distinct real CBD / ENGD signals (6 rows), of which 2 are reachable.
  - 2025-11 .. 2026-10 bars, and NOISE #382 from 2024-06, are read only to compute the flags and the gate on those days.

## Stage 0 (printed before any outcome)
- **Selftests:** r1's, plus:
  - bar-so-far truncation / perturbation on every column, on a random walk;
  - the forming bar's open and age, and entry times;
  - the crown's time mapping, and the strict gate edges, with a NOISE long ignored;
  - a zero-trade arm, the verdict edges, and run-record JSON.
- **Census per arm:** signal bars, BOTH, capped at 2 a session, per year, and B's 30m-bar ages.
- **Power line:** r1's SDs (E1 1.4, E2 1.6, E3 4.0 R) vs the prior +0.10 R.
  - The pre-WF 2015 flags (no outcomes, 2015-03-15 .. 12-31) gave 13 capped gated signals for A and 17 for B, about 15-20 a year. So
    both gated arms are expected UNDERPOWERED, and a null reads "not shown".

## Stage 1 reads, per arm x exit (r1's read code)
- **The house four numbers** (ROC @ $30k, DD5, DD % from peak, Sortino) on the WF daily curve, every regular session a row. Given for
  the $ curve (1 NQ) and the R curve ($500 a 1R).
- **Also:** gross points a trade vs 0.783, trades a year, win rate, mean R net, and the R-curve block-bootstrap t (20-session blocks,
  2,000 draws, seed 20261017; reported, not gated).
- **Splits and stresses:** the two cost stresses, the halves, ex Feb-Apr 2020, ex the 3 best trades.
- **ORB #314:** the trades on its flat days, and the flat-day share of own net (printed).

## Verdicts (set now; per gated arm x exit, NQ cost; B0 gets none)
- **House bar (MANAGER #116):** PASS when all four hold:
  - gross points a trade >= 0.783;
  - net ROC @ $30k > 0;
  - not one episode;
  - an MDL path: >= 50 trades a year AND ROC @ $30k >= 15.

  The gated census caps the trades at about 15-20 a year. So this bar is expected to FAIL on arms A and B, stated now, before any
  outcome. **This read is not a strategy test.**
- **Aid read** (the lane's proposal): **SUPPORTED** when all of these hold:
  - gross points a trade >= 0.783;
  - net ROC @ $30k > 0;
  - not one episode (one_episode is False);
  - net > 0 in both halves;
  - >= 30 trades.

  Otherwise NOT SUPPORTED.
- **Summary:** the count of SUPPORTED cells over the **6 gated cells** (2 arms x 3 exits), listed with trades and the bootstrap t, A / E2
  first.
- A SUPPORTED read describes the setup for a trader who already watches NOISE #382's NQ signal. Its trades are NOISE-short minutes by
  construction, so it has no book value. It changes no rule, size or live leg.

## Records
- One run-record line per arm x exit goes to `C:\EdgeLog\run_records\DISC_<YYYYMM>.jsonl` (house rule 10-18). That is 9 lines; B0's
  are marked report only.
  - run_id = CTXSHORT-r2-<arm>-<exit>-<harness sha8>; sha = the harness LF sha; the prereg sha8 is in the note.
  - The lines are written right after Stage 1, before the answer key.
- Harness: `tools/disc_ctxshort_r2.py`. It embeds this note's LF sha256 and stops on a mismatch; the hashes go to MANAGER before the run.
