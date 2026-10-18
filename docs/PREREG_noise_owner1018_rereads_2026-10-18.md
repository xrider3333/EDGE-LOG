# PREREG - NOISE lane, owner order 10-18 ("more testing on everything promising", MANAGER #127) - four threads, frozen before any number

**Status:** written 2026-10-18 13:35 MST, before any computation below. Every read here is a RE-READ or a LISTING. Nothing
can be adopted from it, and nothing live or in the book changes. The lockbox (2025-06-30 .. 2026-06-30) is veto-only and is
not read by any thread.

**Four numbers:** `augur_engine.drawdowns.four_numbers(daily)` (FRONTIER #125). Daily $ per stretch, every day present, zero
days in. It gives ROC@30k / DD5 (+ one_episode) / DD% from peak / Sortino, per stretch, never pooled across stretches.

## Thread 1 - T42 publication-decay re-read + harm monitor A1

**(a) Decay re-read.**
- Run `tools/noise_pubdecay_read.py` UNCHANGED. Its own pre-stated rule (`docs/PRESTATED_noise_pubdecay_2026-10-15.md`,
  sha 1cd933b5) is checked at start.
- The master now runs through 2026-10-17.
- This is an INTERIM monthly look. The pre-stated read point stays the 12-month forward mark, and this look cannot change
  that verdict.
- **Printed:** POST/PRE ratio, 90% CI, the power line, and #422's four numbers per stretch (PRE / POST / POST-DESIGN).
- **Context line, report only:** the forward stretch 2026-07-17 .. 2026-10-17 on its own.

**(b) Harm monitor.**
- Run `tools/harm_monitor.py` WITHOUT `--post`. Its output is the read file only.
- Report in plain words:
  - is NOISE #422's A1 still tripped (sticky by rule);
  - where the leg stands now against its pace line;
  - its A2 drawdown state.

## Thread 2 - the three shelf-44 lifts that held (ORB LW44 r1, prereg 43e6f81f), on a SECOND SPLIT and the FORWARD months

**The lifts, as LW44 paired them:**
- (L1) the #422 seat vs the #304 seat inside #463;
- (L2) NOISE x1.25 inside #463 (#463 + 0.25 x the NOISE leg);
- (L3) #422 with the KEEL v12 fixed package vs raw #422.

LW44 read the claims' own WF rows (2016-07-01 .. 2025-06-29).

**Second split = pre-WF, 2010-06-07 .. 2016-06-30.**
- Same series construction as LW44 (lw44_inventory.md).
- Book rows on the book's own day stamps; leg rows reindexed with zeros.
- If L3's KEEL package has no honest pre-WF series (KEEL needs history to learn), L3's pre-WF line is reported as
  "not available" rather than rebuilt with a look-ahead.

**Forward = 2026-07-17 .. 2026-10-17.**
- The four legs re-run on the current masters as the harm monitor does. L1's #304 seat and L2's x1.25 come from the same
  runs.
- L3 uses the forward shadow's real fills (forward log) where the engine replay of the KEEL package is unavailable.

**Per lift, per stretch:**
- The four numbers for the candidate and the baseline.
- The paired Sharpe difference: `sharpe_diff_test` from ORB's `augur_engine/sharpe_diff.py`, sha pinned at read time.
  Pre-WF only; forward is too short to test.
- Fold by fold:
  - calendar years for pre-WF (2010H2, 2011 .. 2015, 2016H1);
  - months for forward;
  - each fold's ROC@30k candidate vs baseline and its sign.

**Reading rule (fixed now):**
- A lift **HOLDS on the second split** if all of these hold on pre-WF:
  - the paired SR difference is > 0 with one-sided p < 0.10;
  - the candidate's ROC@30k >= the baseline's;
  - the candidate is not one episode where the baseline is not.
- **WEAKENS** if the SR difference is > 0 but the rest fails; **REVERSES** if the SR difference is < 0 with p < 0.10.
- Forward is a report line only, whatever it shows.

## Thread 3 - everything the FUNDGRID / fund runs touched since 09-18, on one scatter

**What it covers:** a LISTING, no new run. Every NOISE-lane fund read since 2026-09-18, from the ledger rows and their
result files:
- IWM r1;
- sector funds r1 (each fund);
- the XLK Auto-Validate #488 (NOISE_1_1_FUNDGRID.py);
- the QQQ calibration r1 and QQQ validate #485;
- TLT fade r1;
- the GLD / SPY / DIA controls map check.

**Each row:** run / ledger row, instrument, stage (preWF / IS / WF / LB / forward), the four numbers as recorded, and gross
points or bps a trade vs cost where recorded.
- Where a recorded row lacks DD5 or DD%, recompute it from that run's own saved daily series ONLY if one exists on disk.
  Otherwise mark it '-'.

**Output:**
- one CSV plus one scatter PNG: ROC@30k (y) vs DD% from peak (x), WF and LB as separate marks, labelled by fund;
- monochrome, house style.

## Thread 4 - run records (new house rule, MANAGER #127)

**The file:** `C:\EdgeLog\run_records\NOISE_202610.jsonl`, one line per completed engine run and stage.
- **Schema:** {ts, lane, host, where, strategy, family, instrument, timeframe, stage, roc30k, dd5, ddpct, sortino, trades,
  gross_pt, cost_pt, one_episode, ledger_row, run_id, sha, note}.

**What goes in:**
- this prereg's own runs, as they finish;
- a BACKFILL of every NOISE-lane run since 2026-09-18, taken from the lane's ledger rows and result files. Values are
  copied, never re-estimated; '-' becomes null.

**The 289-entry catalogue:** its entries that carry numbers go to `C:\EdgeLog\run_records\CATALOGUE_202610.jsonl`, with
lane = the owning lane and note = "from catalogue". They are kept apart so other lanes' own backfills are not
double-counted. MANAGER can merge them.

## Timing

Results to MANAGER by 21:00 MST 2026-10-18, with the four numbers on every line.
