# PREREG - test 75: SCALE-OUT exits for NOISE #382 and ORB #314 (owner 10-31, MANAGER #145)

Written and pushed BEFORE any scale-out is simulated. One family, both legs. NOISE lane writes this and runs the NOISE half
(`tools/noise_t75_scaleout.py`); the ORB lane runs the ORB half on THIS rule, unchanged.

## Question
The owner does not want +8.5 pts of open profit to end at +1. Does taking PART of the position off at a trigger, and holding
the rest to the leg's normal exit, beat holding the whole position (hold-to-exit)? Test 74 (giveback stop on the whole
position) was NO LIFT for NOISE; this is the partial-take version.

## t74 for ORB (MANAGER #144)
The t74 prereg (docs/PREREG_noise_t74_giveback_2026-10-31.md) was written for NOISE #382 only. ORB #314's giveback half runs
on THAT prereg's rule and reading rule unchanged (Y in {0.5,1,1.5}R x X in {33,50,67}%, WF chain only), owned by the ORB lane.

## The rule (fixed)
- **Trigger T**, measured from entry in the trade's favour:
  - `1R`, `2R` - R = the entry's own protective-stop distance (NOISE: bandwidth stop; ORB: its own stop).
  - Fixed points, in the LIVE instrument's points: NOISE {3, 5, 8} QQQ $/share; ORB {2, 4, 6} in its live instrument's
    points. A WF chain on a different instrument (NOISE's chain is NQ 5m) translates each fixed trigger as a % of the
    entry price at the 10-30 reference: NOISE QQQ 690 -> 3 = 0.435%, 5 = 0.725%, 8 = 1.159% of entry.
- **Fraction F** closed at the trigger: 1/3, 1/2, 2/3. Fill = the trigger level exactly (no better fill on a gap).
- **Armed from the bar AFTER entry.** A bar can scale only if it is after the entry bar and before the leg's exit bar. On
  the leg's own exit bar no scale happens (the stop-first rule: when a bar may touch both the trigger and the stop, the
  stop/exit is assumed first). Conservative by construction.
- **Remainder** (1 - F) holds to the leg's normal exit.
- **Breakeven arm (BE on / off):** with BE on, after the scale bar j the remainder's stop moves to entry from bar j + 1;
  a later bar before the leg's exit (or the exit bar when the leg's exit is not at its open) that opens through entry fills
  at the open, a touch fills at entry.
- **Cost:** the leg's round-trip cost per contract is kept on the whole size; a trade that scales pays ONE EXTRA exit
  commission on the scaled part, taken as half the round-trip cost (NOISE 0.533 / 2 = 0.2665 pts a contract) x F.
- Size tilt kept: per-unit result = F x T + (1 - F) x remainder - extra, then x the leg's size.

## Grid (30 cells per leg, nothing else runs)
T (5: 1R, 2R, three fixed) x F (3) x BE (2). Twin = HOLD (the leg as is).

## Stretch and numbers
WF chain only (NOISE: 2016-06-30 .. 2025-07-15, 8 anchored folds, crown params per fold, same rebuilt trades as t74).
**Lockbox never loaded.** Four numbers per cell via `augur_engine.drawdowns.four_numbers` on daily $: ROC@30k, DD5, DD%
from peak, Sortino; plus folds won vs HOLD (net $ per fold), trades scaled, and **MFE captured** = sum of final pts /
sum of MFE pts over trades with MFE > 0 (HOLD's value printed beside it).

## Reading rule (mirrors t74)
A scale-out is a LIFT for a leg only if ALL hold for that leg's best cell by WF ROC@30k:
1. It beats HOLD on WF ROC@30k AND WF Sortino.
2. Not one episode: it wins at least 5 of 8 folds on net $, AND its worst DD <= 1.3 x its DD5 (or the one-episode flag
   equals HOLD's).
3. Neighbours hold: the same T and BE with each adjacent F, and the same F and BE with each adjacent T in its own family
   (1R<->2R; fixed lower<->higher), also beat HOLD on ROC@30k.
Else NO LIFT. Prior about 15% (every NOISE exit change so far has failed; t74 included). Per-leg verdicts are separate.
A lift is a draft only (pinned 900-trial validate next); nothing live changes. Higher MFE captured alone is NOT a lift.
