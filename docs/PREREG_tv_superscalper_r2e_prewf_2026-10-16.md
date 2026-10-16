# PREREG - SUPERSCALPER r2e: does the r2d carrier (RE long) beat an always-long twin on the PRE-WF rows? (OUR PORT) - TV, 2026-10-16

Written before any pre-WF number of this port exists. r2d (docs/SUPERSCALPER_R2D_PATHS.md) found one path-side carrying both
development years - RE long (2023 364 trades net PF 1.205, 2024 412 PF 1.120) - and the port's net on its long side (longs PF
1.139 / 1.069, shorts 0.897 / 1.007) in two NQ up-years. SELECTION COUNT: RE long is the best of 12 path-side cells read on the dev
years (plus 6 aggregates), so its dev PFs are inflated by selection. This prereg asks whether RE long earns, beyond what an
always-long position in the same clock hours earns, on data neither the development years nor the 900-trial validate touch.
GO: MANAGER #151 (with the always-long twin and its bar). Owner standing order 10-16 via MANAGER #148. DESCRIPTIVE unless it passes.

## Data never read by this port
- NQ 1m ETH no-adjust master id 34 (NOADJ_NQ_1m_ETH.csv, starts 2010-06-06). PRE-WF periods, each loaded and run standalone as
  the dev years were (r2's Runner: one load per period, cold start): P0 2010-06-06 .. 2010-12-31, P1 2011, P2 2012, P3 2013, P4 2014,
  P5 2015, P6 2016-01-01 .. 2016-06-30 (~6.07 years). Nothing at or after 2016-07-01 (the validate's window) is read here.
- The QQQ 1m helper feed starts 2016-01-04, so every pre-WF period runs with the QQQ feed WITHHELD (an empty injected feed, the
  port's own test hook) - one object throughout. ES 1m helper: the harness asserts master id 30 (NOADJ_ES_1m_ETH.csv) starting on
  or before each period's first day and holding >= 90% of NQ's bar count in each period; any 'feed unavailable'
  warning from the port refuses the run. Daily VIX file held for the whole span.

## Fixed
- Port `augur_strategies/MISC_SUPERSCALPER_1_0.py` LF sha256 b8ef032f89c1adb1a57093df0a319060a9c2165ff6565c09c2a90f0d6a2955e1 at file
  defaults (IMPROVED_R1, session 'all'), intrabar 'worst', close_rule 'any'; re-checked after every period. Engine, master
  loader, stats and four numbers from r2's harness (tools/superscalper_explore_r2.py, LF sha 26a2f9aa..., sha-checked).
- STEP 0 - the QQQ control on the dev years (already seen; no fresh data): with QQQ present 2023 / 2024 must reproduce r2d's parity
  gates (2,311 / 2,005.9 / 0.5690 and 2,633 / 1,997.4 / 0.5853), else refuse. Then re-run both with QQQ withheld; report RE long
  and the trade overlap (same entry bar, side and path) with vs without QQQ. same_object = RE long still meets r2d's carry rule
  (>= 100 trades, PF >= 1.10 at 0.706, > 1.00 at 0.956) in both dev years with QQQ withheld.
- THE ALWAYS-LONG TWIN (MANAGER #151): for each trade, the twin is a long held over the SAME clock window - entry at the same New York
  wall-clock time as the trade's entry bar, held for the same clock duration (exit bar start minus entry bar start) - on every OTHER
  trading date of the same period, entering at the open of the first bar starting within 5 minutes after that time and exiting at
  the open of the first bar starting within 5 minutes after the end; dates without both bars, or whose window straddles a roll
  switch (tools/data/rolls_NQ.csv), are skipped. twin = the mean of those changes (points). Same cost as the trade, so the paired
  difference d = trade gross - twin. For shorts (context) the twin is the always-short mirror (d = gross + twin).
- Cells per period and pooled: RE long, BOS long, ALL long, ALL short, ALL - trades, trades a year, win rate, avg win / loss, net PF,
  net points, mean d (twin-adjusted per trade), and the four numbers (ROC@30k, DD5 and DD% from peak at the $30k sizing, daily
  Sortino) on the cell's daily P&L; costs 0.706 pt and 0.956 pt (+1 tick). Context: mu x hold (all-bar drift) per trade.

## Reading (fixed now) - RE long, pooled P0-P6, QQQ withheld
- (A) beats the twin: paired t = mean(d) / (sd(d) / sqrt(n)) >= 2.0 (sd of the difference), trades with no valid twin date excluded
  and counted.
- (B) net PF >= 1.10 at +1 tick (0.956), from unrounded sums (MANAGER #151).
- (C) >= 100 trades a year (pooled count / 6.07).
- (D) not one episode: (B) still holds with every trade exiting on the single best exit date removed.
- RE LONG HOLDS only if A, B, C and D all pass AND same_object. A, B, C, D passing with same_object False = "holds for the no-QQQ
  variant only" - not a candidate (the validate window has QQQ).
- Each failure is named for what it measures, never lumped: A = "not separable from always-long drift"; B = "below the PF bar at
  +1 tick"; C = "too thin"; D = "one episode". Per-period PFs are printed as context; a period with no RE long trade has no PF.
- POWER (pre-stated): the dev years' RE long per-trade sd is ~19 pt; with ~1,800 pooled trades the paired bar detects ~1.3 pt a
  trade 80% of the time. The dev edge (1.75 / 1.21 pt net a trade) shrunk for best-of-12 selection (~0.7 pt) would pass (A) about
  a third of the time; fewer trades (the port's fixed 5-point minimum target bites harder at 2010-16 prices) lower that. A FAIL is
  therefore weak evidence against a small edge - but it is the pre-set bar, and it closes the line.
- If RE long HOLDS: a separate ranged file (an entry-path / side knob) and its own 900-trial Auto-Validate, only after MANAGER reads
  this; the validate's folds clean of 2023-24 (about folds 1-4) are its next check. If it FAILS: the path line closes and the queued
  validate stays the only Super Scalper read.
- Long vs short (context only): longs and shorts with no edge sit around minus the cost each, shifted by the twin; printed raw and
  twin-adjusted, no verdict drawn from them.

## Harness
`tools/superscalper_explore_r2e.py` - checks this file's LF sha256, r2's harness sha and the port sha at start, prints its own.
Output `C:\EdgeLog\_research_cache\tv_scalp\superscalper\explore_r2e.json`. Pushed as prereg/tv-ssexplore5 before the run. Review
before freeze (2 lenses, adversarial verify, 10-16): fixed - an empty period counted as profitable, every failure labelled 'drift';
added - the twin (MANAGER #151), the QQQ same-object rule, the ES check, the one-episode guard, trades a year, the power line. Second
review of the revision (10-16): no blocker / major; minor fixes taken (ES bar-count + feed-warning refusal, a checkpoint JSON per period,
an empty-pool guard).
