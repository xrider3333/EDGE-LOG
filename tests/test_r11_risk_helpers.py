"""RISK r1 harness (tools/rocfrontier/r11_risk.py) - the statistics and the sparse book, on hand-checkable inputs.

The harness's own `smoke` runs the whole round on a synthetic world through the engine's leg runner (and shows the test has power and
does not pass a null world); these pin the pieces a verdict rests on: the drawdown path (peak from 0), CDaR95, the underwater periods
E3 ranks, the Diebold-Mariano / HLN read of R5, Newey-West OLS, the stationary bootstrap, and the entry-row rule of the sparse book.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "rocfrontier"))
import r11_risk as R  # noqa: E402


def test_drawdown_starts_from_zero_and_cdar_is_the_mean_of_the_worst_five_percent():
    x = np.array([-10.0, 5.0, 20.0, -30.0, 10.0] + [1.0] * 15)
    dd = R.ddpath(x)
    assert dd[0] == 10.0                                    # an opening loss is a drawdown (peak starts at 0)
    assert dd.max() == 30.0
    s = R.stats(x, pd.bdate_range("2021-01-04", periods=len(x)))
    assert s["cdar95"] == 30.0                              # ceil(5% of 20) = 1 worst value
    yrs = (pd.bdate_range("2021-01-04", periods=20)[-1] - pd.Timestamp("2021-01-04")).days / 365.25
    assert s["roc"] == pytest.approx(30.0 * (x.sum() / yrs) / 30.0)
    assert s["cdr"] == pytest.approx(30.0 * (x.sum() / yrs) / 30.0)


def test_underwater_periods_are_maximal_runs_ranked_by_depth():
    x = np.array([5.0, -3.0, -4.0, 10.0, -1.0, 2.0, -6.0, 1.0])
    u = R.underwater(x, pd.bdate_range("2022-03-01", periods=len(x)))
    assert [round(p["depth"], 9) for p in u] == [7.0, 6.0, 1.0]
    assert u[0]["peak"] == "2022-03-01" and u[0]["trough"] == "2022-03-03"


def test_dm_hln_reads_a_real_improvement_and_not_noise():
    rng = np.random.default_rng(3)
    better = 0.2 + rng.normal(0, 0.5, 1500)
    stat, p = R.dm_hln(better, 20, 19)
    assert p < 0.01 and stat > 0
    _, p0 = R.dm_hln(rng.normal(0, 0.5, 1500), 20, 19)
    assert p0 > 0.01


def test_newey_west_ols_recovers_coefficients():
    rng = np.random.default_rng(4)
    x = rng.normal(0, 1, 3000)
    y = 0.5 + 2.0 * x + rng.normal(0, 0.1, 3000)
    b, t = R.ols_nw(y, np.column_stack([np.ones(3000), x]), 10)
    assert b[0] == pytest.approx(0.5, abs=0.02) and b[1] == pytest.approx(2.0, abs=0.02) and t[1] > 100


def test_stationary_bootstrap_stays_in_range_with_the_mean_block_asked_for():
    rng = np.random.default_rng(5)
    ix = R.stationary_bootstrap(20000, 60, rng)
    assert ix.min() >= 0 and ix.max() < 20000
    jumps = np.mean(ix[1:] != (ix[:-1] + 1) % 20000)
    assert 1 / 75 < jumps < 1 / 48                          # ~ one jump every 60 rows


def test_the_sparse_book_sizes_each_trade_by_its_entry_row_and_reads_the_next_row_off_index():
    D = lambda s: np.datetime64(s, "D")
    rec = {  # trade 0: intraday Monday; trade 1: entered on a Sunday (off the business-day index), marked Mon, closed Tue
        "entry": np.array([D("2020-01-06"), D("2020-01-05")]), "exit": np.array([D("2020-01-06"), D("2020-01-07")]),
        "closed": np.array([100.0, 50.0]), "leg": np.array([0, 1]),
        "inc_t": np.array([0, 1, 1]), "inc_d": np.array([D("2020-01-06"), D("2020-01-06"), D("2020-01-07")]),
        "inc_v": np.array([100.0, 80.0, -30.0])}
    meta = [{"strategy": "A", "instrument": "NQ", "mult": 20.0, "weight": 1.0, "cost_pts": 0.5},
            {"strategy": "ENGUQ", "instrument": "NQ", "mult": 20.0, "weight": 1.0, "cost_pts": 0.783}]
    B = R.Book(rec, meta)
    assert B.index[B.erow[1]] == pd.Timestamp("2020-01-06")  # Sunday entry reads Monday's row
    m = np.ones(B.n)
    m[B.erow[1]] = 2.0                                         # the Monday row's multiplier
    out = pd.Series(B.sized(m), index=B.index)
    assert out.loc["2020-01-06"] == pytest.approx(2 * 100.0 + 2 * 80.0)   # both trades enter on the Monday row
    assert out.loc["2020-01-07"] == pytest.approx(2 * -30.0)
    assert np.allclose(B.sized(np.ones(B.n)), B.raw)
    assert pd.Series(B.sized_closed(np.ones(B.n)), index=B.index).loc["2020-01-07"] == 50.0
