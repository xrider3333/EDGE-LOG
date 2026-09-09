"""The tilt guard must pass a planted real edge and reject leverage, a one-trade gain,
and a candidate whose placebo matches it. Synthetic data, so it is fast and deterministic."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from tilt_guard import _selftest, guard  # noqa: E402


def test_selftest_suite_passes():
    assert _selftest() == 0


def test_a_cut_of_a_genuinely_worse_bucket_passes():
    rng = np.random.default_rng(11)
    n = 3000
    ts = pd.DatetimeIndex(pd.bdate_range("2013-01-02", periods=n, freq="B"))
    pnl = rng.normal(50, 800, n)
    tag = np.zeros(n, bool)
    tag[rng.choice(n, 250, replace=False)] = True
    pnl[tag] = rng.normal(-650, 800, tag.sum())
    wf = np.arange(n) < int(n * 0.8)
    r = guard(pnl, ts, np.ones(n), tag, 0.5, wf, ~wf, perm=300, label="planted")
    assert r["passed"], r["report"]


def test_flat_leverage_is_rejected():
    rng = np.random.default_rng(12)
    n = 3000
    ts = pd.DatetimeIndex(pd.bdate_range("2013-01-02", periods=n, freq="B"))
    pnl = rng.normal(50, 800, n)
    tag = np.zeros(n, bool)
    tag[rng.choice(n, 250, replace=False)] = True
    wf = np.arange(n) < int(n * 0.8)
    r = guard(pnl, ts, np.ones(n), tag, 1.5, wf, ~wf, perm=300, label="leverage")
    assert not r["passed"]


def test_report_is_printable_and_names_its_reasons():
    rng = np.random.default_rng(13)
    n = 1200
    ts = pd.DatetimeIndex(pd.bdate_range("2015-01-02", periods=n, freq="B"))
    pnl = rng.normal(10, 300, n)
    tag = np.zeros(n, bool)
    tag[rng.choice(n, 100, replace=False)] = True
    wf = np.arange(n) < int(n * 0.8)
    r = guard(pnl, ts, np.ones(n), tag, 1.25, wf, ~wf, perm=200, label="x")
    assert "TILT GUARD" in r["report"] and "VERDICT" in r["report"]
    assert r["passed"] or r["reasons"]


def test_shift_null_rejects_a_condition_that_is_only_shaped_right():
    """A condition with the right shape but pointed at nothing must fail the shift null."""
    rng = np.random.default_rng(21)
    n = 4000
    ts = pd.DatetimeIndex(pd.bdate_range("2012-01-02", periods=n, freq="B"))
    pnl = rng.normal(40, 700, n)
    tag = np.zeros(n, bool)                      # a clustered condition, aligned with nothing
    i = 0
    while i < n:
        i += int(rng.integers(5, 40))
        tag[i:i + int(rng.integers(3, 12))] = True
    wf = np.arange(n) < int(n * 0.8)
    r = guard(pnl, ts, np.ones(n), tag, 1.5, wf, ~wf, permute="shift", perm=300, label="shaped only")
    assert not r["passed"]


def test_shift_null_accepts_a_condition_that_really_picks_the_trades():
    rng = np.random.default_rng(22)
    n = 4000
    ts = pd.DatetimeIndex(pd.bdate_range("2012-01-02", periods=n, freq="B"))
    pnl = rng.normal(40, 700, n)
    tag = np.zeros(n, bool)
    i = 0
    while i < n:
        i += int(rng.integers(5, 40))
        tag[i:i + int(rng.integers(3, 12))] = True
    pnl[tag] = rng.normal(-600, 700, tag.sum())   # the tagged trades really are worse
    wf = np.arange(n) < int(n * 0.8)
    r = guard(pnl, ts, np.ones(n), tag, 0.5, wf, ~wf, permute="shift", perm=300, label="real condition")
    assert r["passed"], r["report"]
