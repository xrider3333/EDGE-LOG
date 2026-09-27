# PRE-REGISTRATION — what KEEL v12 adds on NOISE #422: the double squeeze and the learned part (2026-09-27)

Written and committed BEFORE any arm below except A0/A1 was computed. A0 and A1 were read on 2026-09-27
(tools/keel_422_stack_check.py, commit 40d25f64) and are the comparators, not candidates.

## Why
The owner's live-leg pick is NOISE #422 + KEEL v12. Two things about that stack are untested:
1. **Double squeeze.** #422 already sizes 1.75x in compressed hours (hourly squeeze, 20 / 1.15); KEEL v12
   adds its own 60-minute squeeze 1.5x on top, so the same bet is counted twice (up to 5.25x).
2. **The learned part.** The 7-seed bag showed KEEL's walk-forward return per drawdown equals raw's on
   #304 and #382 (docs/PREREG_keel_bag_2026-09-26.md), and the live box runs KEEL at trust 0 - i.e. the
   fixed tilts only. If the model adds nothing, the simpler fixed tilts should be what goes live.

## Arms (same round-60 tape, stretches and leak-fixed engine as tools/keel_bag_check.py)
- A0  #422 alone.                                            (already read)
- A1  #422 + KEEL v12, 7-seed bag (seeds 90001-90007).       (already read)
- A2  #422 + KEEL v12 WITHOUT its compression multiplier, 7-seed bag, same seeds.
- A3  #422 + the fixed v12 tilts only, no model: compression 1.5x, Friday 1.5x, cap 3.0, FOMC
      pre-statement 0.5x (ml_keel.compression_sizes with those arguments).
- A4  #422 + the fixed tilts WITHOUT compression: Friday 1.5x and the FOMC 0.5x only.

## Decision rules (walk-forward decides; the lockbox only vetoes)
- **H1, drop KEEL's squeeze on #422:** A2's walk-forward return per drawdown beats A1's by at least 3%
  AND A2's walk-forward Sortino is at least A1's.
- **H2, the learned part adds nothing on #422:** A3's walk-forward return per drawdown is at least A1's
  AND A3's walk-forward Sortino is at least 97% of A1's. (If H1 also holds, the same test is A4 vs A2.)
- **Lockbox veto:** no arm is recommended unless its lockbox return per drawdown is at least A0's.
- **Recommendation:** among arms that clear the veto, the one with the highest walk-forward return per
  drawdown, reported beside its WF/LB net, ROC %/yr, Sortino, drawdown and largest contract multiple.

## What happens next
Nothing live changes. The recommendation goes to MANAGER as an owner call for the #422 live build.

---

## RESULT (read 2026-09-27 after 10dedef5) - H1 does not hold, H2 HOLDS, recommendation A3

`python tools/keel_422_parts_check.py` (round-60 tape; WF 2016-06-30..2025-07-16, LB 2025-07-16..2026-09-16).

| arm | WF net | WF ROC %/yr | WF Sortino | WF DD | WF ret/DD | LB net | LB ROC %/yr | LB Sortino | LB DD | LB ret/DD | max size |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A0 #422 alone | 448,732 | 49.6 | 4.49 | 17,616 | 2.82 | 82,488 | 70.6 | 3.67 | 22,416 | 3.15 | 1.75x |
| A1 + KEEL v12 (7-seed) | 745,188 | 82.4 | 4.97 | 31,173 | 2.64 | 145,199 | 124.2 | 4.68 | 31,756 | 3.91 | 5.25x |
| A2 + KEEL v12 no squeeze | 626,053 | 69.2 | 4.74 | 28,848 | 2.40 | 115,910 | 99.1 | 4.08 | 31,991 | 3.10 | 5.25x |
| **A3 + fixed tilts only** | 635,254 | 70.2 | **5.48** | **19,356** | **3.63** | 110,339 | 94.4 | 3.86 | 28,116 | 3.36 | 3.94x |
| A4 + fixed tilts, no squeeze | 522,642 | 57.8 | 4.86 | 17,364 | 3.33 | 92,093 | 78.8 | 3.66 | 25,162 | 3.13 | 2.62x |

- **H1 does not hold:** removing KEEL's squeeze LOWERS walk-forward return per drawdown (2.64 -> 2.40). The
  double squeeze is not what hurts; in the fixed form it helps (A3 3.63 vs A4 3.33).
- **H2 HOLDS:** the fixed tilts alone beat full KEEL on walk-forward return per drawdown (3.63 vs 2.64) and
  Sortino (5.48 vs 4.97). The learned model adds $110k of walk-forward money for $11.8k (61%) more
  drawdown - leverage, not edge, the same finding as the 7-seed bag on #304 and #382.
- **Lockbox veto:** A1 and A3 clear it (3.91 and 3.36 vs raw 3.15). A1's lockbox lead is partly in-sample
  for KEEL, which was designed with that stretch visible.
- **Pre-registered recommendation: A3, #422 + the fixed v12 tilts with no model.** Deterministic (no seed),
  largest size 3.94x instead of 5.25x. The live box already runs KEEL at trust 0, which is the fixed tilts
  in practice; A3 makes that explicit and stops the model from growing into the sizing as trust accrues.
  Owner call; nothing live changed.

---

## ADDENDUM PRE-REGISTRATION (2026-09-27, committed before any #382 arm is computed) - the same test on NOISE #382

The live leg today is #382 + KEEL v12. The identical arms A0-A4, H1, H2, lockbox veto and recommendation
rule above are applied unchanged to NOISE #382 (NOISE_1_8_CT304.py 30-min, 16, 1.15, 2.0x), same tape,
stretches, engine and seeds (A1/A2 = 7-seed bags 90001-90007). A0 and A1 for #382 were read on 2026-09-26/27
(tools/keel_bag_check.py) and are comparators only. Nothing live changes whatever the result.

## ADDENDUM RESULT - NOISE #382 (read after f6e09db6): H1 does not hold, H2 HOLDS, recommendation A3

`python tools/keel_422_parts_check.py --leg 382`

| arm | WF net | WF ROC %/yr | WF Sortino | WF DD | WF ret/DD | LB net | LB ROC %/yr | LB Sortino | LB DD | LB ret/DD | max size |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A0 #382 alone | 505,314 | 55.9 | 3.87 | 20,960 | 2.67 | 90,675 | 77.6 | 2.95 | 33,290 | 2.33 | 2.00x |
| A1 + KEEL v12 (7-seed) | 765,966 | 84.7 | 4.24 | 32,715 | 2.59 | 111,340 | 95.2 | 2.74 | 40,881 | 2.33 | 6.00x |
| A2 + KEEL v12 no squeeze | 660,097 | 73.0 | 4.01 | 30,953 | 2.36 | 87,919 | 75.2 | 2.29 | 41,992 | 1.79 | 6.00x |
| **A3 + fixed tilts only** | 710,868 | 78.6 | **4.84** | 25,170 | **3.12** | **120,614** | 103.2 | **3.26** | 32,941 | **3.13** | 4.50x |
| A4 + fixed tilts, no squeeze | 595,995 | 65.9 | 4.26 | 22,174 | 2.97 | 104,198 | 89.1 | 3.05 | 35,733 | 2.49 | 3.00x |

The #422 finding replicates on the live leg, more strongly: the fixed tilts beat full KEEL on walk-forward
return per drawdown and Sortino AND on lockbox money ($120.6k vs $111.3k) at lower lockbox drawdown. Full
KEEL fails the lockbox veto on #382 (it only ties raw). Across both legs the learned model adds walk-forward
money at a disproportionate drawdown and nothing the fixed tilts do not already capture.

**The two candidates side by side (fixed tilts):** #382 + tilts makes more (WF 78.6 vs 70.2 %/yr, LB 103.2 vs
94.4) with more risk (WF DD $25.2k vs $19.4k, top size 4.5x vs 3.9x); #422 + tilts is the better return per
drawdown (WF 3.63 vs 3.12, LB 3.36 vs 3.13) and Sortino (5.48 vs 4.84). Owner call; nothing live changed.

---

## POST-HOC (2026-09-27, MANAGER audit #18) - the only clean window, and what it says

**No tilt or KEEL lockbox figure above is clean.** Every setting was chosen reading NOISE #243 / #304's
walk-forward AND lockbox on tapes ending 2026-08-12:

| setting | fixed | chosen on |
|---|---|---|
| compression 1.5x | v9, 2026-09-07 | TTM round-6 by-product; 2x rejected on #304's lockbox drawdown |
| Friday 1.5x | v11, 2026-09-08 | picked from five weekdays on WF AND lockbox EV R |
| FOMC-morning 0.5x | v12, 2026-09-09 | an a-priori hypothesis (the Fed calendar) with permutation + placebo support - the only one with independent evidence; the 0.5 level was the middle because deeper cuts read better on the lockbox |
| KEEL model (v1-v12) | 2026-09-02..09 | members, windows, shade and trust tuned reading both stretches |
| #382 / #422 cells | validates to 2026-07-16 | their own searches |

**Cut-off 2026-08-12.** Clean window = entries 2026-08-13 .. 2026-09-25 (the last bar), the 09-14 splice
session dropped: **27 trades**. `python tools/keel_clean_window.py`

| leg | arm | n | net $ | max DD $ | net / DD |
|---|---|---|---|---|---|
| #422 | raw | 27 | 6,932 | 4,633 | 1.50 |
| #422 | fixed tilts | 27 | 5,534 | 4,633 | 1.19 |
| #422 | KEEL seed 42 | 27 | 4,737 | 6,010 | 0.79 |
| #422 | KEEL 7-seed | 27 | 5,013 | 5,466 | 0.92 |
| #382 | raw | 27 | 5,726 | 5,878 | 0.97 |
| #382 | fixed tilts | 27 | 4,328 | 5,878 | 0.74 |
| #382 | KEEL seed 42 | 27 | 3,346 | 8,638 | 0.39 |
| #382 | KEEL 7-seed | 27 | 5,414 | 7,268 | 0.75 |

Raw leads on both legs, but every gap is smaller than one trade's P&L - 27 trades cannot separate these
arms. Round 60 and the 09-27 comparisons had already looked at data to 2026-09-16, so only 15 of these
trades are unseen by any comparison either (same ordering on #422; on #382 KEEL 7-seed edges raw, 2.12 vs 2.05).
**Conclusion: there is no clean evidence yet that any NOISE sizing layer beats raw.** The earlier
"fixed tilts beat KEEL" result still holds as a comparison on the walk-forward, but the walk-forward is
not clean either - the tilts were read on it. Only forward data can decide; the live NOISE leg's paper record
from 2026-09-24 is the clean test, and a shadow-scored raw / fixed-tilt / KEEL comparison on its fills
would settle it the same way as docs/PREREG_orb314_tree_forward_2026-09-27.md.
