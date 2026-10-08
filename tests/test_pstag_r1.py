"""PS-TAG r1 (tools/pstag_r1.py): the statistics, on synthetic data only (the real read needs the masters)."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

PT = pytest.importorskip("pstag_r1")


def test_july_june_year():
    assert PT.jy("2016-07-01") == 2016 and PT.jy("2017-06-30") == 2016 and PT.jy("2017-07-03") == 2017


def test_spearman_matches_pearson_of_average_ranks():
    x = np.array([1, 2, 2, 3, 5, 4.0])
    y = np.array([10, 20, 15, 30, 50, 40.0])
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    assert PT.spearman(x, y) == pytest.approx(np.corrcoef(rx, ry)[0, 1])
    assert np.isnan(PT.spearman(np.ones(5), np.arange(5.0)))
    assert np.isnan(PT.spearman(np.arange(2.0), np.arange(2.0)))


def test_null_keeps_each_group_and_centres_on_zero():
    rng = np.random.default_rng(1)
    n = 600
    g = np.repeat([2016, 2017, 2018], n // 3)
    s = rng.integers(0, 7, n) / 6.0
    r = rng.normal(size=n) + 0.0 * s
    nr = PT.null_rho(s, r, g, draws=300, seed=7)
    assert abs(np.median(nr)) < 0.02 and 0.02 < nr.std() < 0.06
    assert np.array_equal(nr, PT.null_rho(s, r, g, draws=300, seed=7))        # seeded


def test_within_group_shuffle_cannot_break_a_pure_year_effect():
    """score and R both = the year: a within-year shuffle keeps rho at its real value (the null keeps year effects)"""
    g = np.repeat([0, 1, 2], 50)
    s = g.astype(float)
    r = g.astype(float) + 0.0
    real = PT.spearman(s, r)
    nr = PT.null_rho(s, r, g, draws=50, seed=3)
    assert np.allclose(nr, real)


def test_informative_points_exclude_the_constant_ones():
    for side in ("LONG", "SHORT"):
        assert not set(PT.INFORMATIVE[side]) & set(PT.CONSTANT[side])
        assert len(PT.INFORMATIVE[side]) == 6 and "ma200_10s" not in PT.INFORMATIVE[side]
    assert "y_high" in PT.INFORMATIVE["LONG"] and "y_low" in PT.INFORMATIVE["SHORT"]
