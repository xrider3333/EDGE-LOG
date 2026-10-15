# SUPERSCALPER r2c - which RTH hours carry it, and +1 tick - RESULT (TV, 2026-10-15)

Prereg `docs/PREREG_tv_superscalper_r2c_rth_hours_2026-10-15.md` (LF sha256 7f3caabe..., witness prereg/tv-ssexplore3-1015 @ 6e63a876,
pushed before the run); harness `tools/superscalper_explore_r2c.py` (f7ab2f08...; r2 harness 26a2f9aa... and port b8ef032f... checked).
PARITY GATE passed: the session-knob port at defaults reproduces r2b's 2023 decomposition exactly (2,311 trades, 2,005.9 net pt).
Descriptive only. NQ 1m ETH no-adjust, file defaults, close_rule 'any', tagged at the signal bar (New York). One-year reads.

## At the owner-rule cost (0.706 pt)
| year / hours | trades | win | avg win / loss | net PF | net pt | ROC@30k | DD5 @30k | DD% peak | Sortino |
|---|---|---|---|---|---|---|---|---|---|
| 2023 RTH all | 597 | 29.8% | 49.09 / 17.25 | 1.209 | +1,512 | 65.3 | $15.6k | 28.1% | 2.63 |
| 2023 H1 09:30-10:29 | 139 | 30.2% | 82.30 / 21.21 | 1.680 | +1,399 | 120.4 | $18.2k | 27.6% | 4.48 |
| 2023 H2 10:30-14:59 | 335 | 31.3% | 36.74 / 16.60 | 1.010 | +39 | 2.2 | $10.2k | 27.6% | 0.11 |
| 2023 H3 15:00-15:59 | 123 | 25.2% | 45.90 / 14.67 | 1.055 | +74 | 9.2 | $22.4k | 26.6% | 0.31 |
| 2024 RTH all | 624 | 26.6% | 56.42 / 21.40 | 0.956 | -434 | -6.9 | $7.4k | 26.8% | -0.52 |
| 2024 H1 09:30-10:29 | 136 | 24.3% | 94.04 / 29.83 | 1.010 | +31 | 0.7 | $7.4k | 25.6% | 0.06 |
| 2024 H2 10:30-14:59 | 361 | 28.8% | 45.19 / 18.96 | 0.965 | -173 | -3.8 | $9.8k | 25.5% | -0.32 |
| 2024 H3 15:00-15:59 | 127 | 22.8% | 53.91 / 18.93 | 0.843 | -292 | -11.5 | $30.0k* | 30.0%* | -1.01 |

\* 2024 H3 only fell: its worst drawdown is the whole stretch, so at the $30k sizing DD5 and DD% sit at the cap.

## At +1 tick (0.956 pt)
| year | RTH all | H1 | H2 | H3 |
|---|---|---|---|---|
| 2023 net PF (ROC@30k) | 1.186 (56.3) | 1.655 (115.0) | 0.988 (-2.5) | 1.031 (5.3) |
| 2024 net PF (ROC@30k) | 0.941 (-8.8) | 0.999 (-0.1) | 0.947 (-5.7) | 0.828 (-12.5) |

## Reading (fixed rules)
- **No hour carries it in both years** (rule: net PF >= 1.10 with >= 100 trades in 2023 AND 2024). The 2023 RTH edge is almost all
  the first hour (H1 = 93% of RTH net points); in 2024 the same hour is flat (1.01) and every other RTH hour loses.
- **+1 tick**: 2023 RTH and H1 / H3 survive; nothing survives in 2024. The scalper's dev-year record stays one good year and one
  bad one, now down to a single hour of a single year.
- Nothing is acted on here: the validate's own session_filter search (Amendment 5) is the only session choice, and per NOISE #138 /
  MANAGER #139 its read prints the per-fold session picks if the crown is not 'all'.
