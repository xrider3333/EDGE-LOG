"""Fast synthetic checks for tools/pool_vs_crown.py.

Four things have to be right or the whole POOL vs CROWN report is wrong:
  1. equal-weight pooling is 1/N, and lines that step on different bars line up;
  2. drawdown of a pooled line is measured on the POOLED line, not averaged;
  3. the paired sign / signed-rank tests behave on cases with a known answer;
  4. the duplicate detector actually catches finalists that are the same bet.
No file, no network, no run cache -- every input below is made up on the spot.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import pool_vs_crown as P  # noqa: E402


# --- 1. equal-weight pooling maths -----------------------------------------

def test_equal_weight_pooling_is_one_over_n_and_aligns_offset_curves():
    # Two finalists that trade on DIFFERENT bars. Cumulative profit holds flat
    # between trades, so at bar 10 the first is already at +100 and the second has
    # not traded yet.
    a = [(0.0, 0.0), (10.0, 100.0), (30.0, 200.0)]
    b = [(0.0, 0.0), (20.0, -40.0), (30.0, 60.0)]

    grid, pooled = P.pool_curve([a, b])
    assert grid == [0.0, 10.0, 20.0, 30.0]
    # 1/N each: at bar 10 -> (100 + 0)/2, at bar 20 -> (100 - 40)/2, end -> (200+60)/2
    assert pooled == pytest.approx([0.0, 50.0, 30.0, 130.0])

    # The basket's end value is EXACTLY the average of the finalists' end values.
    # This is the arithmetic identity the report leans on: a 1/N basket cannot
    # out-earn "pick one at random", it IS that number.
    assert pooled[-1] == pytest.approx((a[-1][1] + b[-1][1]) / 2.0)

    # A finalist that traded nothing still takes its slice of the capital: pooling
    # two live lines but weighting for three holds back a third of the money.
    _, with_idle = P.pool_curve([a, b], n_weight=3)
    assert with_idle[-1] == pytest.approx(260.0 / 3.0)

    # Doubling up instead of averaging would be leverage; assert we do not.
    assert pooled[-1] != pytest.approx(a[-1][1] + b[-1][1])


# --- 2. drawdown of a pooled curve -----------------------------------------

def test_pooled_drawdown_is_measured_on_the_pooled_line():
    # Two finalists whose losing stretches fall in DIFFERENT places. Each alone digs
    # a 100-deep hole; averaged, the holes partly cancel.
    a = [(0.0, 0.0), (1.0, 100.0), (2.0, 0.0), (3.0, 120.0)]
    b = [(0.0, 0.0), (1.0, 0.0), (2.0, 100.0), (3.0, 0.0)]

    ga, va = P.pool_curve([a])
    gb, vb = P.pool_curve([b])
    dd_a = P.curve_stats(ga, va, 1.0, 1.0)["dd"]
    dd_b = P.curve_stats(gb, vb, 1.0, 1.0)["dd"]
    assert dd_a == pytest.approx(-100.0)
    assert dd_b == pytest.approx(-100.0)

    g, v = P.pool_curve([a, b])
    assert v == pytest.approx([0.0, 50.0, 50.0, 60.0])
    stats = P.curve_stats(g, v, 1.0, 1.0)
    assert stats["dd"] == pytest.approx(0.0)          # the holes cancelled outright
    assert stats["net"] == pytest.approx(60.0)
    # ... and it is strictly shallower than averaging the two drawdowns would say.
    assert abs(stats["dd"]) < abs((dd_a + dd_b) / 2.0)

    # Perfectly matched finalists get NO benefit: pooling two copies of one line
    # leaves the drawdown exactly where it was. This is the "same bet twice" case.
    g2, v2 = P.pool_curve([a, list(a)])
    assert P.curve_stats(g2, v2, 1.0, 1.0)["dd"] == pytest.approx(dd_a)

    # Dollars and annualising: half a year at x2 contract size doubles net and
    # drawdown, and return-over-drawdown annualises.
    g3, v3 = P.pool_curve([a])
    s3 = P.curve_stats(g3, v3, 0.5, 2.0)
    assert s3["net"] == pytest.approx(240.0)
    assert s3["dd"] == pytest.approx(-200.0)
    assert s3["mar"] == pytest.approx((240.0 / 0.5) / 200.0)


# --- 3. the paired tests ----------------------------------------------------

def test_paired_sign_and_signed_rank_tests():
    # All ten runs favour the first side -> sign test p = 2 * (1/2)^10.
    allpos = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    st = P.sign_test(allpos)
    assert st["n"] == 10 and st["wins"] == 10
    assert st["p"] == pytest.approx(2.0 / 1024.0)
    wx = P.wilcoxon(allpos)
    assert wx["r"] == pytest.approx(1.0)              # effect size pinned at +1
    assert wx["p"] < 0.01

    # Exact ties are dropped, not counted as wins for either side.
    assert P.sign_test([0.0, 0.0, 1.0, -1.0])["n"] == 2
    assert P.sign_test([0.0, 0.0, 0.0]) == {"n": 0, "wins": 0, "p": 1.0}

    # A dead heat: equal numbers of wins each way is not significant, and the
    # signed-rank effect size sits at zero.
    even = [1.0, -1.0, 2.0, -2.0, 3.0, -3.0]
    assert P.sign_test(even)["p"] == pytest.approx(1.0)
    assert P.wilcoxon(even)["r"] == pytest.approx(0.0)

    # The signed-rank test weighs the ORDER of the gaps, not their raw size: five
    # small wins against one huge loss still comes out positive (the loss can only
    # earn the top rank, not fifty times the weight) even though the plain average
    # of the differences is strongly negative. That bounded behaviour is exactly why
    # the report quotes it alongside the sign test rather than a paired t-test.
    lopsided = [1.0, 1.0, 1.0, 1.0, 1.0, -50.0]
    assert P.sign_test(lopsided)["wins"] == 5
    assert sum(lopsided) / len(lopsided) < 0.0
    wxl = P.wilcoxon(lopsided)
    assert wxl["r"] == pytest.approx((15.0 - 6.0) / 21.0)   # ranks 3,3,3,3,3 vs 6
    assert 0.0 < wxl["r"] < 1.0

    # Sign is direction-consistent.
    assert P.sign_test([-x for x in allpos])["wins"] == 0
    assert P.wilcoxon([-x for x in allpos])["r"] == pytest.approx(-1.0)


# --- 4. the duplicate-configuration detector --------------------------------

def test_duplicate_configuration_detector():
    ranges = {"stop": (1.0, 2.0), "len": (0.0, 100.0)}
    base = {"stop": 1.5, "len": 50.0, "mode": "atr"}
    twin = {"stop": 1.51, "len": 50.5, "mode": "atr"}   # a hair away = same bet
    far = {"stop": 2.0, "len": 100.0, "mode": "atr"}    # opposite end of the sweep

    d = P.param_distances([base, twin, far], ranges)
    assert d["n"] == 3 and d["pairs"] == 3
    assert d["n_frozen"] == 1 and d["n_varying"] == 2   # every finalist agrees on mode
    assert d["near_dupe_pairs"] == 1                    # only base/twin
    assert d["distinct_configs"] == 2                   # twin collapses into base
    assert d["min_dist"] < P.DUPE_TOL < d["mean_dist"]

    # Identical parameter sets are caught outright.
    d2 = P.param_distances([base, dict(base)], ranges)
    assert d2["exact_dupe_pairs"] == 1 and d2["distinct_configs"] == 1

    # Normalising by the SEARCHED span matters: with a narrow sweep the same two
    # settings are far apart, so we must not fall back to the finalists' own spread.
    wide = P.param_distances([base, far], {"stop": (0.0, 100.0), "len": (0.0, 10000.0)})
    assert wide["mean_dist"] < P.DUPE_TOL

    # And the check that cannot be argued with: finalists whose sealed-year line is
    # the same line took the same trades, whatever their settings say.
    a = [(0.0, 0.0), (5.0, 10.0), (9.0, 4.0)]
    dc = P.distinct_curves([a, list(a), [(0.0, 0.0), (5.0, -10.0), (9.0, 4.0)]])
    assert dc == {"n": 3, "distinct": 2, "identical_pairs": 1}
