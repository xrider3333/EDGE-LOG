"""Walk-forward out-of-sample block (ENGINE_BRIEF.md STAGE 1, 2026-09-15).

Today no run saves a walk-forward Sharpe, Sortino or drawdown — every fold's real
per-trade OOS pnls exist transiently inside auto.py's `_wf_fold_row` but are pooled
into one capped, unlabeled distribution (`win_dist_wf`) and discarded before the saved
doc is built. `analytics.wf_oos_block` stitches the PRIMARY walk-forward scheme's
per-fold OOS trades into ONE small saved block (`validate.wf_oos`) — net/PF/win-rate/
avg-win-loss/drawdown/Sharpe/Sortino/equity, in fold order — and validate.py attaches
it before the pop loop that used to throw the per-trade arrays away.

Sections:
  1. `wf_oos_block` unit tests — a hand-checkable two-fold example (PF, win rate,
     avg win/loss, a drawdown whose worst trough spans a fold boundary, sharpe/sortino
     equal to the analytics.py helpers, years from real dates, fold_idx).
  2. Reconciliation-guard failures -> None (never save a block that disagrees with the
     fold figures the app already shows).
  3. D6 — the cost-double-charge fix: `_oos_pnls` must now sum to `oos_pnl` for a fold
     with cost_pts > 0 (was previously short by cost_pts * n_trades).
  4. A full `run_validate` walk-forward run on a small synthetic dataset (the same
     monkeypatched find_master/load_master_arrays pattern tests/test_fold_detail.py
     and tests/test_selection.py already use): `validate.wf_oos` is present and its
     net/trades/profit_factor equal the pooled `top10_results` (`top`) fold figures.
  5. D2 — a big `validate.wf_oos.equity` array survives api/runner.py's shrink_to_fit
     (downsampled, never dropped) because 'equity' is already in _CURVE_KEYS and
     'validate' already matches a _PROTECTED_KEY_HINTS substring.
"""
import datetime
import types

import numpy as np
import pandas as pd
import pytest

from augur_engine.analytics import (wf_oos_block, sharpe_from_pnls, sortino_from_pnls,
                                    bar_date_bounds)
from augur_engine.auto import run_auto


# ─────────────────────────────────────────────────────────────────────────────
# 1-2. wf_oos_block — hand-checkable example + reconciliation guard
# ─────────────────────────────────────────────────────────────────────────────

# Two folds, stitched: [10, -5, 3, -2, -20, 8, 4, -1, 2].
# The running peak (10, after fold 1's first trade) and the worst trough (-14
# cumulative, after fold 2's FIRST trade) straddle the fold boundary on purpose.
_FOLD1 = {"fold": 1, "pnls": [10.0, -5.0, 3.0, -2.0], "oos_pnl": 6.0, "oos_trades": 4,
          "oos_wins": 2, "oos_pf": 13 / 7, "from": "2020-01-01", "to": "2020-06-01"}
_FOLD2 = {"fold": 2, "pnls": [-20.0, 8.0, 4.0, -1.0, 2.0], "oos_pnl": -7.0, "oos_trades": 5,
          "oos_wins": 3, "oos_pf": 14 / 21, "from": "2020-06-02", "to": "2021-01-01"}
_STITCHED = _FOLD1["pnls"] + _FOLD2["pnls"]


def test_hand_checkable_pooled_figures():
    b = wf_oos_block([_FOLD1, _FOLD2], mode="rolling")
    assert b is not None
    assert b["v"] == 1 and b["mode"] == "rolling" and b["n_folds"] == 2
    assert b["trades"] == 9
    assert b["wins"] == 5                              # 10, 3, 8, 4, 2 are the winners
    assert b["win_rate"] == pytest.approx(500 / 9, abs=0.01)
    assert b["net"] == pytest.approx(-1.0)              # 6 + (-7)
    assert b["gross_win"] == pytest.approx(27.0)        # 10+3+8+4+2
    assert b["gross_loss"] == pytest.approx(28.0)       # 5+2+20+1 (positive magnitude)
    assert b["profit_factor"] == pytest.approx(27 / 28, abs=1e-3)
    assert b["avg_win"] == pytest.approx(27 / 5)
    assert b["avg_loss"] == pytest.approx(28 / 4)


def test_drawdown_worst_trough_spans_a_fold_boundary():
    """Cumulative curve: 10, 5, 8, 6, -14, -6, -2, -3, -1 — the running peak (10) sits
    in fold 1's first trade, the trough (-14, cum-peak=-24) in fold 2's first trade."""
    b = wf_oos_block([_FOLD1, _FOLD2], mode="rolling")
    assert b["max_drawdown"] == pytest.approx(24.0)
    assert b["max_drawdown"] >= 0                       # magnitude, per ENGINE_BRIEF D3


def test_drawdown_peak_starts_flat_when_the_sequence_opens_with_losses():
    """Stitched [-5, -3, 4, 6] + [2, -1] -> cumulative -5, -8, -4, 2, 4, 3. The worst
    trough (-8) comes BEFORE equity first goes above 0, so measured from a flat account
    (peak 0.0, like engine._apply_costs / ml_gate._stats) the drawdown is 8. Seeding the
    peak at the first trade's cumulative value (-5) would report only 3 and inflate a
    walk-forward MAR built on it by ~2.7x."""
    f1 = {"fold": 1, "pnls": [-5.0, -3.0, 4.0, 6.0], "oos_pnl": 2.0, "oos_trades": 4,
          "oos_wins": 2, "oos_pf": 10 / 8, "from": "2020-01-01", "to": "2020-03-01"}
    f2 = {"fold": 2, "pnls": [2.0, -1.0], "oos_pnl": 1.0, "oos_trades": 2,
          "oos_wins": 1, "oos_pf": 2.0, "from": "2020-03-02", "to": "2020-06-01"}
    b = wf_oos_block([f1, f2], mode="rolling")
    assert b["max_drawdown"] == pytest.approx(8.0)
    # the engine's own drawdown for the same net trade list agrees
    from augur_engine.engine import _apply_costs
    eng = _apply_costs({"trades": [(i, i + 1, x) for i, x in enumerate(f1["pnls"] + f2["pnls"])]},
                       0.0)
    assert b["max_drawdown"] == pytest.approx(abs(eng["max_drawdown"]))


def test_max_dd_default_callers_keep_their_first_trade_peak():
    """_max_dd has other callers (monte_carlo_drawdown, the ensemble block) whose saved
    figures must not change meaning: only peak_from_flat=True seeds the peak at 0."""
    from augur_engine.analytics import _max_dd, monte_carlo_drawdown
    arr = np.array([-5.0, -3.0, 4.0, 6.0, 2.0, -1.0])
    assert _max_dd(arr) == pytest.approx(-3.0)
    assert _max_dd(arr, peak_from_flat=True) == pytest.approx(-8.0)
    assert monte_carlo_drawdown(arr, n_sims=5)["as_traded"] == pytest.approx(-3.0)


def test_sharpe_sortino_equal_the_analytics_helpers_and_years_from_dates():
    b = wf_oos_block([_FOLD1, _FOLD2], mode="rolling")
    d0 = datetime.date.fromisoformat(_FOLD1["from"])
    d1 = datetime.date.fromisoformat(_FOLD2["to"])
    years = (d1 - d0).days / 365.25                    # 366 days -> ~1.002, no 0.1 floor hit
    assert b["years"] == pytest.approx(years, abs=1e-3)
    assert b["sharpe"] == pytest.approx(sharpe_from_pnls(_STITCHED, years))
    assert b["sortino"] == pytest.approx(sortino_from_pnls(_STITCHED, years))


def test_equity_curve_and_fold_idx_when_no_downsampling_is_needed():
    b = wf_oos_block([_FOLD1, _FOLD2], mode="rolling")
    cum = np.cumsum(_STITCHED).tolist()
    assert b["equity"] == pytest.approx(cum, abs=0.05)
    assert b["equity_n"] == 9
    assert b["fold_idx"] == [0, 4]                      # fold 2's first trade is index 4


def test_fold_idx_maps_correctly_through_downsampling():
    """With more trades than the equity cap, fold_idx must still point at (or just
    after) each fold's real first-trade position in the DOWNSAMPLED curve."""
    rng = np.random.default_rng(0)
    folds = []
    for f in range(3):
        n = 300
        pnls = rng.normal(0, 1, n).tolist()
        folds.append({"fold": f + 1, "pnls": pnls, "oos_pnl": float(sum(pnls)),
                      "oos_trades": n, "oos_wins": None, "oos_pf": 1.0,
                      "from": f"2020-0{f + 1}-01", "to": f"2020-0{f + 1}-28"})
    b = wf_oos_block(folds, mode="anchored", cap=200)
    assert b["equity_n"] == 900
    assert len(b["equity"]) == 200
    offsets = [0, 300, 600]
    for fidx, off in zip(b["fold_idx"], offsets):
        # the downsampled point at fold_idx covers a bar at or after the fold's own
        # start, and the point right before it (if any) covers a bar still short of it
        step = 900 / 200
        assert int(fidx * step) >= off
        if fidx > 0:
            assert int((fidx - 1) * step) < off


def test_folds_summary_rows_use_the_saved_oos_pnl_not_a_recomputed_one():
    b = wf_oos_block([_FOLD1, _FOLD2], mode="anchored", src="backfill")
    assert b["src"] == "backfill"
    assert [f["f"] for f in b["folds"]] == [1, 2]
    assert [f["net"] for f in b["folds"]] == [pytest.approx(6.0), pytest.approx(-7.0)]
    assert [f["from"] for f in b["folds"]] == ["2020-01-01", "2020-06-02"]
    assert [f["to"] for f in b["folds"]] == ["2020-06-01", "2021-01-01"]
    assert [f["trades"] for f in b["folds"]] == [4, 5]


def test_no_folds_returns_none():
    assert wf_oos_block([], mode="rolling") is None
    assert wf_oos_block(None, mode="rolling") is None


def test_reconciliation_guard_refuses_a_trade_count_mismatch():
    bad = dict(_FOLD1, pnls=[10.0, -5.0, 3.0])          # len 3, oos_trades still says 4
    assert wf_oos_block([bad, _FOLD2], mode="rolling") is None


def test_reconciliation_guard_refuses_a_net_pnl_mismatch():
    bad = dict(_FOLD1, oos_pnl=999.0)                    # sum(pnls)=6, way outside tolerance
    assert wf_oos_block([bad, _FOLD2], mode="rolling") is None


@pytest.mark.parametrize("bad_fold", [
    dict(_FOLD1, pnls=[10.0, float("nan"), 3.0, -2.0]),        # NaN pnl
    dict(_FOLD1, pnls=[10.0, float("inf"), 3.0, -2.0]),        # +inf pnl
    dict(_FOLD1, pnls=[10.0, float("-inf"), 3.0, -2.0]),       # -inf pnl
    dict(_FOLD1, oos_pnl=float("nan")),                         # NaN oos_pnl
    dict(_FOLD1, oos_pnl=float("inf")),                         # inf oos_pnl
    dict(_FOLD1, oos_pnl=None),                                 # no oos_pnl at all
])
def test_reconciliation_guard_refuses_non_finite_values(bad_fold, capsys):
    """A NaN slips through `abs(sum - oos_pnl) > tol` (every NaN comparison is False), and
    an inf would poison net/PF/Sharpe/equity into values json_safe saves as null. The
    guard must refuse both, and say why in the log."""
    assert wf_oos_block([bad_fold, _FOLD2], mode="rolling") is None
    out = capsys.readouterr().out
    assert "[wf_oos_block] fold 1" in out and "refusing to save the block" in out


def test_reconciliation_guard_refuses_a_nan_that_would_pass_the_tolerance_check():
    # sum(pnls) is NaN and oos_pnl is NaN: without the finiteness check the tolerance test
    # abs(nan - nan) > tol is False, i.e. it would have "reconciled"
    both_nan = dict(_FOLD1, pnls=[float("nan")] * 4, oos_pnl=float("nan"))
    assert wf_oos_block([both_nan, _FOLD2], mode="rolling") is None


def test_reconciliation_guard_allows_rounding_noise():
    ok = dict(_FOLD1, oos_pnl=6.0005)                    # within 1e-3 * max(1, 4) = 0.004
    assert wf_oos_block([ok, _FOLD2], mode="rolling") is not None


def test_gross_loss_zero_gives_none_profit_factor_not_a_crash():
    all_wins = {"fold": 1, "pnls": [1.0, 2.0, 3.0], "oos_pnl": 6.0, "oos_trades": 3,
               "oos_wins": 3, "oos_pf": 0.0, "from": "2020-01-01", "to": "2020-01-02"}
    b = wf_oos_block([all_wins], mode="rolling")
    assert b["profit_factor"] is None
    assert b["avg_loss"] is None
    assert b["max_drawdown"] == pytest.approx(0.0)


def test_missing_dates_omit_years_and_sharpe_but_still_build_the_rest():
    no_dates = [dict(_FOLD1, **{"from": None, "to": None}),
                dict(_FOLD2, **{"from": None, "to": None})]
    b = wf_oos_block(no_dates, mode="rolling")
    assert b is not None
    assert b["years"] is None and b["sharpe"] is None and b["sortino"] is None
    assert b["net"] == pytest.approx(-1.0)               # everything else unaffected


# ─────────────────────────────────────────────────────────────────────────────
# 3. D6 — the cost-double-charge fix
# ─────────────────────────────────────────────────────────────────────────────

def _cost_fix_strategy():
    """A fixed-shape strategy: always 20 trades with pnls -10..9 before cost, so
    cost_pts>0 leaves both wins and losses (clears WF_MIN_SIDE=5 on each side) —
    the point is only the cost arithmetic, not realistic price action."""
    mod = types.ModuleType("fake_cost_fix_strategy")
    mod.STRATEGY_NAME = "SYN COST FIX"
    mod.DEFAULT_PARAMS = {"knob": {"type": "float", "min": 0.0, "max": 10.0,
                                   "step": 1.0, "default": 5.0}}

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        pnls = [float(i - 10) for i in range(20)]
        total = sum(pnls)
        wins = sum(1 for x in pnls if x > 0)
        losses = 20 - wins
        out = {"total_pnl": total, "num_trades": 20, "win_rate": 100.0 * wins / 20,
               "profit_factor": 2.0, "max_drawdown": -5.0, "avg_pnl": total / 20,
               "wins": wins, "losses": losses}
        if return_trades:
            out["trades"] = [(i, i + 1, pnls[i]) for i in range(20)]
        return out

    mod.run_backtest = run_backtest
    return mod


def _flat_arrays(n=4500, index=None):
    c = np.full(n, 100.0)
    return {"open": c.copy(), "high": c + 1.0, "low": c - 1.0, "close": c.copy(),
            "volume": None, "day_id": None, "index": index}


def test_oos_pnls_now_sums_to_oos_pnl_with_cost_pts_positive():
    mod = _cost_fix_strategy()
    out = run_auto(mod, arrays=_flat_arrays(), method="walkforward", wf_mode="rolling",
                   wf_folds=2, n_trials=3, seed=1, min_trades=1, cost_pts=1.0, oos=True,
                   auto_expand=False, workers=1)
    folds = out["top"]
    assert len(folds) == 2
    for fr in folds:
        assert fr["oos_trades"] == 20
        # before the fix this was oos_pnl - cost_pts*20 (short by exactly 20 points)
        assert sum(fr["_oos_pnls"]) == pytest.approx(fr["oos_pnl"], abs=1e-3)


# The same fixed-shape strategy as _cost_fix_strategy, as SOURCE: the wf_pool path only
#   runs when run_auto is handed a strategy FILE PATH (auto.py: `isinstance(strategy, str)`),
#   because Windows spawn workers re-load the strategy by path - a module object would
#   silently take the in-line loop and prove nothing about the pool.
_COST_FIX_SRC = '''
STRATEGY_NAME = "SYN COST FIX POOL"
DEFAULT_PARAMS = {"knob": {"type": "float", "min": 0.0, "max": 10.0, "step": 1.0, "default": 5.0}}
def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
    pnls = [float(i - 10) for i in range(20)]
    total = sum(pnls)
    wins = sum(1 for x in pnls if x > 0)
    out = {"total_pnl": total, "num_trades": 20, "win_rate": 100.0 * wins / 20,
           "profit_factor": 2.0, "max_drawdown": -5.0, "avg_pnl": total / 20,
           "wins": wins, "losses": 20 - wins}
    if return_trades:
        out["trades"] = [(i, i + 1, pnls[i]) for i in range(20)]
    return out
'''


def test_oos_pnls_fix_holds_in_the_parallel_fold_path_too(tmp_path, monkeypatch):
    import augur_engine.auto as auto_mod
    strat_path = tmp_path / "WFOOS_COSTFIX_1_0.py"
    strat_path.write_text(_COST_FIX_SRC, encoding="utf-8")

    # spy on the pool driver: the rows must really come back from worker processes, not
    # from run_auto's in-line fallback
    real = auto_mod._run_folds_parallel
    pool = {}

    def _spy(*a, **k):
        try:
            rows = real(*a, **k)
        except BaseException as exc:
            pool["error"] = exc
            raise
        pool["rows"] = rows
        return rows
    monkeypatch.setattr(auto_mod, "_run_folds_parallel", _spy)

    out = run_auto(str(strat_path), arrays=_flat_arrays(), method="walkforward",
                   wf_mode="rolling", wf_folds=2, n_trials=3, seed=1, min_trades=1,
                   cost_pts=1.0, oos=True, auto_expand=False, workers=2)
    if isinstance(pool.get("error"), TimeoutError):
        # the one fallback run_auto documents as environmental (Windows spawn handshake
        # stalled under a saturated machine, see _run_folds_parallel) - not this fix
        pytest.skip(f"wf_pool could not start on this machine: {pool['error']}")
    assert "error" not in pool, f"the fold pool raised: {pool.get('error')!r}"
    assert pool.get("rows") and all(r is not None for r in pool["rows"])
    assert len(out["top"]) == 2
    for fr in out["top"]:
        assert fr["oos_trades"] == 20
        # before D6 the worker's _wf_fold_row re-subtracted cost: short by 1.0 * 20 points
        assert sum(fr["_oos_pnls"]) == pytest.approx(fr["oos_pnl"], abs=1e-3)
    # and these ARE the pool's rows
    assert sorted(r["oos_pnl"] for r in pool["rows"]) == sorted(r["oos_pnl"] for r in out["top"])


def test_oos_from_oos_to_present_when_arrays_carry_an_index():
    mod = _cost_fix_strategy()
    idx = pd.date_range("2020-01-01", periods=4500, freq="5min", tz="US/Eastern")
    out = run_auto(mod, arrays=_flat_arrays(index=idx), method="walkforward",
                   wf_mode="rolling", wf_folds=2, n_trials=3, seed=1, min_trades=1,
                   cost_pts=1.0, oos=True, auto_expand=False, workers=1)
    for fr in out["top"]:
        assert "oos_from" in fr and "oos_to" in fr
        assert fr["oos_from"] <= fr["oos_to"]
    # cross-check one fold's dates directly against the shared helper
    te_s = 1800   # init = int(4500*0.40)
    te_e = 1800 + (4500 - 1800) // 2
    d0, d1 = bar_date_bounds(idx, te_s, te_e)
    assert out["top"][0]["oos_from"] == d0
    assert out["top"][0]["oos_to"] == d1


# ─────────────────────────────────────────────────────────────────────────────
# 4. Full run_validate walk-forward run on a small synthetic dataset
# ─────────────────────────────────────────────────────────────────────────────

_FULL_IDX = pd.date_range(pd.Timestamp("2020-01-01", tz="US/Eastern"),
                          pd.Timestamp("2020-01-26", tz="US/Eastern"), freq="5min",
                          tz="US/Eastern")
_FULL_CLOSE = 1000.0 + np.arange(len(_FULL_IDX), dtype=float)
_MASTER = {"filename": "SYN_WFOOS.csv", "instrument": "SYN_WFOOS", "timeframe": "5m",
          "date_from": "2020-01-01", "date_to": "2020-01-26", "name": "SYN_WFOOS"}


def _fake_find_master(instrument, timeframe, session=None, source=None):
    return dict(_MASTER)


def _fake_load_master_arrays(master, date_from=None, date_to=None):
    idx = _FULL_IDX
    mask = np.ones(len(idx), dtype=bool)
    if date_from:
        mask &= (idx >= pd.Timestamp(date_from, tz="US/Eastern"))
    if date_to:
        mask &= (idx < pd.Timestamp(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
    sub_idx, sub_close = idx[mask], _FULL_CLOSE[mask]
    n = len(sub_close)
    day_id = (pd.factorize(pd.Series(sub_idx).dt.date)[0].astype("int64")
             if n else np.array([], dtype="int64"))
    return {"open": sub_close.copy(), "high": sub_close + 1.0, "low": sub_close - 1.0,
            "close": sub_close.copy(), "volume": np.full(n, 1000.0), "day_id": day_id,
            "index": sub_idx, "meta": master}


def _wfoos_pipeline_strategy():
    """20 varying-pnl trades per slice (some negative) so the pooled block exercises
    profit_factor/avg_loss/drawdown, not only the degenerate all-wins case."""
    mod = types.ModuleType("fake_wfoos_pipeline_strategy")
    mod.STRATEGY_NAME = "SYN WFOOS PIPELINE"
    mod.DEFAULT_PARAMS = {"knob": {"type": "float", "min": 0.0, "max": 10.0,
                                   "step": 0.5, "default": 5.0}}

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        n = len(c)
        trades_n = 20
        base = 50.0 * (n / 100.0) + (10.0 - abs(float(knob) - 3.0))
        pnls = [base / trades_n + (i - trades_n / 2) * 0.5 for i in range(trades_n)]
        total = float(sum(pnls))
        wins = sum(1 for x in pnls if x > 0)
        losses = trades_n - wins
        out = {"total_pnl": total, "num_trades": trades_n, "win_rate": 100.0 * wins / trades_n,
               "profit_factor": 3.0 if total > 0 else 0.3, "max_drawdown": -10.0,
               "avg_pnl": total / trades_n, "wins": max(wins, 5), "losses": max(losses, 5)}
        if return_trades:
            out["trades"] = [(i, i + 1, pnls[i]) for i in range(trades_n)]
        return out

    mod.run_backtest = run_backtest
    return mod


@pytest.fixture()
def _patched_data_layer():
    import augur_engine.auto as auto_mod
    import augur_engine.engine as engine_mod
    import augur_engine.optimize as optimize_mod
    import augur_engine.validate as validate_mod
    mods = (validate_mod, auto_mod, engine_mod, optimize_mod)
    originals = [(m, m.find_master, m.load_master_arrays) for m in mods]
    for m in mods:
        m.find_master = _fake_find_master
        m.load_master_arrays = _fake_load_master_arrays
    try:
        yield
    finally:
        for m, fm, lma in originals:
            m.find_master, m.load_master_arrays = fm, lma


def test_run_validate_saves_a_wf_oos_block_matching_the_pooled_folds(_patched_data_layer):
    from augur_engine.validate import run_validate
    strat = _wfoos_pipeline_strategy()
    res = run_validate(strat, instrument="SYN_WFOOS", timeframe="5m", session="rth",
                       source=None, cost_pts=0.0, min_trades=1, n_trials=10, wf_folds=3,
                       seed=42, lockbox_months=0.2, equity_points=200, select_oos_topk=0)
    assert res["validate"]["wf_ran"] is True
    wf_oos = res["validate"].get("wf_oos")
    assert wf_oos is not None
    folds = res["top"]                      # PRIMARY scheme's fold rows (top10_results)
    assert wf_oos["n_folds"] == len(folds)
    assert wf_oos["mode"] == res["validate"]["wf_best_mode"]
    assert wf_oos["trades"] == sum(int(f["oos_trades"]) for f in folds)
    # net/profit_factor computed from the SAME per-trade data the fold rows already
    # reconcile to (ENGINE_BRIEF D5: "block net/trades/profit_factor must then equal
    # the pooled fold figures").
    assert wf_oos["net"] == pytest.approx(sum(float(f["oos_pnl"]) for f in folds), abs=0.05)
    assert wf_oos["profit_factor"] is None or wf_oos["profit_factor"] > 0
    # per-trade arrays must NOT survive on the returned fold rows (still popped)
    for f in folds:
        for k in ("_oos_pnls", "_oos_mae", "_oos_mfe", "_oos_won"):
            assert k not in f


def test_run_validate_wf_oos_is_none_when_walkforward_did_not_run(_patched_data_layer):
    """Below the n>=4000 walk-forward gate, run_auto silently falls back to a single
    split (auto.py) — wf_ran is False and `folds` is empty, so wf_oos must be None,
    never a crash and never a block built from nothing."""
    from augur_engine.validate import run_validate
    import augur_engine.auto as auto_mod
    import augur_engine.engine as engine_mod
    import augur_engine.optimize as optimize_mod
    import augur_engine.validate as validate_mod
    strat = _wfoos_pipeline_strategy()
    tiny_idx = pd.date_range(pd.Timestamp("2020-01-01", tz="US/Eastern"), periods=500,
                             freq="5min", tz="US/Eastern")
    tiny_close = 1000.0 + np.arange(len(tiny_idx), dtype=float)

    def _tiny_load(master, date_from=None, date_to=None):
        n = len(tiny_idx)
        day_id = pd.factorize(pd.Series(tiny_idx).dt.date)[0].astype("int64")
        return {"open": tiny_close.copy(), "high": tiny_close + 1.0, "low": tiny_close - 1.0,
                "close": tiny_close.copy(), "volume": np.full(n, 1000.0), "day_id": day_id,
                "index": tiny_idx, "meta": master}

    # _patched_data_layer already points every module at the 7200-bar fake (>= the
    # walk-forward n>=4000 gate) — override ALL of them to the tiny (500-bar) loader
    # for this one test, since run_auto itself resolves the module-level name it was
    # imported with (auto_mod.load_master_arrays), not validate.py's.
    mods = (validate_mod, auto_mod, engine_mod, optimize_mod)
    for m in mods:
        m.load_master_arrays = _tiny_load
    res = run_validate(strat, instrument="SYN_WFOOS", timeframe="5m", session="rth",
                       source=None, cost_pts=0.0, min_trades=1, n_trials=5, wf_folds=2,
                       seed=42, lockbox_months=0.1, equity_points=100, select_oos_topk=0)
    assert res["validate"]["wf_ran"] is False
    assert res["validate"].get("wf_oos") is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. D2 — validate.wf_oos.equity survives api/runner.py's shrink_to_fit
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_wf_oos_equity_survives_shrink_to_fit():
    import api.runner as R
    big_equity = [round(float(i) * 1.1, 1) for i in range(5000)]
    doc = {
        "validate": {"wf_oos": {"v": 1, "mode": "rolling", "n_folds": 5,
                                "equity": list(big_equity), "equity_n": 5000,
                                "net": 1234.5, "trades": 5000, "sharpe": 1.2}},
        "junk_field": ["x" * 500] * 3000,      # not protected — pushes size over budget
        "best": {"total_pnl": 999.0},
    }
    before_size = R._doc_size(doc)
    budget = 60_000
    assert before_size > budget
    logs = []
    out = R.shrink_to_fit(doc, budget=budget, log=logs.append, label="wfoos-shrink-test",
                          equity_points=200)
    assert "validate" in out and out["validate"].get("wf_oos") is not None   # never dropped
    eq = out["validate"]["wf_oos"]["equity"]
    assert 0 < len(eq) <= 200                    # stage 1 downsampled it
    assert eq[-1] == pytest.approx(big_equity[-1])   # endpoint-pinned
    assert out["validate"]["wf_oos"]["net"] == 1234.5   # scalar fields untouched
    assert out["best"] == {"total_pnl": 999.0}   # protected field untouched
    assert any("size-guard" in m for m in logs)
