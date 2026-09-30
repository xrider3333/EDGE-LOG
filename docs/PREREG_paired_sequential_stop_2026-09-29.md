# PRE-REGISTRATION — paired sequential stop for the forward shadow tests (2026-09-29)

Owner YES via MANAGER (inbox #27, 2026-09-29). Written before any forward shadow trade was read. It ADDS an early
stop to three tests; their written rules stay the final check:
docs/PREREG_noise_shadow_forward_2026-09-28.md, docs/PREREG_orb314_tree_forward_2026-09-27.md,
docs/PREREG_ttm458_keel_shadow_2026-09-28.md (and Frontier's "#463 + TTM #458 KEEL" book line, below).
Scorer: tools/paired_seq_stop.py (read_pair); constants below are frozen in that file.

## Why a paired test
Each shadow arm and its twin trade the SAME fills; only the size differs. Judging the per-trade difference
removes the market noise both arms share, so a real difference shows up in far fewer trades than two separate
equity curves need.

## The difference (tests aim, not leverage)
For forward trade i: d_i = (m_arm_i - c x m_twin_i) x u_i, where u_i = the trade's actual fill P&L on one base
unit, m = each side's size multiplier (uncapped, as each test already logs; 0 for a skipped trade), and c = the
arm's mean size relative to its twin over the WALK-FORWARD stretch of the book-leg exports (C:\EdgeLog\book_legs).
Subtracting c means an arm that is only bigger scores zero; it must put its size on the better trades.

## When to look and when to stop
- Looks at forward trade 20, 30, 40, ... (every 10), up to each test's own end point.
- t = mean(d) / (sd(d) / sqrt(n)) over all forward trades so far.
- EARLY FAIL: t <= -B, and t is still <= -2.0 without the single most negative d. That arm is dead; logging it
  can stop (owner / MANAGER call).
- EARLY PASS: t >= +B, and t is still >= +2.0 without the single largest d. The test's written final rule is
  then read immediately on the trades so far (with its trade minimum waived only for that early read); if it
  passes too, the arm goes to MANAGER as a candidate, otherwise the test simply continues.
- Neither boundary crossed: the written final rule decides at its written end point, unchanged.
- B is set per pair so that re-drawing the walk-forward differences with their mean removed crosses a boundary
  (either side) at most 5% of the time over the test's full length (4,000 draws, seed 20260929).

| test | arm vs twin | c | B | false stops | WF paired t (for reference) |
|---|---|---|---|---|---|
| NOISE (150 trades) | P #382 + KEEL vs A1 #382 plain | 1.2447 | 3.00 | 1.8% | +2.01 |
| NOISE | A3 #422 + fixed tilts vs A2 #422 plain | 1.1394 | 3.75 | 3.2% | +4.31 |
| NOISE | A4 #422 + KEEL vs A2 #422 plain | 1.2290 | 3.00 | 4.6% | +3.20 |
| ORB tree (120 trades) | tree HYBRID DD vs ORB #314 raw | 1.0463 | 3.00 | 0.6% | +0.81 |
| TTM KEEL (50 trades) | K #458 + KEEL vs R #458 raw | 1.8145 | 3.50 | 4.7% | +1.56 |

The walk-forward t column is context only: it was read on data every setting had already seen (NOISE tilts and
KEEL were tuned reading WF), so it is NOT evidence; only forward trades count.

## Frontier's "#463 + TTM #458 KEEL" book line (Frontier inbox #25; live from 2026-09-29)
The book line differs from #463 only on TTM trades, so its difference series IS the TTM pair above: the TTM KEEL
paired stop fires for both. Final check at the TTM test's 50-trade verdict: the book with the KEEL leg must beat
#463 on ROC %/yr at a $30k worst drawdown (valued daily) AND on daily Sortino over the same forward days, and
stay ahead without its single best TTM trade. Book days without a TTM trade are identical in both lines.

## ADDENDUM 2026-09-30 - Frontier's two new #463 shadow lines (Frontier inbox #28), before any forward day was read
Frontier's own reads (C:\EdgeLog\_anatomy_cache\adopt449\PREREG_SHADOWS_0929.txt) stay the verdict.
- **AG (1.5x on ORB #234 / NOISE #422 trades entering while the other leg is open the same way):** paired early
  stop on EVERY forward ORB and NOISE trade in the book, d = (m - c) x trade $, c = 1.1793 (walk-forward
  2016-06-30 .. 2025-07-16 mean of m; 35.9% of 4,250 trades tilted). Looks every 10 trades from 20, up to 279
  trades (= Frontier's 100-tilted read at the walk-forward rate); boundary |t| >= 3.00 (false stops 2.1% when
  sizes are drawn independently of outcomes), ex-extreme check 2.0. Driver: tools/ag_paired_stop.py.
  Context only, not evidence: the walk-forward paired t is +0.11, i.e. on the walk-forward stretch the 1.5x
  trades are no better per dollar than the rest once the extra size is removed.
- **VT (whole book sized by its own 20-day volatility):** NO paired stop. Its claimed value is a smaller
  drawdown in stress, which a mean-difference test cannot see; an early FAIL in calm months would kill a
  working tail hedge. VT keeps Frontier's 12-month read only.
