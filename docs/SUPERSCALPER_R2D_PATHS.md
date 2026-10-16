# SUPERSCALPER r2d - which entry path and side carry it, in both development years (OUR PORT) - RESULT (TV, 2026-10-16)

Prereg `docs/PREREG_tv_superscalper_r2d_paths_2026-10-16.md` (LF sha256 e1868258..., witness prereg/tv-ssexplore4 @ 0ecc8f9b, pushed
and posted to MANAGER before the run; reviewed adversarially before the freeze). Harness `tools/superscalper_explore_r2d.py` (LF
4a88f173...). Port LF b8ef032f... at file defaults (IMPROVED_R1, session all), close_rule 'any', intrabar 'worst', NQ 1m ETH no-adjust
master id 34. Both parity gates passed (2023: 2,311 trades / 2,005.9 net pt / win 0.5690; 2024: 2,633 / 1,997.4 / 0.5853). Output
`C:\EdgeLog\_research_cache\tv_scalp\superscalper\explore_r2d.json` (log `explore_r2d_run.log`). DESCRIPTIVE ONLY: nothing changes.

## Result: ONE path-side carries it in both years - RE long (a hypothesis, not a finding)
| Path-side | 2023 trades / net PF / at +1 tick | 2024 trades / net PF / at +1 tick | Carries? |
|---|---|---|---|
| RE long (re-entry) | 364 / 1.205 / 1.173 | 412 / 1.120 / 1.094 | YES (the only one) |
| BOS long | 1,118 / 1.078 / 1.057 | 1,365 / 1.099 / 1.081 | no (PF < 1.10 both years) |
| OB long | 230 / 1.353 | 206 / 0.945 | no (flips) |
| OB short | 175 / 1.087 | 206 / 1.359 | no (flips) |
| BOS short | 267 / 0.840 | 251 / 0.960 | loses both years |
| RE short | 66 / 0.645 | 86 / 0.597 | loses both years |
| MAIN, TRAP, OD (each side) | 1-23 trades | 0-23 trades | too thin (< 100) |

Four numbers for RE long on its own daily P&L, one-year reads (ROC@30k / DD5@30k / DD% from peak / Sortino):
- 2023: 45.7 / $14.8k / 18.6% / 1.18 at 0.706; 36.9 / $14.5k / 19.4% / 1.01 at +1 tick (1 EPISODE).
- 2024: 29.5 / $14.6k / 26.7% / 1.08 at 0.706; 22.8 / $14.7k / 27.5% / 0.85 at +1 tick (1 EPISODE).
- RE exits: 59% / 57% at the stop, 41% / 43% at the target (2023 / 2024).

## The side split (context)
- All longs: 2023 1,778 trades PF 1.139 (ROC 58.3), 2024 2,070 trades PF 1.069 (ROC 48.3). All shorts: 2023 PF 0.897 (ROC -22.0),
  2024 PF 1.007 (ROC 1.0). The port's whole net in both years is its long side.

## Reading
- 2023 and 2024 were strong NQ up-years. A long-side carrier in two up-years can be market drift picked up by a long entry, not an
  entry edge: the shorts losing in both years points the same way. 12 path-side cells were read; one passing by luck is plausible.
- So RE long (and the long-only shape) is a HYPOTHESIS. Its clean test is data neither the dev years nor the validate touch: the
  PRE-WF rows (2010-06 .. 2016-06; master 34 starts 2010-06-06), which include the 2011 and 2015-16 sell-offs, read before any
  number - the next prereg (r2e). The validate's walk-forward folds clean of 2023-24 (about folds 1-4, 2020-02 .. 2022-10, the 2022
  bear inside) are the second check once the run lands.
- The queued 900-trial validate is unchanged (port b8ef032f, no path or side knob). A path / side knob would be a later, separate
  ranged file and validate, only if r2e holds.
