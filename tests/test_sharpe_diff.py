import math

import numpy as np
import pytest

from augur_engine import sharpe_diff as SD


def test_identical_series_have_no_difference():
    x = np.random.default_rng(1).normal(0.05, 1.0, 600)
    r = SD.sharpe_diff_test(x, x.copy(), b=10, M=99)
    assert r["diff"] == 0.0 and r["p_boot"] == 1.0 and r["p_hac"] == 1.0


def test_a_clear_difference_is_found_both_ways():
    rng = np.random.default_rng(2)
    common = rng.normal(0.0, 1.0, 2000)
    x = 0.15 + common + rng.normal(0.0, 0.3, 2000)          # same shocks, a real per-day edge
    y = common + rng.normal(0.0, 0.3, 2000)
    r = SD.sharpe_diff_test(x, y, b=20, M=499)
    assert r["diff"] > 0 and r["p_boot"] < 0.01 and r["p_hac"] < 0.01
    assert r["ci_boot"][0] > 0 and r["ci_hac"][0] > 0


def test_hac_se_matches_the_iid_formula_on_iid_normal_data():
    rng = np.random.default_rng(3)
    T = 20000
    x, y = rng.normal(0.1, 1.0, T), rng.normal(0.0, 1.0, T)
    s1, s2 = 0.1, 0.0
    iid = math.sqrt(((1 + s1 ** 2 / 2) + (1 + s2 ** 2 / 2)) / T)      # independent series: the two variances add
    assert SD.hac_se(x, y) == pytest.approx(iid, rel=0.1)
    assert SD.hac_se(x, y, prewhiten=False) == pytest.approx(iid, rel=0.1)


def test_hac_se_widens_when_the_differences_are_autocorrelated():
    rng = np.random.default_rng(4)
    T = 5000
    e = rng.normal(0.0, 1.0, T)
    ar = np.empty(T)
    ar[0] = e[0]
    for t in range(1, T):
        ar[t] = 0.6 * ar[t - 1] + e[t]
    y = rng.normal(0.0, 1.0, T)
    assert SD.hac_se(ar, y) > 1.3 * SD.hac_se(rng.permutation(ar), y)


def test_bootstrap_size_is_near_nominal_under_the_null():
    rng = np.random.default_rng(5)
    rej = 0
    n = 60
    for k in range(n):
        x, y = rng.standard_t(5, 800) * 0.5, rng.standard_t(5, 800) * 0.5      # equal (zero) Sharpe, fat tails
        rej += SD.sharpe_diff_test(x, y, b=10, M=199, seed=k)["p_boot"] < 0.05
    assert rej <= 9                                          # 5% of 60 = 3; binomial 99.9% bound ~ 9


def test_rejects_unpaired_input():
    with pytest.raises(ValueError):
        SD.sharpe_diff_test(np.zeros(100), np.zeros(99))
    with pytest.raises(ValueError):
        SD.sharpe_diff_test(np.ones(30), np.ones(30), b=20)
