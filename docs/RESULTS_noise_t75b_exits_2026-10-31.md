# RESULTS - TEST 75 PHASE B, NOISE #382 half: trailing / breakeven exits (2026-10-31)

Prereg: `docs/PREREG_t75b_exits_2026-10-31.md`, locked v1 (sha256 0cb05bb6) and pushed before any run (v73.1450
8cd5b80c). Phase A (in-sample, 2 trades): `tools/t75_phaseA_exits.py` (v73.1449 44adbea1). Simulator:
`tools/noise_t75b_exits.py`. Grids: `C:\EdgeLog\_anatomy_cache\t75b_exits\full_grid.csv` and `chain_grid.csv`.

## Verdict: NO LIFT - 0 of 5 exits pass on NOISE #382. Hold the leg to its own exit. Nothing live changes.

**OOS 2022-01 .. 2025-07-15.** The prereg's verdict stretch. The lockbox was never loaded. 1,016 trades.

| Exit | ROC@30k | DD5 | DD% | Sortino | Net | Years won | MFE captured | Rule |
|---|---|---|---|---|---|---|---|---|
| HOLD (leg as is) | 129.32 | $17,528 | 10.22 | 4.30 | $318,087 | - | 15.8% | - |
| E1 ATR trail 3x14 | 123.09 | $15,773 | 9.78 | 4.02 | $291,777 | 2/4 | 14.3% | fails ROC |
| E2 Chandelier 3x22 | 100.97 | $16,291 | 9.34 | 3.51 | $251,308 | 0/4 | 12.4% | fails ROC |
| E3 6-bar trail | 36.12 | $16,709 | 14.63 | 2.11 | $131,477 | 0/4 | 6.6% | fails ROC |
| E4 Time-decay trail | 70.67 | $14,221 | 10.36 | 2.73 | $166,404 | 0/4 | 8.0% | fails ROC |
| E5 BE 1R + 2 ATR trail | 140.59 | $14,516 | 9.53 | 4.26 | $312,025 | 3/4 | 15.4% | fails Sortino + IS |

**IS 2010-06 .. 2021-12.** Direction check, 3,496 trades.
- Hold: ROC 41.16, DD5 $10,269, Sortino 2.43, net $226,901.
- Every exit is below hold on ROC. In order: E5 33.85, E1 21.20, E2 21.50, E4 15.41, E3 8.05.

**WF chain 2016-10 .. 2025-07.** Second line, test 74's rebuild, about 0.5% off the stored chain.
- Hold: ROC 62.25, Sortino 3.04, net $401k.
- E1 ATR trail: ROC 71.49, Sortino 3.14, DD5 $15.5k against $18.0k, net $393k.
- E1 wins only 4 of 10 years, and it fails IS badly (21 against 41). So its chain lead is the drawdown
  shape, not more money.
- Every other exit is at or below hold.

## What it means
- **E5 (breakeven at 1R, then a 2-ATR trail)** is the closest call.
  - OOS ROC 140.6 beats hold's 129.3, and it wins 3 of 4 years.
  - But Sortino is 4.26 against 4.30, and net is $6k LESS.
  - The higher ROC comes from a smaller DD5 ($14.5k against $17.5k), not more money.
  - It also loses IS (33.8 against 41.2).
  - Rules 1 and 4 fail.
- **No trail keeps more of the best open profit than holding does.** Across the stretch, hold keeps 15.8% of
  MFE; every trail keeps 6.6-15.4%.
  - A trail does lock in the one trade that gave back, as on 10-30.
  - But it also cuts the trades that dip and then run to the close, and NOISE's money is in those.
- **The Phase A ranking flipped.** The time-decay trail banked 85% of MFE on the 10-30 trade and was first in
  Phase A. Out of sample it is 4th of 5, with ROC 70.7 against 129.3. Two trades picked because they gave
  back make every trail look good.
- **The fifth NOISE exit change to fail:**
  1. Targets (#490).
  2. Holding rule (shelf 39/41).
  3. Giveback stop (test 74).
  4. Scale-out (test 75, first scope).
  5. Trails (this test).
  The giveback the owner sees is the cost of the long runs that carry the leg.

## Caveats
- **The entry parameters were tuned on part of IS + OOS.** That affects hold and every exit alike. This
  compares exits on the same trades; it is not a fresh validate.
- **ATR runs on NQ 5m RTH bars.** On a session's first bars it includes the gap from the prior close.
- **ORB #314's half** runs on the same prereg, handed to ORB (ORB inbox #129).
