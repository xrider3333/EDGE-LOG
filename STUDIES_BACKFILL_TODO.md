# STUDIES backfill — the four risk figures, study by study

**What this is.** On COMPARE ▸ STUDIES the parallel chart has ten axes. Four of them —
**WIN % · SHARPE · SORTINO · EV IN R** — are blank for almost every row, because no local
`.py` sweep ever *recorded* them. The drivers printed money, drawdown, profit factor and a
trade count and stopped there. Nothing on disk holds the missing figures, so filling them in
means **re-running the study** and recomputing from its own trades.

`augur_engine/analytics.py` owns the one definition of each figure, shared by `run_backtest`,
`validate.py` and the sweeps, so a re-run puts the *same* arithmetic on the axis an
Auto-Validate row already sits on. Two definitions of Sharpe sharing one axis is exactly the
silent blending this board exists to prevent.

## Where it stands

| | rows | done |
| --- | ---: | ---: |
| **Total registry rows** | 1,143 | **39** |
| noiseplateau243 | 39 | ✅ 39 |
| everything else | 1,104 | 0 |

## What each study needs

1. **four lines in the driver's per-cell row builder** — see `tools/noise_hunt5_plateau.py`
   `row_of()` for the pattern;
2. **a machine-readable results dump** — only one study has one today; the rest print to the
   screen and save nothing;
3. **the driver re-run** — the plateau study took 38 seconds and its verdict came out
   identical, so this does not change any finding;
4. **a mapping function** in `tools/backfill_risk_rows.py`, then
   `python tools/backfill_risk_rows.py --html <worktree>/index.html --write`.

**The mapping is verified, never assumed.** Every row is matched to its re-run cell on figures
the registry already holds — trade count exactly, profit factor to a hundredth — before a
single number is written. A cell that does not reconcile is refused and named. Putting one
configuration's Sharpe under another configuration's name is worse than a blank.

## Order of work, biggest win first

| # | family | rows | driver / shared helper | groundwork |
| --- | --- | ---: | --- | --- |
| 1 | **TTM** | 654 | `ttmsqz_baselines.stats()` feeds baselines / round 2 / round 3 (217 rows); rounds 4 and 5 have their own | ✅ shared helper done |
| 2 | **MISC** | 164 | `r16`–`r25` triage drivers | — |
| 3 | **ORB** | 144 | `orb_hunt*`, `orb_*` drivers | — |
| 4 | **NOISE** | 92 left | `noise_variant_research.metrics()` feeds seven drivers | ✅ shared helper done |
| 5 | **ENGU-Q** | 50 | `enguq_*` drivers | — |

## Two things that are NOT backfill and were checked

- **$ / YEAR and TRADES / YR are already fine.** They need a dated window, and 38 of the 44
  studies declare one. The six that do not are `noise`, `xfam`, `orbbe`, `orbgrail`, `enguq`
  and `paperlegs` — 83 rows. **Do not guess their windows**: a wrong window makes $/YEAR
  wrong, which is worse than a blank. Add each only when its real window is confirmed.
- **MAR, PF, EV and NET are dense already**, straight off what the registry holds.

## Separate, and probably more valuable: AUTO VAL is not fed by Past Runs

The AUTO VAL level lists **registry rows that happen to cite a run number**. It does not
enumerate Past Runs. Measured 2026-08-28: the registry cites **66 distinct run numbers**
spanning #202–#301, and **34 runs inside that range are cited by no row at all** (#204–#208,
#226, #238, #249, #251–#254, #258, #261–#267, #274, #278, #283–#288, #291, #294–#298, #300),
plus everything below #202.

So picking NOISE at AUTO VAL shows the NOISE runs somebody wrote a study row for — not every
NOISE Auto-Validate in Past Runs. Two ways out:

- **(a)** keep it registry-backed and write rows for the uncited runs — accurate, but it goes
  stale again the next time a run is not written up;
- **(b)** have the level read Past Runs directly, one line per run, the same data path the
  RUNBOARD already uses — complete by construction and cannot go stale.

**(b)** is the better shape. It also makes the level genuinely answer "what has actually been
validated", which is what the owner asked it for.
