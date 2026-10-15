# SUPERSCALPER r2b - the outside-RTH / RTH split on 2023 - RESULT: "it does not" (TV, 2026-10-15)

Prereg `docs/PREREG_tv_superscalper_r2b_session_2026-10-15.md` (LF sha256 1166c03e..., witness prereg/tv-ssexplore2-1015 @ b6da51c9,
pushed before the run); harness `tools/superscalper_explore_r2b.py` (ef47c3cc...; r2 harness 26a2f9aa... and port 8566c2c1...
checked at start). NQ 1m ETH no-adjust 2023, file defaults (IMPROVED_R1), close_rule 'any' decomposition tagged at the signal bar
('any' net total 2,005.9 pt = r2 E0's 'fifo' total). Cost 0.706. One-year reads (all flagged 1 EPISODE).

| part (signal bar, New York) | trades | win | avg win / loss (net pt) | net PF | stress +0.25 | ROC@30k | DD5 @30k | DD% peak | Sortino |
|---|---|---|---|---|---|---|---|---|---|
| all | 2,311 | 56.9% | 22.53 / 27.73 | 1.073 | 1.051 | 29.3 | $15.9k | 26.2% | 1.15 |
| RTH 09:30-15:59 | 597 | 29.8% | 49.09 / 17.25 | 1.209 | 1.186 | 65.3 | $15.6k | 28.1% | 2.63 |
| outside RTH | 1,714 | 66.3% | 18.37 / 35.35 | 1.024 | 1.003 | 7.0 | $10.3k | 25.6% | 0.30 |
| (info) W1 open 09:30-10:59 | 176 | 28.4% | 79.82 / 21.44 | 1.477 | 1.456 | 114.2 | $19.1k | 28.2% | 3.47 |
| (info) W2 midday 11:00-13:59 | 201 | 35.8% | 29.23 / 17.19 | 0.949 | 0.928 | -8.5 | $12.4k | 27.7% | -0.43 |
| (info) W3 close 14:00-15:59 | 220 | 25.5% | 47.17 / 14.07 | 1.145 | 1.119 | 29.6 | $17.4k | 27.5% | 1.05 |

- VERDICT (fixed rule: outside-RTH net PF >= 1.00 AND > RTH net PF): **it does not.** 2023 is the mirror of 2024 - RTH carried 2023
  (PF 1.21) and lost in 2024 (0.94-0.97 per window); outside RTH carried 2024 (1.085) and barely broke even in 2023 (1.024).
- Read: the session effect flips sign between the two development years, so neither side is a stable edge on this evidence. As
  pre-registered no filter is added by hand; the session knob goes into the validate's search space (prereg Amendment 5 on
  docs/PREREG_tv_superscalper_r1_2026-10-14.md) and the 900-trial walk-forward decides.
