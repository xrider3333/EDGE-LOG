# RESULTS - ENGU-Q EXECUTOR ROUND r1 (board rows T07 and T08)

2026-10-18, lane ENGU-Q. Prereg `docs/PREREG_enguq_executor_r1_2026-10-18.md` (+ addenda 1-2), frozen
commit `95b1c8816fec86fba356ca97b322a813f6a3867f` on `prereg/enguq-executor-r1`, hashes posted to
MANAGER before the run (#1452, #1455, #1457). Harness `tools/enguq_exec_r1.py`. Run log
`C:\EdgeLog\enguq_exec_r1.log`, record `C:\EdgeLog\_anatomy_cache\enguq_exec_r1\enguq_exec_r1.json`.

**The one-line answer: T07 passes the bar and T08 fails it, but neither arm's headline survives the
fold test, and T07's whole-stretch lead over the bare leg is a property of the YEARS, not the signals.**

## The published arms, on the frozen series (WF 2016-07-01 .. 2025-06-29, 8.9938 years)

| arm | ROC@30k | DD5 | DD% from peak | Sortino | net | one episode |
|---|---|---|---|---|---|---|
| LEG - ENGU-Q #335 as the book trades it | 26.09 | $31,177 | 14.54% | 1.680 | $380,133 | yes |
| T07 - NQ signals filled on QQQ prints | 28.42 | $34,652 | 10.68% | 1.642 | $371,843 | no |
| T08 - the RTH executor holding overnight, NQ prices | 24.57 | $35,511 | 11.74% | 1.470 | $347,041 | yes |

## C1 - fold by fold: T07 3 of 8, T08 3 of 8. Bar was 7 of 8. NO FOLD-LEVEL EVIDENCE, both.

| fold | from | to | LEG | T07 | T08 | T07-LEG | T08-LEG |
|---|---|---|---|---|---|---|---|
| 1 | 2016-10-12 | 2017-11-23 | 107.96 | 93.63 | 89.82 | -14.33 | -18.13 |
| 2 | 2017-11-23 | 2018-12-30 | 32.38 | 20.98 | 16.84 | -11.39 | -15.54 |
| 3 | 2018-12-30 | 2020-02-03 | 57.34 | 105.47 | 95.46 | **+48.14** | **+38.13** |
| 4 | 2020-02-03 | 2021-03-08 | 90.24 | 87.00 | 85.69 | -3.24 | -4.55 |
| 5 | 2021-03-08 | 2022-04-04 | 109.12 | 124.18 | 123.60 | +15.06 | +14.47 |
| 6 | 2022-04-04 | 2023-05-02 | -7.98 | 4.20 | 1.03 | +12.18 | +9.01 |
| 7 | 2023-05-02 | 2024-05-29 | 28.00 | 23.86 | 15.97 | -4.14 | -12.03 |
| 8 | 2024-05-29 | 2025-06-27 | 130.39 | 63.29 | 53.21 | **-67.10** | **-77.18** |

- Per-fold difference: T07 mean **-3.10**, sd 32.69. T08 mean **-8.23**, sd 33.59. On the average fold
  both executors LOSE to the bare leg, and T08 loses by more than its whole-stretch figure suggests.
- The whole-stretch picture is the opposite of the fold picture for T07 (+2.33 ROC points over the leg),
  and that is not a contradiction: ROC@30k is net divided by the WORST drawdown, so an executor that
  smooths one bad episode lifts the whole-stretch ratio while losing on most folds. T07's DD% from peak
  is 10.68% against the leg's 14.54%, and its DD5 is actually WORSE ($34,652 vs $31,177) - so the lift
  is in the single deepest drawdown, not in the typical one.
- Fold 8 is where the executors pay: the leg makes 130.39 and T07 only 63.29. Half the leg's best year
  is lost to filling at the next session's open.

## C3 - the years or the signals: T07 = THE YEARS. T08 = neither.

**Item (3) as #116 wrote it could not be run, and this was declared before any number existed:** the
QQQ 1m tape starts 2016-01-04 (`master_dd092f50.csv`, Alpaca split-adjusted RTH, 1,023,757 rows), so no
2010-16 QQQ arm exists at any cost or sizing. The substitute and its reading rule were fixed in the
prereg in advance.

| half | arm | ROC@30k | DD5 | DD% | Sortino | gap vs LEG |
|---|---|---|---|---|---|---|
| H1 folds 1-4 (4.40 yr) | LEG | 44.82 | $15,464 | 10.49% | 1.605 | - |
| | T07 | 40.29 | $13,773 | 10.73% | 1.874 | **-4.52** |
| | T08 | 38.89 | $14,112 | 11.65% | 1.753 | -5.92 |
| H2 folds 5-8 (4.30 yr) | LEG | 36.70 | $31,177 | 22.97% | 1.849 | - |
| | T07 | 38.97 | $34,652 | 16.99% | 1.713 | **+2.27** |
| | T08 | 32.29 | $35,511 | 17.66% | 1.474 | -4.41 |

- **T07's gap FLIPS SIGN** between the halves (-4.52 then +2.27). By the rule written before the
  numbers, that is the YEARS. The "keeps 98% of its edge on QQQ" headline is a 2021-25 fact; in
  2016-21 the same executor kept about 90% of a much larger edge.
- T08's gap is -5.92 and -4.41, both small against the per-fold sd of 33.59, so the honest answer is
  NEITHER - this round cannot tell the two apart for T08.

## C0 - PARITY GATE: FAILED, for a known reason, by a small margin

| arm | worst day | days over the 50c tolerance | first | net re-derived | net published |
|---|---|---|---|---|---|
| LEG | $4,095 | 4 of 2,626 | 2020-03-02 | $378,594 | $380,133 |
| T07 | $4,094 | 2 of 2,626 | 2020-03-02 | $369,804 | $371,843 |
| T08 | $4,125 | 4 of 2,626 | 2020-03-02 | $344,961 | $347,041 |

- The published reads were made 2026-10-09. The ADJ NQ 1m ETH master has been refilled since (its
  registry row now runs to 2026-10-16), and TTM traced a 10-15 fill that inserted 740 bars INSIDE run
  #491's optimize window on this same tape. A bar inserted inside a window shifts every later bar
  index, so the leg's own trades move.
- **The gate failed and the prereg's fallback was honoured**: C1 and C3-halves above read the frozen
  published series only, and nothing below is published against the published baseline.
- The divergence is nonetheless SMALL and localised - 2 to 4 days of 2,626, starting 2020-03-02, and
  0.4-0.6% of net. That is reported so a reader can size the risk; it does not soften the gate, which
  was set at 50c a day on purpose.

## C2 - COST LADDER [re-derived tape, addendum 2 - read as deltas, the levels are NOT the board rows]

A tick is added to EACH SIDE, so "+1 tick" is two ticks a round trip: NQ +$10.00, QQQ +$0.02 a share
(+$16.44 at 822 shares). "late" moves every fill one bar later at base cost.

| arm | rung | trades | gross/trade | cost/trade | ROC@30k | DD5 | DD% | Sortino |
|---|---|---|---|---|---|---|---|---|
| LEG (at bar closes) | base | 1,194 | $322.51 | $15.66 | 24.38 | $32,379 | 15.48% | 1.589 |
| | +1 tick | 1,194 | $322.51 | $25.66 | 23.41 | $32,654 | 15.97% | 1.532 |
| | +2 ticks | 1,194 | $322.51 | $35.66 | 22.45 | $32,932 | 16.50% | 1.476 |
| | late | 1,194 | $312.10 | $15.66 | 24.02 | $32,974 | 15.29% | 1.515 |
| T08 | base | 824 | $434.30 | $15.66 | 24.43 | $35,511 | 11.80% | 1.455 |
| | +1 tick | 824 | $434.30 | $25.66 | 23.67 | $35,717 | 12.10% | 1.417 |
| | +2 ticks | 824 | $434.30 | $35.66 | 22.92 | $35,923 | 12.57% | 1.379 |
| | late | 824 | $433.50 | $15.66 | 24.17 | $34,424 | 11.91% | 1.452 |
| T07 | base | 823 | $465.78 | $16.44 | 28.27 | $34,652 | 10.74% | 1.626 |
| | +1 tick | 823 | $465.78 | $32.88 | 26.88 | $34,404 | 11.45% | 1.560 |
| | +2 ticks | 823 | $465.78 | $49.32 | 25.53 | $34,743 | 12.61% | 1.495 |
| | late | 823 | $472.02 | $16.44 | 29.36 | $33,980 | 10.56% | 1.657 |

- **Nothing dies.** No arm reaches net ROC@30k <= 0 at any rung, and gross/trade exceeds cost/trade by
  20x to 28x everywhere. These are 400-point-a-trade holds; a tick is noise against them.
- Decay per rung: T07 **-1.37**, LEG -0.97, T08 **-0.76** ROC points. T07 decays FASTEST (a QQQ tick is
  about 1.5x an NQ tick in relative terms), T08 SLOWEST.
- T07's lead over the leg-at-closes narrows from +3.89 (base) to +3.47 (+1 tick) to +3.08 (+2 ticks) -
  it keeps most of its lead, against my prior.
- **1-bar-late fills HELP T07** (+1.09 ROC points) and barely touch T08 (-0.26) or the leg (-0.36).
  My prior said late fills would cost T07 more than the cost rungs; that was wrong, and the sign is
  wrong too. A bar's delay at the open is slightly favourable here.

## C4 - T08's overnight gaps [re-derived tape, addendum 2]

- **1,176 session boundaries are held through on the WF stretch, and they carry $386,945 of the arm's
  $344,961 net - 112%. The daytime part of T08 is NEGATIVE.** The overnight hold is not a bonus on top
  of the day trade; it is the whole of the edge and then some.
- $30k sizing = 30,000 / worst DD $47,108 = **0.6368 contracts**.

| held from | to | pos | move pts | $ at 1 NQ | $ at $30k |
|---|---|---|---|---|---|
| 2025-04-09 | 2025-04-10 | 1.0 | -431.25 | -$8,625 | -$5,493 |
| 2025-04-15 | 2025-04-16 | 1.0 | -346.75 | -$6,935 | -$4,416 |
| 2022-10-25 | 2022-10-26 | 1.0 | -268.00 | -$5,360 | -$3,413 |
| 2023-02-02 | 2023-02-03 | 1.0 | -265.25 | -$5,305 | -$3,378 |
| 2025-05-16 | 2025-05-19 | 1.0 | -254.25 | -$5,085 | -$3,238 |

- Four of the worst five are 2022-2025 and three are April-May 2025. The tail is recent, not historical.
- **DD5 $35,511, worst DD $47,108, ratio 1.33 -> ONE EPISODE** (the bar is 1.3, so it fails by 0.03).

## C3 EXTRA - T08 pre-walk-forward, 2010-06-07 .. 2016-06-30 [FLAGGED, outside the bar]

| arm | ROC@30k | DD5 | DD% | Sortino | net |
|---|---|---|---|---|---|
| LEG | 16.87 | $6,958 | 7.00% | 1.010 | $32,880 |
| T08 | 13.73 | $7,442 | 7.69% | 0.891 | $29,552 |

Gap -3.15 ROC points, the same sign and rough size as both WF halves (-5.92, -4.41). This is the
closest honest thing to the 2010-16 read #116 asked for, it is outside "WF years only", and **no
verdict in this round cites it.** Read as colour: the executor's small drag on the leg looks like a
constant of the fill rule, not a feature of any era.

## THE BAR

BOOK #463 drawdown-day correlation measured on 2,296 drawdown days of 2,626 (column `L0_close`).
Condition 1 is computed on the re-derived tape (addendum 2); conditions 2-4 on the published figures.

| condition | T07 | T08 |
|---|---|---|
| 1 gross/trade >= cost/trade | PASS ($465.78 vs $16.44) | PASS ($434.30 vs $15.66) |
| 2 net ROC@30k > 0 | PASS (28.42) | PASS (24.57) |
| 3 not one episode | PASS | **FAIL** (ratio 1.33) |
| 4 MDL path (ROC >= 15, >= 50 trades/yr, rho_dd no worse than the leg's) | PASS (92/yr, rho 0.056 vs leg 0.057) | PASS (92/yr, rho 0.063 vs leg 0.057) |
| **verdict** | **PASSES THE BAR** | **FAILS THE BAR** |

## What this round changes

1. **Neither row is fold-robust.** Both beat the bare leg in 3 of 8 folds against a bar of 7. The board
   rows should carry that, because "keeps 98% of its edge" reads as a property and it is not one.
2. **T07's edge over the leg is a years effect**, by the test written before the data. It is not
   evidence that filling NQ signals on QQQ is better; it is evidence that 2021-25 suited it.
3. **Cost is not the risk here.** Two ticks a side costs 2.7 ROC points at most and a bar's delay costs
   nothing. Anyone worried about Webull's fills on this leg can stop worrying about the fills.
4. **T08's real risk is the overnight gap, and it is concentrated and recent** - 112% of the net comes
   from holds through the close, the worst five gaps are -$8,625 down to -$5,085 at 1 NQ, and the
   drawdown is one episode by 0.03.
5. **The published 10-09 reads can no longer be reproduced bit-for-bit** because the ADJ NQ master was
   refilled. The divergence is 4 days and 0.5% of net, but any future read of these rows needs the
   master pinned by filename AND by row count, not by name alone.

## Priors, scored

| prior | outcome |
|---|---|
| C1: 4-6 of 8 for T07, 2-4 for T08, neither reaching 7 | RIGHT on the verdict, T07 low (3, not 4-6) |
| C2: T07 loses most of its lead by +1 tick | WRONG - it keeps +3.47 of +3.89 |
| C2: T08 nearly cost-insensitive | RIGHT, and it is the least sensitive of the three |
| C2: late fills cost T07 more than the cost rungs | WRONG, and backwards - late fills HELP T07 |
| C3: the gap is stable (signals, not years) | WRONG for T07 - it flips sign |
| C4: a few gaps carry DD5, one of the worst five inside the deepest episode | RIGHT on concentration |
