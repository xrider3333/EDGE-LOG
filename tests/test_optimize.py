"""Unit tests for augur_engine.optimize — grid expansion, preset lookup, and the
run_grid sweep (ranking + min_trades gating + top_n) driven by a stub strategy.

expand_grid feeds every sweep, and run_grid's rank/gate/trim is what decides which
config wins, so both are pinned. run_grid is exercised single-threaded with a tiny
stub module so there's no real backtest, data, or multiprocessing involved.
"""
import types

import numpy as np
import pytest

from augur_engine.optimize import expand_grid, grid_from_preset, list_presets, run_grid


# ── expand_grid ─────────────────────────────────────────────────────────────────

def test_expand_grid_cartesian_product():
    out = expand_grid({"a": [1, 2], "b": [3, 4]})
    assert out == [{"a": 1, "b": 3}, {"a": 1, "b": 4},
                   {"a": 2, "b": 3}, {"a": 2, "b": 4}]


def test_expand_grid_wraps_scalars():
    assert expand_grid({"a": [1, 2], "b": 9}) == [{"a": 1, "b": 9}, {"a": 2, "b": 9}]


def test_expand_grid_single_combo():
    assert expand_grid({"a": [5]}) == [{"a": 5}]


# ── preset helpers ──────────────────────────────────────────────────────────────

def _stub_module():
    m = types.ModuleType("stub_strategy")
    m.STRATEGY_NAME = "STUB"
    m.DEFAULT_PARAMS = {"x": {"type": "int", "min": 0, "max": 10, "default": 1}}
    m.PARAM_GRID_PRESETS = {"Short test": {"x": [1, 2, 3]}}

    def run_backtest(O, H, L, C, x=1, return_trades=False):
        # x=2 trades too little (gated at min_trades=30); pnl grows with x
        nt = 5 if x == 2 else 40
        return {"total_pnl": float(x * 10), "num_trades": nt, "win_rate": 50.0,
                "profit_factor": 1.0 + x, "max_drawdown": -float(x), "avg_pnl": 1.0,
                "wins": nt // 2, "losses": nt // 2}
    m.run_backtest = run_backtest
    return m


def test_list_and_get_preset():
    mod = _stub_module()
    assert list_presets(mod) == ["Short test"]
    assert grid_from_preset(mod, "Short test") == {"x": [1, 2, 3]}


def test_grid_from_unknown_preset_raises():
    with pytest.raises(ValueError):
        grid_from_preset(_stub_module(), "nope")


# ── run_grid ────────────────────────────────────────────────────────────────────

@pytest.fixture
def flat_arrays():
    n = 100
    return {"open": np.ones(n), "high": np.ones(n), "low": np.ones(n),
            "close": np.ones(n), "volume": None, "day_id": None, "meta": {"name": "S"}}


def test_run_grid_gates_ranks_and_trims(flat_arrays):
    r = run_grid(_stub_module(), grid={"x": [1, 2, 3, 4]}, arrays=flat_arrays,
                 min_trades=30, top_n=2, rank_by="total_pnl", workers=1)
    assert r["n_combos"] == 4
    assert r["n_valid"] == 3                     # x=2 gated out (5 < 30 trades)
    assert r["best_params"] == {"x": 4}          # highest total_pnl
    assert [t["x"] for t in r["top"]] == [4, 3]  # top_n=2, ranked desc


def test_run_grid_rank_by_mar(flat_arrays):
    # mar = total_pnl / |max_drawdown| = (x*10)/x = 10 for all -> tie, stable order
    r = run_grid(_stub_module(), grid={"x": [1, 2, 3, 4]}, arrays=flat_arrays,
                 min_trades=30, rank_by="mar", workers=1)
    assert r["best_params"] == {"x": 1}
