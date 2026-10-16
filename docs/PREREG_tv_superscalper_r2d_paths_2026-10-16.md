# PREREG - SUPERSCALPER r2d: which ENTRY PATH and side carry it, in both development years (OUR PORT) - TV, 2026-10-16

Owner standing order 10-16 via MANAGER #148 ("keep looking for scalpers ... never idle"; "the next scalper decomposition on
dev data" while the 900-trial validate waits on TBIS's runner restart). Written before any number of this split. DESCRIPTIVE
ONLY: no filter, no adoption, no change to the port or to the queued validate. A path that carries both years becomes a
HYPOTHESIS for a separate, later prereg (a path knob on a ranged file + its own 900-trial Auto-Validate) after MANAGER reads it.

## What differs from the 10-12 scalp hunt and from r2 / r2b / r2c
- The 10-12 hunt (STRATEGY-BEATING, rounds 37-38, the OVERRIDE runs) tested generic fixed-target 1-minute scalps (micro ORB, open
  drive, PDH/PDL, range burst, VWAP cross ...): 0 of 59 at house cost. This port is a different object: a published multi-path
  entry engine (MAIN / BOS / OB / RE / TRAP / OD) with ATR stops and 2x targets, net PF 1.05 (2024) and 1.07 (2023) at file defaults.
- r2 / r2b / r2c cut it by CLOCK (sessions, RTH hours): no window carried both years. r2d cuts it by the ENGINE'S OWN ENTRY PATH
  and side - a split never printed. Disclosure: the per-path counts and P&L of any year are unseen; the yearly totals are known
  (2023: 2,311 trades / 2,005.9 net points at 0.706 under close_rule 'any'; 2024: r2's E1 total).

## Fixed
- Port: `augur_strategies/MISC_SUPERSCALPER_1_0.py`, LF sha256 b8ef032f89c1adb1a57093df0a319060a9c2165ff6565c09c2a90f0d6a2955e1, file
  defaults (IMPROVED_R1, session 'all'), intrabar 'worst', close_rule 'any' (the r2b/r2c decomposition rule), NQ 1m ETH no-adjust
  master id 34; engine and master loader through r2's Runner (tools/superscalper_explore_r2.py, LF sha 26a2f9aa..., sha-checked).
- PARITY GATES first, both years, close_rule 'any' at 0.706: 2023 = 2,311 trades / 2,005.9 net points / win rate 0.5690 (r2b);
  2024 = 2,633 trades / 1,997.4 net points / win rate 0.5853 (r2 E1). The win rate tells 'any' from 'fifo' (same totals; 'fifo'
  books each exit against the oldest open ticket's path, which would scramble a path split). The port's LF sha is re-checked
  after each year and before the JSON is written. Any mismatch refuses the run.
- Cells: path (MAIN, BOS, OB, RE, TRAP, OD; "?" counted if any) x side (long, short), plus each path both sides and each side all
  paths. Years 2023 AND 2024 (both development years; nothing else read). Costs 0.706 pt and 0.956 pt (+1 tick). Each cell:
  trades, win rate, average win / loss, net PF, net points, and the four numbers (ROC@30k, DD5 and DD% from peak at the $30k
  sizing, daily Sortino) on the cell's daily P&L - each a one-year read (thin); "1 EPISODE" only where worst DD > 1.3x DD5. Context only: the share of exits by reason
  (stop / limit / reverse / roll_flat / time) per path.

## Reading (fixed now)
- "A path-side carries it" only if: net PF >= 1.10 in BOTH years, >= 100 trades in EACH year, and net PF > 1.00 at +1 tick in
  BOTH years (PFs from unrounded sums). With 12 path-side cells x 2 years read, one carrier by luck is plausible - so a carrier
  is a hypothesis, never a finding. Its clean test is data the dev years never touched: the validate's walk-forward folds whose
  TEST slices end before 2023-01-01 (with init 40% of 2016-07 .. 2025-06 and 8 folds, about folds 1-4, 2020-02 .. 2022-10),
  read apart - the folds that test on or tune on 2023-24 never count - or a direct read of 2016-07 .. 2022-12, which no run of
  this port has read. The walk-forward never tests 2016-07 .. 2020-01 out of sample.
- "None carries" = the port's edge is not concentrated in one entry path either; the clock and path splits are both spent and the
  validate stands alone.

## Harness
`tools/superscalper_explore_r2d.py` (checks this file's LF sha256, r2's harness sha and the port sha at start). Output
`C:\EdgeLog\_research_cache\tv_scalp\superscalper\explore_r2d.json`. Pushed as prereg/tv-ssexplore4 before the run. Review before
freeze (2 lenses, adversarial verify, 10-16): the clean-fold line was wrong (it named the whole walk-forward) - fixed above;
minor fixes: 2024 parity gate, 'any'-vs-'fifo' win-rate gate, port re-checked during the run, unrounded carry PFs, JSON-safe
output, the one-episode wording.
