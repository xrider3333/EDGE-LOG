# RESULTS - test 75: SCALE-OUT exits, NOISE #382 half (2026-10-31)

Prereg: docs/PREREG_noise_orb_t75_scaleout_2026-10-31.md (v73.1440 28885f3c, pushed before any simulation).
Tool: tools/noise_t75_scaleout.py. Grid: C:\EdgeLog\_anatomy_cache\t75_scaleout\grid_wf.csv. ORB half: ORB lane.

## Verdict: NO LIFT for NOISE. Hold the whole position to the leg's exit. Nothing live changes.

| | ROC@30k | DD5 | DD% | Sortino | Folds won | MFE captured |
|---|---|---|---|---|---|---|
| HOLD (leg as is) | 62.25 | $18.0k | 6.46 | 3.04 | - | 13.9% |
| Best cell: 2R, close 1/3, no BE | 63.14 | $17.8k | 6.52 | 3.06 | 3/8 | 14.0% |

- The best cell passes rule 1 (beats HOLD on ROC@30k and Sortino) by hair widths: +0.89 ROC, +0.02 Sortino.
- It FAILS rule 2: it wins only 3 of 8 folds on net $ (the bar is 5). The gain sits in a few folds, not across the years.
- Its neighbours along F (1/2, 2/3 at 2R) also edge HOLD on ROC (62.86, 62.58) - the 2R scale barely changes anything
  because only 176 of 2,345 trades (7.5%) ever reach 2R before the exit bar.
- MFE captured does not move: 13.9% HOLD, 9.9%-14.2% across the grid. Taking a piece early does NOT keep more of the run.

## What the grid says
- **Early triggers cost money.** 1R scales 480 trades and loses 2-5 ROC points; the 3-point trigger (0.43% of entry)
  scales 653 trades, loses 4-10 ROC points, and wins 0 of 8 folds in every cell. The early part of the move is where the
  NOISE winners are still building; cutting them there gives up more than the giveback it saves.
- **Late triggers change nothing.** 2R and the 8-point trigger (1.16% of entry) touch 7-8% of trades and land within
  +/-1 ROC point of HOLD.
- **Breakeven on the remainder does not help.** BE on vs off differs by under 1 ROC point everywhere.
- Same picture as test 74 (giveback stop on the whole position): the leg's money is in a few long runs; any rule that
  trims trades before they finish taxes them.

## Caveats
- Same rebuild as test 74: 2,345 trades / 20,074 pts against #382's stored 2,343 / 19,975 (0.5%). Both arms use the same
  rebuilt trades, so the comparison is like-for-like; absolute numbers are not #382's stored ones.
- Conservative fills by prereg: no scale on the exit bar (stop first), fill at the trigger even on a gap, an extra half
  round-trip commission on the scaled part.
- WF chain 2016-06-30 .. 2025-07-15 only; lockbox never loaded.
