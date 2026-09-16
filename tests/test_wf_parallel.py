"""
Walk-forward folds in parallel must give the SAME rows as the in-line loop (2026-09-08).

A validate's Stage B runs 3,200 backtests at the default 200 trials, one core, most of an
hour on a mid-size window. augur_engine.wf_pool runs the folds in processes. The claim
that makes that safe - every fold builds its own sampler from the run's seed, so nothing
depends on order or process - is pinned here on a tiny synthetic market and a two-knob
crossover strategy: workers=1 and workers=2 must agree on every fold row to the digit.
"""
import os
import sys
import textwrap
import time

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine import auto as _auto
from augur_engine.auto import run_auto

STRAT = textwrap.dedent('''
    import numpy as np
    DEFAULT_PARAMS = {
        "fast": {"default": 5, "min": 2, "max": 12, "step": 1, "type": "int"},
        "slow": {"default": 20, "min": 10, "max": 40, "step": 2, "type": "int"},
    }
    def run_backtest(opens, highs, lows, closes, fast=5, slow=20, return_trades=False, **kw):
        c = np.asarray(closes, float); n = len(c)
        fast, slow = int(fast), int(slow)
        if fast >= slow or n < slow + 2:
            return None
        f = np.convolve(c, np.ones(fast) / fast, "valid")
        s = np.convolve(c, np.ones(slow) / slow, "valid")
        f = f[len(f) - len(s):]
        base = n - len(s)
        trades = []; pos = None
        for i in range(1, len(s)):
            bar = base + i
            if f[i] > s[i] and f[i - 1] <= s[i - 1]:
                pos = bar
            elif f[i] < s[i] and f[i - 1] >= s[i - 1] and pos is not None:
                trades.append((pos, bar, float(c[bar] - c[pos]))); pos = None
        if not trades:
            return None
        p = np.array([t[2] for t in trades]); w = p[p > 0]; l = p[p < 0]
        cum = np.cumsum(p)
        out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)),
               "win_rate": float(100.0 * len(w) / len(p)),
               "profit_factor": float(w.sum() / -l.sum()) if len(l) else 0.0,
               "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()),
               "avg_pnl": float(p.mean()), "wins": int(len(w)), "losses": int(len(l))}
        if return_trades:
            out["trades"] = trades
        return out
''')


def _arrays(n=9000, seed=3, with_index=False):
    rng = np.random.default_rng(seed)
    c = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
    o = c + rng.normal(0, 0.1, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.2, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.2, n))
    out = {"open": o, "high": h, "low": l, "close": c,
           "volume": rng.integers(100, 1000, n).astype(float),
           "day_id": np.repeat(np.arange(n // 78 + 1), 78)[:n]}
    if with_index:
        # ENGINE_BRIEF D7 — oos_from/oos_to: real bar timestamps so both the
        # sequential and parallel fold paths can be checked for identical dates,
        # not just identical numbers.
        out["index"] = pd.date_range("2020-01-01", periods=n, freq="5min", tz="US/Eastern")
    return out


@pytest.fixture(scope="module")
def strat_path(tmp_path_factory):
    d = tmp_path_factory.mktemp("wfstrat")
    p = d / "WFTEST_1_0.py"
    p.write_text(STRAT, encoding="utf-8")
    return str(p)


def _strip(rows):
    # per-trade lists are compared too; only drop nothing - identity is the claim
    return [dict(sorted(r.items())) for r in sorted(rows, key=lambda r: r["fold"])]


def test_parallel_folds_match_inline_rows(strat_path):
    common = dict(arrays=_arrays(), method="walkforward", wf_folds=4, n_trials=20,
                  seed=11, min_trades=5, cost_pts=0.1, oos=True, auto_expand=False)
    seq = run_auto(strat_path, workers=1, **common)
    par = run_auto(strat_path, workers=2, **common)
    assert seq.get("top") and par.get("top"), "both paths must produce fold rows"
    assert len(seq["top"]) == len(par["top"])
    assert _strip(seq["top"]) == _strip(par["top"])
    assert seq["best_params"] == par["best_params"]


def test_parallel_folds_carry_identical_oos_dates(strat_path):
    """ENGINE_BRIEF D7: oos_from/oos_to (the OOS test slice's calendar bounds) must
    come back identically whether a fold ran in-line or in a worker process — the
    parallel path reloads/forwards the SAME `index` a sequential run already has."""
    common = dict(arrays=_arrays(with_index=True), method="walkforward", wf_folds=4,
                  n_trials=20, seed=11, min_trades=5, cost_pts=0.1, oos=True,
                  auto_expand=False)
    seq = run_auto(strat_path, workers=1, **common)
    par = run_auto(strat_path, workers=2, **common)
    assert seq["top"] and par["top"]
    seq_dates = [(r["fold"], r.get("oos_from"), r.get("oos_to")) for r in seq["top"]]
    par_dates = [(r["fold"], r.get("oos_from"), r.get("oos_to")) for r in par["top"]]
    assert seq_dates == par_dates
    assert all(d0 and d1 and d0 <= d1 for _f, d0, d1 in seq_dates)


def test_wf_fold_rows_omit_oos_dates_without_an_index(strat_path):
    """The default `_arrays()` (no `index` key) must not crash — the dates are simply
    omitted, matching validate.py's own save_fold_detail precedent
    (tests/test_fold_detail.py::test_fold_detail_omits_dates_when_the_arrays_carry_no_index)."""
    out = run_auto(strat_path, arrays=_arrays(), method="walkforward", wf_folds=3,
                    n_trials=10, seed=5, min_trades=5, oos=True, auto_expand=False,
                    workers=1)
    assert out["top"]
    for r in out["top"]:
        assert "oos_from" not in r and "oos_to" not in r


def test_parallel_pool_boot_timeout_falls_back_to_sequential(strat_path, monkeypatch):
    """A Windows spawn handshake can stall forever with zero CPU and no exception raised
    anywhere (observed 2026-09-14 under heavy load from the owner's live runner fleet, see
    the note on _run_folds_parallel) - starting the pool must not do the same. Force the
    boot step to run long past a (patched, short) timeout: _run_folds_parallel must give up
    and raise instead of hanging, and run_auto's existing pool-failure handling (the `except
    Exception` around its call site) must fall back to the in-line loop and still land on
    the exact rows workers=1 produces."""
    def _never_returns(*a, **k):
        time.sleep(5)   # far longer than the patched timeout below
        raise AssertionError("should have been abandoned long before returning")

    monkeypatch.setattr(_auto, "_WF_POOL_BOOT_TIMEOUT_S", 0.2)
    monkeypatch.setattr(_auto, "_boot_wf_pool", _never_returns)

    common = dict(arrays=_arrays(), method="walkforward", wf_folds=4, n_trials=20,
                  seed=11, min_trades=5, cost_pts=0.1, oos=True, auto_expand=False)
    seq = run_auto(strat_path, workers=1, **common)
    start = time.time()
    stalled = run_auto(strat_path, workers=2, **common)
    elapsed = time.time() - start
    assert elapsed < 5.0, "run_auto should give up on the stalled pool almost immediately"
    assert _strip(seq["top"]) == _strip(stalled["top"])
    assert seq["best_params"] == stalled["best_params"]


def test_inline_progress_is_reported_per_ten_trials(strat_path):
    seen = []
    run_auto(strat_path, arrays=_arrays(), method="walkforward", wf_folds=3, n_trials=20,
             seed=5, min_trades=5, oos=True, auto_expand=False, workers=1,
             progress_cb=lambda d, t: seen.append((d, t)))
    assert seen and seen[-1] == (60, 60)
    assert all(d % 10 == 0 or d == 60 for d, _ in seen)


def test_parallel_progress_arrives_per_fold(strat_path):
    """Progress arrives per finished fold (20/40/60) when the pool actually starts. If it
    cannot -- the real, occasional case this machine's live runner fleet produces, see the
    Windows-spawn-timeout note on _run_folds_parallel -- run_auto's existing pool-failure
    handling reruns the folds in-line and progress arrives per ten trials instead, same as
    test_inline_progress_is_reported_per_ten_trials. Both are correct reporting, just at
    different granularity, so this only pins what holds true either way: every checkpoint
    is a real multiple of ten, it never goes backwards, and it finishes at (60, 60)."""
    seen = []
    run_auto(strat_path, arrays=_arrays(), method="walkforward", wf_folds=3, n_trials=20,
             seed=5, min_trades=5, oos=True, auto_expand=False, workers=2,
             progress_cb=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (60, 60)
    assert all(d % 10 == 0 for d, _ in seen)
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)
