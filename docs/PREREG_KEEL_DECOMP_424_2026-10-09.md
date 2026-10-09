# KEEL DECOMPOSITION on run #424 - pre-data note (2026-10-09)

For MANAGER and TTM (MANAGER #146 (3), the owner's KEEL question from the reading shelf: Kim-Tse-Wald and Nagel 2025).
Written BEFORE any twin is computed. Read so far: #424's metadata only. That is the strategy, windows and KEEL version
from the run doc, plus the doc's KEEL average size of 1.253 and trust-on 45.9%. No P&L of any reading has been read for this
note (the doc's KEEL row exists on the site; this lane has not opened it). REPORT ONLY: nothing here is adopted, crowned
or traded. TTM independently re-implements every twin below from this note and checks the numbers.

## The run and the data

- **#424:** NQDIP_1_1.py (DIP 1.1) on NQ 5m RTH (db_noadj_rth), 2010-06-07 .. 2026-08-24, multiplier 1.0, cost 0.
  It was superseded for its verdict by #434 (true rolls); MANAGER named #424, so #424 it is. The definitions carry over
  unchanged to #434 if MANAGER prefers it.
- **Reproduction first (tools/backfill_keel.py's path):** the doc's champion through `run_backtest(..., return_trades=True)`
  on the doc's own window. Guard: the ungated pre-lockbox block must match the doc's `gate_validate.ungated_pre`
  (3,185 trades exactly, net within 0.5%), else stop and report.
- **KEEL as shipped in the row:** `ml_keel.keel_walk(arrays, trades, version="v12")` over ALL the run's trades (the walk
  is causal; its 600-trade ledger warms up on 2010-16). Every statistic below is read on the **WF trades only**: entry
  date in [2016-07-18, 2025-08-24). The lockbox (from 2025-08-24) is not read; the KEEL family's lockbox is spent.
- **r_i** = trade i's P&L at size 1 (the run's own units). A reading with sizes s books s_i x r_i on trade i's EXIT
  session. The yardstick is applied to that daily series: WF ROC @ $30k (= 30 x MAR, daily drawdown), DD5 beside it
  ("driven by one episode" if worst DD > 1.3 x DD5), $ a year, Sortino, worst DD, by calendar year.
- **Costs:** the run's are 0, and every reading below keeps 0. At a constant per-unit cost, the timing component
  (below) is cost-neutral by construction, because sum (s_i - s_bar) x c = 0. The leverage part is not.

## KEEL v12's size, in its parts (ml_keel.py as on main)

s_i = event(comp(dow(L_i))), where:
- **L_i (learned part):**
  - Shade branch: when fast-trust t_fast < -0.5 and z != 0, L = clip(1 - z, 0.5, 1.5).
  - Otherwise: L = clip(1 + 1.5 x trust x z, 0.75, 2.0), with trust from the 600-trade dollar ledger, cut by the 50-trade fast ledger.
- **dow:** x1.5 on Fridays, capped at 3.0.
- **comp:** x1.5 when sq60_on, capped at 3.0.
- **event:** x0.5 before a FOMC statement (cut hour 14), applied last.

The fixed tilts alone (L = 1) are exactly `ml_keel.fixed_tilt_sizes_v12`.

## The readings (each on the same WF trades; s_bar = KEEL's MEAN SIZE OVER THE WF TRADES, measured and printed)

1. **RAW:** s = 1.
2. **KEEL:** s_i as above.
3. **F - the Kim-Tse-Wald fixed twin:** s = s_bar on every trade. F's ROC @ $30k equals RAW's: a constant size cancels
   in MAR. On the yardstick, KEEL against F is therefore the whole question. The dollar split is printed:
   KEEL - RAW = (s_bar - 1) x RAW [LEVERAGE] + sum (s_i - s_bar) x r_i [TIMING].
4. **FT - fixed tilts only:** fixed_tilt_sizes_v12, multiplied by one constant so its WF mean is s_bar.
5. **LO - learned part only:** L_i (dow / comp / event off), multiplied by one constant so its WF mean is s_bar.
   The timing of KEEL - FT - LO is printed as the INTERACTION.
6. **M - the Nagel momentum twin (the strategy's own trailing P&L):**
   - m_i = the sum of r_j over the last 20 trades whose EXIT bar is strictly before trade i's entry bar.
   - z_i = m_i / sd_i, where sd_i = the sd of all such 20-trade sums known before i (expanding). z_i = 0 until 100
     trades have resolved.
   - s_i = clip(a + b x z_i, 0.5, 2.0), the clip MANAGER named.
   - a and b are solved together so that M's WF sizes have KEEL's WF MEAN and KEEL's WF SD: the same amount of leverage
     and the same amount of timing. If no (a, b) reaches both inside the clip, b = 0.5 (KEEL's base slope) and only the
     mean is matched, said so.
   - Also printed: corr(KEEL's s_i - s_bar, z_i) and the OLS slope of KEEL's s_i on z_i. This is Nagel's question:
     how much of KEEL's sizing is the strategy's own momentum?
7. **P1 - reversal placebo of M:** the same as M with b -> -b (size up after recent losses), same a, same clip, mean
   re-matched to s_bar. If momentum timing is real, P1 should lose about what M makes.
8. **P2 - KEEL on the sign-flipped series:** keel_walk(v12) re-run with every trade's P&L sign flipped (r_i -> -r_i;
   entries, exits and features unchanged), read on the flipped WF series against the flipped RAW and F.
   - A sizer with real per-trade skill learns the flipped mapping and should still add timing money there.
   - The fixed tilts cannot adapt, so their part flips sign.
   - A sizer that only rides the leg's own run of luck should show little in either direction.

## The null for every timing number (the only "is it more than chance" line)

For KEEL, FT, LO and M, the timing component sum (s_i - s_bar) x r_i is set against 2,000 permutations of that reading's
own WF sizes across the WF trades. Each permutation keeps the size distribution and the mean, and destroys the
alignment with outcomes. Printed:
- the p95 of a plain shuffle;
- the p95 of a shuffle in blocks of 20 trades (keeps size clustering);
- the reading's percentile.

Seeds 20261009 / 20261010.

## What gets reported (to MANAGER + TTM; nothing adopted)

- Per reading: WF net, $ a year, ROC @ $30k / DD5, Sortino, worst DD, mean / sd / min / max size, % of trades sized
  by the shade branch (KEEL, P2), and by year.
- The KEEL - RAW dollar split (leverage, timing), and timing split into FT / LO / interaction, each against its null.
- Nagel line: M's timing and its null beside KEEL's; the KEEL-on-momentum slope and correlation; P1 and P2.
- One sentence for the owner: is KEEL's WF gain on #424 leverage, fixed tilts, learned selection, or the leg's own
  momentum.

## Not done here

- No search over the 20-trade window, the slope or the clip. One value each, fixed above; others are not tried.
- No lockbox. No change to KEEL, ml_keel.py or any live leg.
- Code: a new script, tools/rocfrontier/r28_keel_decomp.py, which imports ml_keel / engine / backfill_keel's
  loaders unchanged. Its sha256 goes to MANAGER + TTM before it runs.

## ADDENDUM 1 (2026-10-09, before any twin is computed): MANAGER #147's four edits + TTM's eleven pins (DM 10-09 06:05)

Read since the note, while checking formats: the header and the first two rows of DISC's trade files (two 2011 warm-up trades),
and DISC's published restatement table (RESTATE_ROLL22_2026-10-08.md: #424 RAW full-window ROC 17.7 on the saved list, 21.1 on
PURE). No KEEL number and no twin number has been read. Where this addendum and the note differ, this addendum wins.

**A1 - THE TRADE LIST (MANAGER edit 3).**
- PRIMARY: DISC's PURE roll-restated list, C:/EdgeLog/_anatomy_cache/restate_roll/dip424_pure_trades.csv (3,404 trades; the
  true-roll twin with no entry or exit fill on a roll session; verified by TTM).
- SECOND COLUMN: the saved list, dip424_saved_trades.csv (3,431 trades), printed beside it on every line, because it carries the
  roll defect.
- Each file's (entry, exit) times are ET wall-clock bar STARTS. Each maps to the bar of the doc's master (NOADJ_NQ_5m_RTH,
  index US/Eastern) whose start equals it exactly, and that gives keel_walk's entry and exit bars. Any time without an exact
  match refuses the run.
- pnl is the file's dollar P&L at size 1. Arrays = that master over the doc's window 2010-06-07 .. 2026-08-24; KEEL's features
  come from it, as in the validate.
- Guard on the saved list: its trades entered before 2025-08-24 must match the doc's ungated pre block (3,185 trades exactly,
  net within 0.5%), else the run refuses.

**A2 - KEEL IS TODAY'S WALK (TTM 1).** KEEL = today's ml_keel.keel_walk(version "v12") on the list being read. The doc's KEEL row
(avg size 1.253, trust-on 45.9%; computed 09-24 on another master build) is printed beside it as a figure, not a parity target.
TTM's reproduction on the saved list reads 1.248.

**A3 - KEEL'S OWN PROVENANCE (MANAGER edit 2).**
- The per-trade parts are causal. The two members (logit, ExtraTrees) refit every 25 trades on resolved trades only. Trust
  comes from the 600-trade dollar ledger, cut by the 50-trade fast ledger, and the shade branch reads only resolved trades.
- KEEL'S DESIGN WAS NOT. Its schedule (v5: floor 0.75, slope 1.5, trust from t 0.5 to 1.0), fast window (v6 / v10: 50 trades),
  shade (v7 / v8), compression x1.5 (v9), Friday x1.5 (v11) and pre-FOMC x0.5 (v12) were chosen 2026-09-06 .. 09-09. They were
  read on the NQ walks of NOISE #243 / #304 (and ORB, ENGU-Q) over 2010-06 .. 2026-06, lockboxes included.
- That data overlaps #424's WF window (2016-07-18 .. 2025-08-24) in the same market. DIP was not used.
- **So KEEL's reading on #424 is IN-SAMPLE for its design (out-of-family, same market and years), and the result line says so.**
  F, FT's tilts and M carry the same caveat only where they inherit KEEL's choices: FT inherits the tilts, F and M inherit only
  the mean size.

**A4 - "RESOLVED" (MANAGER edit 1, TTM 3-4).**
- Everywhere in this note, a trade is RESOLVED for trade i when its EXIT bar is strictly before trade i's ENTRY bar.
- For M, the resolved trades are ordered by exit bar (ties broken by entry order, a stable sort).
- R_k = the sum of r over resolved trades k-19 .. k in that order, defined from the 20th resolved trade.
- At trade i, with K = the number of resolved trades:
  - m_i = R_K;
  - sd_i = the sample sd (ddof 1) of R_20 .. R_K;
  - z_i = m_i / sd_i;
  - z_i = 0 while K < 100. The warm-up counts resolved trades.
- KEEL's own ledgers use ml_keel's definition, unchanged.

**A5 - M AND P1 (TTM 5).** M requires b >= 0 (searched on [0, 20]). P1 = slope -b with a RE-SOLVED so P1's WF mean size is s_bar,
the same clip. The note's "same a" is withdrawn.

**A6 - THE NULLS (TTM 6, 8).**
- Plain shuffle: seed 20261009. Block shuffle: seed 20261010. Each is a fresh generator per reading.
- Blocks are runs of 20 consecutive WF trades in entry order. The partial last block is kept as its own block, and whole blocks
  are permuted.
- P2 gets both nulls, around P2's own WF mean.

**A7 - THE DAILY SERIES (TTM 2, 7).**
- WF = entry time (ET wall clock) in [2016-07-18 00:00, 2025-08-24 00:00) ET.
- Exit session = the exit bar's ET date.
- Rows = every master session date from the first session on or after 2016-07-18 to the last WF trade's exit date, zero days
  included.
- Sortino = mean / sqrt(mean(min(x, 0)^2)) x sqrt(252) over all rows (r11_risk.stats).
- Years = (last row - first row) / 365.25.

**A8 - P2's F (TTM 8).** F_flip = the flipped RAW x P2's own WF mean size.

**A9 - LO AND SHADE (TTM 9).**
- LO = L_i, the learned part INCLUDING the shade branch: everything before the three a-priori tilts.
- Shade share = the WF trades whose L_i differs from clip(1 + 1.5 x trust_i x z_i, 0.75, 2.0). The shade lean cannot coincide
  with that value, so the detection is exact. This is t_fast < -0.5 and z != 0, as TTM states.

**A10 - COSTS (MANAGER edit 4, TTM 11): #424's P&L is ALREADY NET.**
- The job's cost_pts is 0 because NQDIP_1_1 charges its own costs inside the plugin: 0.783 pt per round trip (the overnight NQ
  round trip) x $2 x MNQ micros, plus 0.25 pt per quarterly roll crossed. Micros = round(100,000 / (entry price x 2)).
- So r_i is net at size 1. A size multiplier s scales micros, and so the cost, linearly. s x r_i is the net at s, with
  fractional micros and no rounding.
- The "with costs" row is therefore every reading as computed.
- The added "without costs" row adds back c_i = s_i x 0.783 x $2 x micros_i, with micros_i from the master's OPEN at the entry
  bar. The roll part is not added back, so it is labelled approximate gross.
- The house RTH cost (0.533 pt) is not used: DIP holds overnight and its own 0.783 is the run's convention.
