"""Auto-Optimize 'pills' must score the champion's NET trades, not gross (2026-09-15).

WHY: analytics.run_pills' `champ_trades` contract is NET of cost_pts (see its docstring,
updated alongside this fix) -- conformal_pnl_band, edge_significance and
synthetic_day_bootstrap take no cost_pts at all and score t[2] as-is, and
causal_entry_test's `real` total is summed straight from t[2] while its OWN random-entry
null simulations ARE charged cost_pts (`- m * cost_pts`), so `real` must already be net to
sit on the same footing as those nulls. auto.run_auto's pills block (~augur_engine/auto.py,
the compute_pills branch) called the raw strategy plugin directly
(`fn(O, H, L, C, return_trades=True, ...)`) for its champion re-backtest -- GROSS trades,
no engine._apply_costs -- and handed them to run_pills as champ_trades. So on every
cost-bearing Auto-Optimize job with pills on, conformal/edge_sig/causal all read too
optimistic. The fix nets `_ctrades` with engine._apply_costs before the run_pills call,
mirroring `_eval_full`'s own regime-report netting a few lines above it in the same
function. validate.py's run_pills call was already fed NET trades (`full["trades"]` comes
from engine.run_backtest, which applies costs internally) -- pinned unchanged here too.

Layer 1 (below) drives the REAL augur_engine.auto.run_auto pipeline end-to-end with a tiny
synthetic strategy + cost_pts > 0 and reads the real conformal/edge_sig/causal pill dicts
straight off its result -- proving the actual numbers a job would save. Layer 2 pins
validate.py's call site is unaffected, by spying on analytics.run_pills through one small
real run_validate() call (find_master/load_master_arrays faked, same convention as
tests/test_selection.py's Layer 2).
"""
import types

import numpy as np
import pandas as pd
import pytest

COST = 3.0
N_TRADES = 70          # >=60 (conformal), >=30 (edge_sig/causal); <80 skips gate_feature_select
                        #   (the RFECV pill) so this test stays fast -- see ml_gate.gate_feature_select's
                        #   `len(T) < max(min_history, 80)` early-return.
N_DAYS = 100


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 -- augur_engine.auto.run_auto, real pill computations
# ─────────────────────────────────────────────────────────────────────────────

def _arrays():
    idx = pd.date_range("2020-01-01 09:30", periods=288 * N_DAYS, freq="5min",
                        tz="US/Eastern")
    n = len(idx)
    rng = np.random.default_rng(7)
    c = 100 + np.cumsum(rng.normal(0, 0.3, n))
    return {"open": c, "high": c + 0.5, "low": c - 0.5, "close": c,
            "volume": np.full(n, 100.0),
            "day_id": np.repeat(np.arange(n // 78 + 1), 78)[:n], "index": idx,
            "meta": {"name": "SYN_PILLS"}}


def _gross_trades(n_bars):
    # 4-tuples (entry_bar, exit_bar, GROSS pnl, side) -- side at t[3] is needed by
    #   causal_entry_test; alternating sign/magnitude so the champion's NET total differs
    #   materially from its GROSS total (COST=3.0: +50->+47, -10->-13 -- signs unchanged,
    #   both classes survive netting) and so a gross-vs-net mixup is not lost in noise.
    #   Entries step by >1 bar-day so N_TRADES trades land on N_TRADES distinct days.
    step = (n_bars - 2000) // N_TRADES
    out = []
    for i in range(N_TRADES):
        entry = 500 + i * step
        pnl = 50.0 if i % 2 == 0 else -10.0
        side = 1.0 if i % 2 == 0 else -1.0
        out.append((entry, entry + 3, pnl, side))
    return out


def _strategy():
    mod = types.ModuleType("pills_cost_probe")
    mod.STRATEGY_NAME = "PILLS COST PROBE"
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


def _net_pnls():
    tr = _gross_trades(288 * N_DAYS)
    return [t[2] - COST for t in tr]


def _gross_pnls():
    tr = _gross_trades(288 * N_DAYS)
    return [t[2] for t in tr]


@pytest.fixture(scope="module")
def pills_out():
    """One real run_auto(..., compute_pills=True, cost_pts=COST) call, reused by every
    assertion below (mirrors test_regime_report_cost.py / test_selection.py's own
    module-scoped-fixture convention to avoid re-paying the search cost per test)."""
    from augur_engine.auto import run_auto
    arrays = _arrays()
    return run_auto(_strategy(), arrays=arrays, method="single", oos=False, n_trials=2,
                    seed=1, min_trades=1, cost_pts=COST, compute_pills=True,
                    compute_regime=False, compute_context=False, auto_expand=False)


def test_edge_significance_mean_is_the_champions_net_mean(pills_out):
    from augur_engine.analytics import edge_significance
    edge = pills_out.get("edge_sig")
    assert edge is not None
    net = _net_pnls()
    assert edge["n"] == len(net)
    assert edge["mean_pnl"] == pytest.approx(float(np.mean(net)), abs=1e-6)
    # sanity: cost actually moves this number -- proves the assertion isn't vacuous
    gross_mean = float(np.mean(_gross_pnls()))
    assert edge["mean_pnl"] != pytest.approx(gross_mean, abs=0.5)
    # and the real function, called directly on the net list, reproduces the exact dict
    #   (both are seeded deterministically) -- confirms it's genuinely NET, not just "some
    #   other number that happens to be far from gross".
    ref = edge_significance(net)
    assert edge["t_stat"] == pytest.approx(ref["t_stat"])
    assert edge["p_value"] == pytest.approx(ref["p_value"])


def test_conformal_band_is_centered_on_net_pnl(pills_out):
    from augur_engine.analytics import conformal_pnl_band
    conf = pills_out.get("conformal")
    assert conf is not None
    net = _net_pnls()
    ref_net = conformal_pnl_band(net)                 # same seed=42 default -> same split
    ref_gross = conformal_pnl_band(_gross_pnls())
    assert conf["median"] == pytest.approx(ref_net["median"])
    assert conf["lo"] == pytest.approx(ref_net["lo"])
    assert conf["hi"] == pytest.approx(ref_net["hi"])
    # sanity: the gross-computed band sits at a materially different centre
    assert conf["median"] != pytest.approx(ref_gross["median"], abs=0.5)


def test_causal_entry_test_real_total_is_net_like_its_nulls(pills_out):
    causal = pills_out.get("causal")
    assert causal is not None
    net_total = sum(_net_pnls())
    gross_total = sum(_gross_pnls())
    assert causal["real_total_pts"] == pytest.approx(round(net_total, 1), abs=0.05)
    assert causal["real_total_pts"] != pytest.approx(round(gross_total, 1), abs=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 -- validate.py's run_pills call site is fed NET trades already; unaffected by
#   this fix. Spies on analytics.run_pills (patched where validate.py looks it up) inside
#   one small real run_validate() call, same faked find_master/load_master_arrays
#   convention as tests/test_selection.py's Layer 2.
# ─────────────────────────────────────────────────────────────────────────────

_V_MARKER = 1000.0
_V_LO = pd.Timestamp("2020-01-01", tz="US/Eastern")
_V_HI = pd.Timestamp("2020-01-20", tz="US/Eastern")
_V_IDX = pd.date_range(_V_LO, _V_HI, freq="5min", tz="US/Eastern")
_V_CLOSE = _V_MARKER + np.zeros(len(_V_IDX))    # flat -- makes the champion's gross
                                                 #   per-trade pnl a hand-known constant
_V_MASTER = {"filename": "SYN_PILLS_COST_VALIDATE.csv", "instrument": "SYN_PC",
             "timeframe": "5m", "date_from": _V_LO.date().isoformat(),
             "date_to": _V_HI.date().isoformat(), "name": "SYN_PC"}
_V_GROSS_PER_TRADE = 777.0


def _v_fake_find_master(instrument, timeframe, session=None, source=None):
    return dict(_V_MASTER)


def _v_fake_load_master_arrays(master, date_from=None, date_to=None):
    idx = _V_IDX
    mask = np.ones(len(idx), dtype=bool)
    if date_from:
        mask &= (idx >= pd.Timestamp(date_from, tz="US/Eastern"))
    if date_to:
        mask &= (idx < pd.Timestamp(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
    sub_idx = idx[mask]
    sub_close = _V_CLOSE[mask]
    n = len(sub_close)
    day_id = (pd.factorize(pd.Series(sub_idx).dt.date)[0].astype("int64")
              if n else np.array([], dtype="int64"))
    return {"open": sub_close.copy(), "high": sub_close + 1.0, "low": sub_close - 1.0,
            "close": sub_close.copy(), "volume": np.full(n, 1000.0), "day_id": day_id,
            "index": sub_idx, "meta": master}


def _v_strategy():
    """Fixed GROSS per-trade pnl regardless of params/window -- so the champion's whole-
    window `full["trades"]` (validate.py's own extra run_backtest call) is a hand-known
    constant, letting the test assert NET-ness by exact value instead of re-deriving it."""
    mod = types.ModuleType("pills_cost_validate_probe")
    mod.STRATEGY_NAME = "PILLS COST VALIDATE PROBE"
    mod.DEFAULT_PARAMS = {"knob": {"type": "float", "min": 1.0, "max": 2.0, "step": 1.0,
                                    "default": 1.0}}

    def run_backtest(o, h, l, c, knob=1.0, return_trades=False, **kw):
        n = len(c)
        trades_n = 10
        pnl = _V_GROSS_PER_TRADE * trades_n
        out = {"total_pnl": pnl, "num_trades": trades_n, "win_rate": 60.0,
               "profit_factor": 3.0, "max_drawdown": -10.0, "avg_pnl": pnl / trades_n,
               "wins": 6, "losses": 4}
        if return_trades:
            step = max(1, (n - 2) // trades_n)
            out["trades"] = [(i * step, i * step + 1, _V_GROSS_PER_TRADE, 1, 100.0)
                             for i in range(trades_n)]
        return out

    mod.run_backtest = run_backtest
    return mod


def test_run_validate_feeds_run_pills_already_net_trades(monkeypatch):
    import augur_engine.analytics as analytics_mod
    import augur_engine.auto as auto_mod
    import augur_engine.engine as engine_mod
    import augur_engine.optimize as optimize_mod
    import augur_engine.validate as validate_mod
    from augur_engine.validate import run_validate

    for m in (validate_mod, auto_mod, engine_mod, optimize_mod):
        monkeypatch.setattr(m, "find_master", _v_fake_find_master)
        monkeypatch.setattr(m, "load_master_arrays", _v_fake_load_master_arrays)

    captured = {}
    real_run_pills = analytics_mod.run_pills

    def _spy_run_pills(*a, **kw):
        captured.update(kw)
        return real_run_pills(*a, **kw)

    monkeypatch.setattr(analytics_mod, "run_pills", _spy_run_pills)

    run_validate(_v_strategy(), instrument="SYN_PC", timeframe="5m", session="rth",
                cost_pts=COST, min_trades=1, n_trials=10, wf_folds=0, seed=1,
                lockbox_months=0.2, select_oos_topk=0, compute_pills=True,
                compute_feature_select=False, equity_points=100)

    trades = captured.get("champ_trades")
    assert trades and len(trades) == 10
    for t in trades:
        # already net: engine.run_backtest applied _apply_costs before validate.py ever
        #   built `full["trades"]` -- if this ever regressed to passing gross trades
        #   again, t[2] would read _V_GROSS_PER_TRADE (777.0) instead.
        assert t[2] == pytest.approx(_V_GROSS_PER_TRADE - COST)
    assert captured.get("cost_pts") == pytest.approx(COST)
