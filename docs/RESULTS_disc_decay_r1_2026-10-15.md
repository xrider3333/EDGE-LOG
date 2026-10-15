# RESULTS: DECAY r1 - the house's own out-of-sample Sharpe shrink (DISC, 2026-10-15)

- **Prereg:** docs/PREREG_disc_decay_r1_2026-10-15.md, branch prereg/disc-decay-r1 = 6378133b, pushed before the run.
  - LF sha256 0e802566...d587, checked at the run's start.
- **Harness:** tools/disc_decay_r1.py.
- **Outputs:** C:\EdgeLog\_anatomy_cache\decay_r1\ (run.log, runs_sample.csv, decay_r1_result.json).
- **Source paper:** reading shelf No. 19, Falck, Rej & Thesmar (arXiv 2105.01380). Median OOS / IS Sharpe 0.55, slope 0.57.

## Verdict (pre-set): LESS DECAY
Across 127 saved validates in 8 families (in-sample Sharpe >= 0.3):

| read | median | 90% family-cluster bootstrap | paper |
|---|---|---|---|
| Q1 lockbox / in-sample Sharpe | 0.98 | 0.73 - 1.14 | 0.55 |
| Q2 walk-forward / in-sample Sharpe | 1.08 | 1.02 - 1.14 | - |
| Q3 lockbox / walk-forward Sharpe (the haircut on the number we act on) | 0.95 | 0.75 - 1.05 | - |

- The slope of lockbox Sharpe on in-sample Sharpe through the origin is 0.87 (paper 0.57).
- The SR_IS > 0 sensitivity read (129 runs) gives the same medians.

## The haircut is a FAMILY story, not a house constant
Family medians of lockbox / walk-forward Sharpe (runs):

| family | h | runs |
|---|---|---|
| ORB | 1.00 | 26 |
| ENGU-Q | 0.98 | 25 |
| DIP | 1.31 | 14 |
| NOISE | 0.81 | 38 |
| TTIBS | 0.56 | 9 |
| TTM | -0.12 | 11 |
| GAPGO | -1.58 | 3 |
| CBU-Q | -1.75 | 1 |

- Only 35% of runs have lockbox Sharpe above walk-forward Sharpe. Median Sharpe: IS 0.99, WF 1.10, LB 0.94.

## Forward haircut per book / live leg
- Method: the leg's WF ROC @ $30k, from the run's stored WF curve (trade-level drawdown), times its family's h.
- DD5, DD % from peak and Sortino: '-' (no curve is simulated).

| leg | WF ROC | h | expected forward ROC |
|---|---|---|---|
| ORB #234 | 35.2 | 1.00 | 35.2 |
| ORB #314 | 21.7 | 1.00 | 21.7 |
| ENGU-Q #335 | 33.9 | 0.98 | 33.3 |
| NOISE #422 | 76.5 | 0.81 | 62.3 |
| NOISE #382 | 61.9 | 0.81 | 50.4 |
| DIP #424 | 24.3 | 1.31 | 31.9 (an h above 1 is the lockbox year's luck, not a promise) |
| **TTM #459** | 38.9 | -0.12 | **-4.7** |

**The TTM read.** Across 11 runs the TTM family's lockbox Sharpe is negative while its walk-forward is +0.69. This agrees with the family luck bar
(2.150: TTM #459 beats the bar only on its own run). It is the one book leg where this read says to expect about nothing forward.

## Predictors (pre-set rule: t >= 2 in the predicted direction AND the same sign in all 8 leave-one-family-out refits)

| outcome | predictor | beta | t | holds? | notes |
|---|---|---|---|---|---|
| q_LB | IS Sharpe level | -0.003 | -0.03 | no | |
| q_LB | log trades per knob | +0.11 | +1.26 | no | |
| q_LB | plateau share | -0.04 | -2.36 | no | wrong sign: higher-plateau runs shrank MORE in the lockbox |
| q_WF | log trades per knob | +0.07 | +2.08 | **yes** | more in-sample trades per knob = less IS -> WF shrink, as the paper predicts |
| q_WF | IS Sharpe level | -0.08 | -1.85 | no | |
| q_WF | plateau share | -0.02 | -1.25 | no | |

- Run date is too short a span (07-16 .. 10-14) to read; correlation 0.07.

## What this does and does not show
- **The house's pipeline does not show the paper's 45% haircut.** The IS -> WF step shows none: WF Sharpe is about 8% higher, because WF covers
  2016-25, a richer regime for intraday futures than the 2010-16 tuning years. LB / WF shrinks about 5% at the median.
- **One shared lockbox year.** Every run's lockbox is essentially the same 12 months (2025-07 .. 2026-07), so the LB ratios mix decay with how
  that one year suited each family. The 129 runs are not 129 independent tests of decay: their effective sample for the LB level is one year per
  family. The family-cluster bootstrap does not capture that common-year shock, so the intervals are too narrow for "decay", though fine for
  "this year".
- **Near-duplicates.** Runs inside a family are often re-validations of the same rule, so N overstates the evidence.
- **Selection across runs is not measured.** The paper's decay is of SELECTED (published) factors. Our analogue is the crowned runs' forward
  record, about 3 months so far. The harm monitors remain the right forward read.
- **Use:** read TTM's forward with this -0.12 in mind; read NOISE's WF numbers about 20% lower; treat a high WF figure on few trades per knob
  with more suspicion (the one predictor that held).
