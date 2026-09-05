# Continuous-lockbox grading — first run, 2026-09-05

Harness: `tools/continuous_lb_check.py`. One continuous backtest per config over
2010-06-07 → 2026-06-30 (NQ 1m ETH, `db_noadj_eth`, cost 0.533, mult 20), trades sliced into
selection / lockbox by **entry time**, against the reload the engine actually grades on.

**Self-test PASS** — the frozen #226 control reproduces to the cent: n=2,843 / $434,721.12 /
PF 1.332 / DD $50,420. Every EV R below also matches the engine's own `expectancy_r` to 3 dp.

## Results (selection = 2010-06-07 → 2025-06-30, lockbox = 2025-06-30 → 2026-06-30)

| config | sel n | sel EV R | sel R/YR | LB n (cont.) | LB EV R | LB R/YR | top-10 share | longest hold | reload vs cont. LB |
|---|---|---|---|---|---|---|---|---|---|
| **B14** (mined out of #309) | 2,342 | **0.598** | **93.1** | 184 | 0.291 | 53.5 | 81% | 164 d | 211 vs 184 (+27) |
| #309 crown (ER gate) | 1,270 | 0.342 | 28.8 | 67 | **1.179** | **79.0** | 61% | 104 d | 83 vs 67 (+16) |
| #226 frozen (DEPLOYED) | 2,655 | 0.227 | 40.0 | 188 | 0.364 | 68.5 | 80% | 105 d | 212 vs 188 (+24) |
| **#310 LIM** (verdict PASS) | 749 | 0.942 | 46.8 | **0** | — | — | **90%** | **449 d** | **91 vs 0 (+91)** |

## What it found

1. **#310 is run #198's failure repeated, on today's fixed file.** Its last entry is held 449 days
   to the final bar, so it takes **no lockbox trades at all**; the engine's reload invents 91 and
   the run carries a PASS. Two queued BOOK jobs use this leg at these exact params and report the
   program's highest R / YR (148 / 152). Both job docs were annotated in place before running.
   Nothing was cancelled — that is the owner's decision.
2. **B14's R / YR 93 is real and reproduces to the dollar, but does not survive contact with the
   held-out year.** It beats the deployed leg 0.598 / 93.1 against 0.227 / 40.0 pre-lockbox, then
   **loses to it on both reads in the lockbox** (0.291 / 53.5 against 0.364 / 68.5).
3. **Concentration is a family property, not a B14 defect.** B14 81%, deployed #226 80%, #310 90%.
   Only the ER crown (61%) is meaningfully less tail-dependent. Judging B14 on "81% in ten trades"
   alone would condemn the leg already in production.
4. **The reload always over-counts, and by how much depends on the shape.** ORB (flat at the close,
   no multi-session state) is exact — #234 178 vs 178, #314 168 vs 168. NOISE is +7% to +17%.
   ENGU-Q on the 24h tape is +13% to +24%, every config tested. **Lockbox verdicts on overnight
   families are systematically optimistic.**
5. **Run #198's "not deployable" write-up is pre-fix and no longer reproduces.** Commit 6da54db
   (2026-08-26) fixed an ETH regime mis-scaling (390 bars/day assumed on a 1,091-bar tape), so
   `regime_len 5` now means 5 days rather than ~1.8. Same params today: 1,795 trades not 1,304,
   longest hold 156 days not 449, 100 lockbox entries not 0. **Any run older than 2026-08-26 whose
   params set `regime_len > 0` no longer reproduces from its own file.**

## A trap this run walked into, recorded so the next reader does not

The first pass ran the #310 case with `params={}` and it came back **byte-identical to #226**.
`ENGUQ_1M_ETH_LIM_1_0.py`'s DEFAULT_PARAMS are the parity anchor (`limit_atr 0` = fill at the
signal close = the frozen config), so the file's defaults are NOT its champion. Same lesson as
`edgelog-run234-not-reproducible`: pass the run's `best_params` explicitly, always.

## Not done

The reload is still not warm-started, so the engine keeps grading long-lookback configs on a
truncated window; this tool measures the damage rather than fixing it. NOISE and ORB configs were
measured only through their saved blocks, not re-run here.
