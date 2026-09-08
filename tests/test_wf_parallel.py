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

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def _arrays(n=9000, seed=3):
    rng = np.random.default_rng(seed)
    c = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
    o = c + rng.normal(0, 0.1, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.2, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.2, n))
    return {"open": o, "high": h, "low": l, "close": c,
            "volume": rng.integers(100, 1000, n).astype(float),
            "day_id": np.repeat(np.arange(n // 78 + 1), 78)[:n]}


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


def test_inline_progress_is_reported_per_ten_trials(strat_path):
    seen = []
    run_auto(strat_path, arrays=_arrays(), method="walkforward", wf_folds=3, n_trials=20,
             seed=5, min_trades=5, oos=True, auto_expand=False, workers=1,
             progress_cb=lambda d, t: seen.append((d, t)))
    assert seen and seen[-1] == (60, 60)
    assert all(d % 10 == 0 or d == 60 for d, _ in seen)


def test_parallel_progress_arrives_per_fold(strat_path):
    seen = []
    run_auto(strat_path, arrays=_arrays(), method="walkforward", wf_folds=3, n_trials=20,
             seed=5, min_trades=5, oos=True, auto_expand=False, workers=2,
             progress_cb=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (60, 60)
    assert {d for d, _ in seen} <= {20, 40, 60}
