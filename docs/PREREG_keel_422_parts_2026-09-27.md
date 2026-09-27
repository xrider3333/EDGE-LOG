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
