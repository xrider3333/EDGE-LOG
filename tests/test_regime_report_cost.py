"""The 1F regime report card charges cost ONCE (2026-09-15).

WHY: analytics.regime_report's contract is GROSS trades in - it subtracts `cost_pts` from
every trade itself (`usd = float(pnl) - cost_pts`). Both callers that build the saved
`regime` block - optimize.run_grid (`_eval_net`) and auto.run_auto (`_eval_full`) - hand it
trades that engine._apply_costs has ALREADY netted, and used to pass the run's cost_pts on
top. Every cost-bearing run therefore saved 1F vol/trend/day-of-week/time-of-day buckets,
their PF and the monthly P&L grid n*cost points below the headline total_pnl (repro: 34
trades at cost 1.0 -> monthly grid 20.0 vs total_pnl 54.0). The call sites now pass
cost_pts=0.0; regime_report itself keeps its gross-in contract, pinned below too.
"""
import types

import numpy as np
import pandas as pd
import pytest

from augur_engine.analytics import regime_report

COST = 1.0
_N_DAYS = 60


def _arrays():
    idx = pd.date_range("2020-01-01 09:30", periods=288 * _N_DAYS, freq="5min",
                        tz="US/Eastern")
    n = len(idx)
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 0.3, n))
    return {"open": c, "high": c + 0.5, "low": c - 0.5, "close": c,
            "volume": np.full(n, 100.0),
            "day_id": np.repeat(np.arange(n // 78 + 1), 78)[:n], "index": idx,
            "meta": {"name": "SYN"}}


def _gross_trades(n_bars):
    # entries start on day 25 so every trade is past regime_report's 20-day ATR warm-up
    #   (a warm-up trade is skipped there, which would muddy a sum comparison)
    return [(i, i + 1, 10.0 if (i // 400) % 2 else -4.0)
            for i in range(288 * 25, n_bars - 2, 300)]


def _strategy():
    mod = types.ModuleType("regime_cost_probe")
    mod.STRATEGY_NAME = "REGIME COST PROBE"
    mod.DEFAULT_PARAMS = {"k": {"type": "int", "min": 1, "max": 2, "step": 1, "default": 1}}

    def run_backtest(o, h, l, cl, k=1, return_trades=False, **kw):
        tr = _gross_trades(len(cl))
        p = [t[2] for t in tr]
        gw = sum(x for x in p if x > 0)
        gl = -sum(x for x in p if x < 0)
        out = {"total_pnl": sum(p), "num_trades": len(p),
               "win_rate": 100.0 * sum(1 for x in p if x > 0) / len(p),
               "profit_factor": gw / gl, "max_drawdown": -1.0, "avg_pnl": sum(p) / len(p),
               "wins": sum(1 for x in p if x > 0), "losses": sum(1 for x in p if x < 0)}
        if return_trades:
            out["trades"] = tr
        return out

    mod.run_backtest = run_backtest
    return mod


def _monthly_sum(rr):
    return sum(v for row in rr["monthly"]["rows"] for v in row["months"] if v is not None)


def _expected_net(arrays):
    tr = _gross_trades(len(arrays["close"]))
    return len(tr), sum(t[2] for t in tr) - COST * len(tr)


def test_run_grid_regime_monthly_sum_equals_best_total_pnl_with_cost():
    from augur_engine.optimize import run_grid
    arrays = _arrays()
    out = run_grid(_strategy(), arrays=arrays, grid={"k": [1]}, cost_pts=COST, min_trades=1,
                   top_n=1, compute_dsr=False, mc_sims=0, compute_regime=True,
                   compute_context=False)
    rr = out.get("regime")
    assert rr is not None
    best = out["best"][0] if isinstance(out.get("best"), list) else out.get("best")
    n, net = _expected_net(arrays)
    assert rr["n_trades"] == best["num_trades"] == n
    assert best["total_pnl"] == pytest.approx(net)
    # was net - COST * n (charged twice): 20.0 against 54.0 on this fixture
    assert _monthly_sum(rr) == pytest.approx(best["total_pnl"], abs=0.05 * 12)
    buckets = sum(b["pnl"] for b in rr["vol"])
    assert buckets == pytest.approx(best["total_pnl"])


def test_run_auto_regime_monthly_sum_equals_the_champion_net_with_cost():
    from augur_engine.auto import run_auto
    arrays = _arrays()
    out = run_auto(_strategy(), arrays=arrays, method="single", oos=False, n_trials=2,
                   seed=1, min_trades=1, cost_pts=COST, compute_regime=True,
                   compute_context=False, auto_expand=False)
    rr = out.get("regime")
    assert rr is not None
    n, net = _expected_net(arrays)
    assert rr["n_trades"] == n
    assert sum(b["pnl"] for b in rr["vol"]) == pytest.approx(net)
    assert _monthly_sum(rr) == pytest.approx(net, abs=0.05 * 12)


def test_regime_report_keeps_its_gross_in_contract():
    """A caller holding GROSS trades still passes the run's cost and gets net buckets."""
    arrays = _arrays()
    tr = _gross_trades(len(arrays["close"]))
    n, net = _expected_net(arrays)
    rr = regime_report(tr, arrays["index"], arrays["high"], arrays["low"], arrays["close"],
                       cost_pts=COST)
    assert rr["n_trades"] == n
    assert sum(b["pnl"] for b in rr["vol"]) == pytest.approx(net)
    # and already-net trades with cost_pts=0.0 land on the SAME numbers
    net_tr = [(a, b, p - COST) for a, b, p in tr]
    rr0 = regime_report(net_tr, arrays["index"], arrays["high"], arrays["low"],
                        arrays["close"], cost_pts=0.0)
    assert rr0["vol"] == rr["vol"] and rr0["monthly"] == rr["monthly"]
