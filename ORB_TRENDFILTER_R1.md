# ORB TRENDFILTER r1 (T05): result (2026-10-18)

**Setup:**
- Prereg: `docs/PREREG_orb_trendfilter_r1_2026-10-18.md` (LF sha256 47dfcd13..., branch prereg/orb-trendfilter-r1 = d3cacc71, pushed before the run,
  posted to MANAGER at launch, #1459). Fixed after a pre-freeze review (raw-price denominator, F- renamed, power lines), see #1459.
- Harness: `tools/orb_trendfilter_r1.py` (LF sha256 77245249...). It checked the note, `augur_engine/sharpe_diff.py` (704559490f7b...),
  the leg's params, both masters and the pre-WF theta at start.
- Output: `C:\EdgeLog\_anatomy_cache\orb_trendfilter\t05_r1_result.json` + `t05_r1_stdout.txt`.
- Scope: #314 (ORB_R6 on NQ 5m RTH, 0.533 pt, one contract). Scored trades enter 2016-07-01 .. 2025-06-27 (WF). Lockbox unread. Report-only.

**The question:** does the trend-day catcher, used as a filter on #314's entries, beat #314 bare?
- The catcher is the move so far at the fill: m = side x (fill - first RTH open) / the raw first open.
- Theta 0.584% = the pre-WF upper quartile of m.

| Arm | ROC @ $30k | DD5 (at $30k) | DD % from peak (at $30k) | Sortino | Trades a year | Gross a trade |
|---|---|---|---|---|---|---|
| A #314 bare | 36.22 | $22,382 | 17.1 | 2.26 | 142.5 | 12.76 pt |
| F+ CATCHER (keep m >= theta) | 25.51 | $22,351 | 17.7 | 1.86 | 49.8 | 22.85 pt |
| F- NARROW OPEN (skip m >= theta) | 16.62 | $21,341 | 19.5 | 1.29 | 92.7 | 7.32 pt |
| W- OR-width control (report-only) | 24.47 | $24,144 | 14.0 | 1.42 | 87.4 | 7.71 pt |

- A, F+ and F- are driven by one episode (worst drawdown 1.34 / 1.34 / 1.41 x DD5). W- is not (1.24 x).
- Gross 7.3-22.9 pt a trade vs cost 0.533 pt: every arm clears gross >= cost.

**The paired read (vs A; 95% Ledoit-Wolf intervals, two-sided p):**

| Arm | Sharpe vs A | Diff | 95% | p | MDE80 | ROC lead (90%, report-only) |
|---|---|---|---|---|---|---|
| F+ | 0.96 vs 1.22 | -0.26 | -0.64 .. +0.12 | 0.18 | 0.54 | -10.7 (-30.4 .. +8.0) |
| F- | 0.75 vs 1.22 | -0.47 | -0.99 .. +0.05 | 0.08 | 0.73 | -19.6 (-44.6 .. -0.8) |
| W- | 0.78 vs 1.22 | -0.44 | -0.93 .. +0.06 | 0.08 | 0.68 | -11.8 (-42.9 .. +3.8) |

- **Per trade:** fills with m >= theta made +0.168% a trade (448 trades) vs +0.060% (833). Diff +0.108% (95% -0.011 .. +0.228, p 0.08).
- **Money days:** 16 of the 26 WF money-day trades had m >= theta (pre-WF: 9 of 26).

**Verdict (pre-set): NO FILTER LIFT.** Both arms read NOT SHOWN (Sharpe intervals cross 0, so not REVERSED). Both fail clause 1
(Sharpe diff < 0), clause 2 (ROC below A: -10.7 / -19.6) and clause 3 (one episode: 1.34 / 1.41 x DD5). Clause 4, MANAGER's bar, passes
on the prereg's assumed MDL band |rho_dd| < 0.15 (ROC >= 15; rho_dd not measured).

**What it means:**
- **The pre-WF prior reversed sign on WF (WF p 0.08, interval includes 0).** Pre-WF, the late-move trades lost (-0.099% a trade vs
  +0.041%). On WF they earned the most per trade (+0.168% vs +0.060%). The F- prior (+0.60 Sharpe) sat under the WF MDE80 (0.64
  forecast, 0.73 realised) and did not hold on WF (-0.47).
- **Neither side of this feature lifts #314.** Dropping the high-m 35% throws away the best trades a trade. Dropping the rest throws away
  2/3 of the trades. Either way the money falls faster than the drawdown. (One feature at one theta: not a claim about every filter.)
- **m mostly measures the opening-range width** (corr 0.83 pre-WF, 0.88 WF). On the skip side the width gate W- matches F- on Sharpe
  (diff -0.44 vs -0.47) and beats it on ROC and DD %, so skipping on m adds nothing a width gate would not. The keep side (F+) had no
  width control. This repeats the legal-base OR-width gate that was already DEAD.
- **Side note, not a finding:** W- is the only arm that is not one episode, at the lowest DD % (14.0). It loses 12 ROC points, though. A
  report-only row, not a candidate.

Nothing changes. #314 untouched. The catcher stays a harm-monitor read, not a filter.
