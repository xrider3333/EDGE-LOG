# SUPERSCALPER r1 - improvement round (OUR PORT, 2024 development year) - RESULT: IMPROVED defaults (TV, 2026-10-14)

Prereg `docs/PREREG_tv_superscalper_r1_2026-10-14.md`, Amendments 2-4 (LF sha256 bd316e49..., witness branch
prereg/tv-superscalper-1014 @ 56ca4d9b, pushed before the grid ran). Harness `tools/superscalper_improve_r1.py` (LF sha256
5f6ffb32..., checked the prereg sha at start: OK), port `MISC_SUPERSCALPER_1_0.py` at 63b8a5e5... (witness). NQ 1-minute ETH
no-adjust (master id 34), 2024-01-01 .. 2024-12-31, cost 0.706 points a round trip, intrabar 'worst', VIX = the pinned derived
file. 216 cells, 4 worker processes, 593 s. Lockbox unread. Everything here is OUR PORT, not the published script (Stage 0 FAIL).

## The two rows (NET points per trade; NOISE #123 asked for the baseline beside the pick)
| cell | trades | win rate | avg win | avg loss | net PF | net points | net PF at +0.25 pt |
|---|---|---|---|---|---|---|---|
| as-ported (cap off, stop x1.0, target x1.0, no time-out, no breakeven, no VIX) | 2,718 | 68.8% | 14.84 | 33.97 | 0.962 | -1,104 | 0.939 |
| CHOSEN: target x2.0, breakeven at +1.0 R, daily VIX (cap off, stop x1.0, no time-out) | 2,633 | 59.7% | 26.16 | 36.88 | 1.051 | +1,997 | 1.034 |

- Selection (Amendment 3): net PF >= 1.0 AND the median net PF of the cell's one-step neighbours > 0.962. The chosen cell's
  neighbour median is 0.999 -> adopted. 20 of 216 cells have net PF >= 1.0.
- These become the file defaults (`IMPROVED_R1`); the as-ported values stay available as `AS_PORTED_OURS` (tests pin both).

## What moved it (median net PF over all 216 cells, per knob value)
- Target scale: 1.0 = 0.916, 1.5 = 0.939, 2.0 = 0.970 - the only axis with a clear effect (wider targets pay).
- The author's 3-ATR stop cap, applied: off = 0.958, 3.0 = 0.917 - capping the stops made it WORSE (NOISE's E1 hypothesis rejected).
- Stop scale 0.5 / 0.75 / 1.0 = 0.941 / 0.936 / 0.955; time-out 0 / 30 / 90 = 0.953 / 0.937 / 0.950; breakeven 0 / 1.0 = 0.948 / 0.939.
- Daily VIX vs none: 0.947 vs 0.944, and the top cell differs from its no-VIX twin by 0.001 PF (1 trade) - the VIX vote barely acts.
- Top 8 cells all have target x2.0 and no cap; the top two are the same exits with and without VIX (1.051 / 1.050).

## Reading
- Best of 216 on ONE year: optimistic by construction. The edge is thin (net PF 1.05; +0.76 points a trade after the 0.706 cost) and the
  plateau is just at break-even (neighbour median 0.999). The 900-trial Auto-Validate's walk-forward and lockbox decide; 2024 sits
  inside its walk-forward window, so its WF read is printed with the 2024 fold apart and the chain without it.
- Prior unchanged (NOISE, STRATEGY-BEATING): 5-10% that the validate's WF clears ROC 15.

## Runtime guard (Amendment 4)
- One full 9-year optimize-window trial: 95 s, peak 4.4 GB (before the memory edit it exhausted free RAM). Validate estimate on
  today's load: ~3 days (Stage A 900 trials in one process, then 2 x 8 walk-forward folds x 900 trials in 3 processes). No trial cut.
