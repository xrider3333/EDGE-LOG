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


def _c4_fired(r):
    return any("C4" in x for x in r["reasons"])


def test_c4_catches_a_one_trade_lockbox_bucket():
    """The artifact C4 exists for: one monster carries a small lockbox bucket."""
    rng = np.random.default_rng(31)
    n = 4000
    ts = pd.DatetimeIndex(pd.bdate_range("2012-01-02", periods=n, freq="B"))
    pnl = rng.normal(5, 200, n)
    lb = np.arange(n) >= int(n * 0.85)
    tag = np.zeros(n, bool); tag[rng.choice(np.where(lb)[0], 12, replace=False)] = True
    pnl[np.where(tag)[0][0]] = 90_000
    r = guard(pnl, ts, np.ones(n), tag, 1.5, ~lb, lb, perm=200, label="one trade")
    assert _c4_fired(r), r["report"]


def test_c4_does_not_fire_on_ordinary_small_buckets():
    """2026-09-24 calibration: the old 50%-of-net line failed ~73% of RANDOM 20-trade buckets on
    fat-tailed legs. Random tags on a fat-tailed leg must now trip C4 only at about its 5% rate."""
    fired_new = fired_old = 0
    for seed in range(40):
        rng = np.random.default_rng(100 + seed)
        n = 3000
        ts = pd.DatetimeIndex(pd.bdate_range("2012-01-02", periods=n, freq="B"))
        pnl = 150 * rng.standard_t(3, n) + 25           # fat tails, PF ~1.2 like the real legs
        lb = np.arange(n) >= int(n * 0.85)
        tag = np.zeros(n, bool); tag[rng.choice(np.where(lb)[0], 20, replace=False)] = True
        fired_new += _c4_fired(guard(pnl, ts, np.ones(n), tag, 1.5, ~lb, lb, perm=50, label="r"))
        fired_old += _c4_fired(guard(pnl, ts, np.ones(n), tag, 1.5, ~lb, lb, perm=50, label="r",
                                     c4="net50"))
    assert fired_new <= 6, fired_new                     # ~5% of 40 = 2; allow noise
    assert fired_old >= 16, fired_old                    # the defect this replaced, still measurable
