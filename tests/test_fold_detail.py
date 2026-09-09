"""Unit tests for the two opt-in blind-spot closers in augur_engine.validate:

  save_fold_detail  — an Auto-Validate stored `folds_held` (a COUNT) and `wf_oos_pnl`
      (a TOTAL) per candidate, so after the run you could not tell a config that won
      every fold from one carried by a single lucky fold. The flag saves the PER-FOLD
      row the walk-forward scoring already produced (nothing is re-run).
  oos_sample_k      — `points` (the searched cloud) carried IN-SAMPLE pnl/dd only and
      out-of-sample truth existed for the ten hand-picked winners alone, so "does this
      REGION of the parameter space generalise?" had no answer. The flag scores a
      STRATIFIED sample of the cloud (deciles of in-sample net, random draw inside
      each) on the same walk-forward folds the crown pool uses.

Both default OFF. The first test in each group pins the no-op: with the flag off the
saved shape is exactly what it was before the flags existed.

Conventions follow tests/test_selection.py (synthetic module strategy + raw arrays for
the direct unit layer; monkeypatched find_master/load_master_arrays for the full
run_validate layer), which these tests deliberately reuse.
"""
import types

import numpy as np
import pandas as pd
import pytest

from augur_engine import validate as V
from augur_engine.auto import score_candidates_on_folds
from augur_engine.validate import (_select_oos_champion, _stratified_oos_sample,
                                   _apply_fold_budget, _anchored_fold_bounds,
                                   run_validate)


# ─────────────────────────────────────────────────────────────────────────────
# fixtures (mirroring tests/test_selection.py's own)
# ─────────────────────────────────────────────────────────────────────────────

def _metric_row(knob, total_pnl, num_trades=10):
    return {"knob": knob, "total_pnl": total_pnl, "num_trades": num_trades,
            "win_rate": 60.0, "profit_factor": 2.0, "max_drawdown": -10.0,
            "avg_pnl": total_pnl / num_trades, "wins": 5, "losses": 5}


def _make_arrays(n, const=100.0, with_index=False):
    c = np.full(n, const)
    idx = (pd.date_range("2020-01-01", periods=n, freq="5min", tz="US/Eastern")
           if with_index else None)
    return {"open": c.copy(), "high": c + 1.0, "low": c - 1.0, "close": c.copy(),
            "volume": None, "day_id": None, "index": idx}


def _knob_strategy():
    """total_pnl scales with the knob AND with how far into the array the slice starts,
    so different folds genuinely produce different per-fold numbers (a constant-per-fold
    strategy would make the "sums to wf_oos_pnl" test vacuous)."""
    mod = types.ModuleType("fake_fold_detail_strategy")
    mod.STRATEGY_NAME = "SYN FOLD DETAIL"

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        n = len(c)
        pnl = float(knob) * n + float(c[0])      # c[0] differs per slice on a ramp array
        trades_n = 10
        out = {"total_pnl": pnl, "num_trades": trades_n, "win_rate": 60.0,
               "profit_factor": 2.0 if pnl >= 0 else 0.4, "max_drawdown": -12.5,
               "avg_pnl": pnl / trades_n, "wins": 5, "losses": 5}
        if return_trades:
            out["trades"] = [(i, i + 1, pnl / trades_n, 1, 100.0) for i in range(trades_n)]
        return out

    mod.run_backtest = run_backtest
    return mod


def _ramp_arrays(n, with_index=True):
    close = 100.0 + np.arange(n, dtype=float)
    idx = (pd.date_range("2020-01-01", periods=n, freq="5min", tz="US/Eastern")
           if with_index else None)
    return {"open": close.copy(), "high": close + 1.0, "low": close - 1.0,
            "close": close.copy(), "volume": None, "day_id": None, "index": idx}


_WF_ANCH = {"ran": True, "folds": [{"train_bars": 60, "test_bars": 70},
                                   {"train_bars": 130, "test_bars": 70}]}


def _A_block(n, knobs=(5.0, 4.0, 3.0, 2.0, 1.0)):
    return {"top": [_metric_row(k, k * 100.0) for k in knobs], "bars": n,
            "plateau_pick": {}}


# ─────────────────────────────────────────────────────────────────────────────
# 1. save_fold_detail
# ─────────────────────────────────────────────────────────────────────────────

def test_flag_off_is_a_no_op_no_folds_key_anywhere():
    """Default OFF: not one candidate/robust row grows a `folds` key, and no
    `folds_trimmed` marker appears — the saved shape is exactly the old one."""
    mod = _knob_strategy()
    arrays = _ramp_arrays(200)
    _, _, sel = _select_oos_champion(mod, arrays, {"knob": 5.0}, _metric_row(5.0, 500.0),
                                     _A_block(200), _WF_ANCH, cost_pts=0.0, k=3)
    assert "folds_trimmed" not in sel
    for c in (sel["candidates"] + sel.get("robust", [])):
        assert "folds" not in c
        assert "_fold_rows" not in c


def test_fold_detail_sums_to_the_existing_wf_oos_pnl_and_folds_held():
    """The saved per-fold nets add back up to the `wf_oos_pnl` total that was already
    being stored, and the `held` flags add back up to `folds_held` — i.e. the detail is
    a decomposition of the existing number, not a second, differently-computed one."""
    mod = _knob_strategy()
    arrays = _ramp_arrays(200)
    _, _, sel = _select_oos_champion(mod, arrays, {"knob": 5.0}, _metric_row(5.0, 500.0),
                                     _A_block(200), _WF_ANCH, cost_pts=0.0, k=3,
                                     save_fold_detail=True)
    rows = sel["candidates"] + sel.get("robust", [])
    assert rows
    for c in rows:
        folds = c["folds"]
        assert len(folds) == len(_WF_ANCH["folds"])          # capped at the fold count
        assert [f["f"] for f in folds] == [0, 1]
        assert sum(f["net"] for f in folds) == pytest.approx(c["wf_oos_pnl"], abs=0.11)
        assert sum(1 for f in folds if f["held"]) == c["folds_held"]
        # per-fold rows genuinely differ (the ramp strategy makes each fold distinct),
        # which is the whole point: "won every fold" vs "one lucky fold" is now visible.
        assert len({f["net"] for f in folds}) == len(folds)
        for f in folds:
            assert set(("f", "trades", "net", "pf", "dd", "held", "from", "to")) >= set(f)
            assert f["dd"] >= 0                                # magnitude, not signed
            assert f["from"] <= f["to"]


def test_fold_detail_carries_fold_date_ranges_from_the_bar_index():
    mod = _knob_strategy()
    arrays = _ramp_arrays(200)
    _, _, sel = _select_oos_champion(mod, arrays, {"knob": 5.0}, _metric_row(5.0, 500.0),
                                     _A_block(200), _WF_ANCH, cost_pts=0.0, k=3,
                                     save_fold_detail=True)
    idx = arrays["index"]
    bounds = _anchored_fold_bounds(_WF_ANCH)
    want = [(str(pd.Timestamp(idx[a]).date()), str(pd.Timestamp(idx[b - 1]).date()))
            for a, b in bounds]
    got = [(f["from"], f["to"]) for f in sel["candidates"][0]["folds"]]
    assert got == want


def test_fold_detail_omits_dates_when_the_arrays_carry_no_index():
    mod = _knob_strategy()
    arrays = _ramp_arrays(200, with_index=False)
    _, _, sel = _select_oos_champion(mod, arrays, {"knob": 5.0}, _metric_row(5.0, 500.0),
                                     _A_block(200), _WF_ANCH, cost_pts=0.0, k=3,
                                     save_fold_detail=True)
    for f in sel["candidates"][0]["folds"]:
        assert "from" not in f and "to" not in f
        assert "net" in f and "trades" in f


def test_score_candidates_on_folds_reports_dd_without_changing_the_old_keys():
    """The per-fold drawdown rides along on the backtest that was already run — the
    keys every existing caller reads are untouched."""
    mod = _knob_strategy()
    arrays = _ramp_arrays(200)
    rows = score_candidates_on_folds(mod, arrays, [{"knob": 5.0}],
                                     _anchored_fold_bounds(_WF_ANCH))[0]
    for r in rows:
        assert set(r) == {"oos_pnl", "oos_pf", "oos_trades", "oos_dd", "held"}
        assert r["oos_dd"] == pytest.approx(12.5)      # magnitude of max_drawdown=-12.5


# ─────────────────────────────────────────────────────────────────────────────
# 2. the 1 MiB (Firestore doc-cap) trim path
# ─────────────────────────────────────────────────────────────────────────────

def _sel_with_folds(n_cfgs=12, n_folds=8):
    return {"candidates": [{"params": {"knob": float(i)},
                            "folds": [{"f": f, "from": "2020-01-01", "to": "2020-03-01",
                                       "trades": 40, "net": 1234.5, "pf": 1.23, "dd": 99.9,
                                       "held": True} for f in range(n_folds)]}
                           for i in range(n_cfgs)]}


def test_trim_does_nothing_under_budget():
    sel = _sel_with_folds(2, 2)
    assert _apply_fold_budget(sel) is False
    assert sel["folds_trimmed"] is False
    assert "pf" in sel["candidates"][0]["folds"][0]      # full rows kept


def test_trim_path_triggers_over_budget_and_drops_to_net_plus_trades():
    sel = _sel_with_folds(12, 8)
    assert _apply_fold_budget(sel, budget=200) is True
    assert sel["folds_trimmed"] is True
    for c in sel["candidates"]:
        for f in c["folds"]:
            assert set(f) == {"f", "net", "trades"}     # dates/pf/dd/held dropped
    assert len(sel["candidates"][0]["folds"]) == 8       # still one row per fold


def test_trim_uses_the_module_budget_and_covers_oos_sample_rows_too():
    sel = _sel_with_folds(3, 4)
    sel["oos_sample"] = [{"params": {"knob": 9.0},
                          "folds": [{"f": 0, "from": "2020-01-01", "to": "2020-03-01",
                                     "trades": 12, "net": 5.0, "pf": 1.1, "dd": 3.0,
                                     "held": True}]}]
    old = V._FOLD_DETAIL_BUDGET_BYTES
    V._FOLD_DETAIL_BUDGET_BYTES = 50
    try:
        assert _apply_fold_budget(sel) is True
    finally:
        V._FOLD_DETAIL_BUDGET_BYTES = old
    assert set(sel["oos_sample"][0]["folds"][0]) == {"f", "net", "trades"}


def test_trim_no_op_when_nothing_carries_folds():
    sel = {"candidates": [{"params": {"knob": 1.0}}], "robust": []}
    assert _apply_fold_budget(sel) is False
    assert sel["folds_trimmed"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. the stratified out-of-sample sampler
# ─────────────────────────────────────────────────────────────────────────────

def _cloud(n=200):
    """A searched cloud shaped like A["points"]: param dict + in-sample pnl + dd."""
    return [{"knob": round(0.05 * i, 3), "pnl": float(i * 10), "dd": 20.0} for i in range(n)]


def test_sampler_off_by_default_returns_nothing_for_k_zero():
    mod = _knob_strategy()
    assert _stratified_oos_sample(mod, _ramp_arrays(200), _cloud(), ["knob"],
                                  _anchored_fold_bounds(_WF_ANCH), set(), 0) == []


def test_sampler_spans_the_in_sample_score_range_not_just_the_top():
    """The point of the flag: unlike the top-k, the sample must reach the BOTTOM of the
    in-sample score range as well as the top, and cover most deciles."""
    mod = _knob_strategy()
    cloud = _cloud(200)
    smp = _stratified_oos_sample(mod, _ramp_arrays(200), cloud, ["knob"],
                                 _anchored_fold_bounds(_WF_ANCH), set(), 30, seed=42)
    assert len(smp) == 30
    lo_all = min(p["pnl"] for p in cloud)
    hi_all = max(p["pnl"] for p in cloud)
    deciles = {s["decile"] for s in smp}
    assert deciles == set(range(10))                      # every decile represented
    assert min(s["decile"] for s in smp) == 0 and max(s["decile"] for s in smp) == 9
    # the drawn configs really do straddle the range, not cluster at one end
    lo_s = min(s["is_pnl"] for s in smp)
    hi_s = max(s["is_pnl"] for s in smp)
    span = (hi_s - lo_s) / (hi_all - lo_all)
    assert span > 0.8, span
    assert lo_s < lo_all + 0.15 * (hi_all - lo_all)
    assert hi_s > hi_all - 0.15 * (hi_all - lo_all)


def test_sampler_never_duplicates_a_topk_config_or_itself():
    mod = _knob_strategy()
    cloud = _cloud(200)
    # pretend the top-10 candidates were the ten highest-PnL configs
    top = sorted(cloud, key=lambda p: -p["pnl"])[:10]
    excl = {(("knob", p["knob"]),) for p in top}
    smp = _stratified_oos_sample(mod, _ramp_arrays(200), cloud, ["knob"],
                                 _anchored_fold_bounds(_WF_ANCH), excl, 40, seed=7)
    sigs = [(("knob", s["params"]["knob"]),) for s in smp]
    assert len(set(sigs)) == len(sigs)                    # no internal duplicates
    assert not (set(sigs) & excl)                          # and never a top-k config


def test_sampler_rows_have_the_candidate_shape_and_real_oos_numbers():
    mod = _knob_strategy()
    bounds = _anchored_fold_bounds(_WF_ANCH)
    smp = _stratified_oos_sample(mod, _ramp_arrays(200), _cloud(60), ["knob"], bounds,
                                 set(), 8, seed=42, save_fold_detail=True)
    assert smp
    for s in smp:
        assert set(s) >= {"params", "decile", "is_pnl", "is_dd", "metrics",
                          "wf_oos_pnl", "folds_held", "n_folds", "folds"}
        assert s["n_folds"] == len(bounds)
        assert 0 <= s["folds_held"] <= s["n_folds"]
        assert s["metrics"]["num_trades"] == 10
        assert sum(f["net"] for f in s["folds"]) == pytest.approx(s["wf_oos_pnl"], abs=0.11)
    # the walk-forward numbers are NOT copies of the in-sample ones (they are a real
    # out-of-sample scoring of the same config, which is the whole deliverable)
    assert any(abs(s["wf_oos_pnl"] - s["is_pnl"]) > 1e-6 for s in smp)


def test_sampler_is_deterministic_for_a_given_seed():
    mod = _knob_strategy()
    args = (mod, _ramp_arrays(200), _cloud(120), ["knob"],
            _anchored_fold_bounds(_WF_ANCH), set(), 15)
    a = _stratified_oos_sample(*args, seed=42)
    b = _stratified_oos_sample(*args, seed=42)
    c = _stratified_oos_sample(*args, seed=99)
    assert [x["params"] for x in a] == [x["params"] for x in b]
    assert [x["params"] for x in a] != [x["params"] for x in c]


def test_sampler_handles_a_cloud_smaller_than_k_and_missing_param_keys():
    mod = _knob_strategy()
    bounds = _anchored_fold_bounds(_WF_ANCH)
    cloud = _cloud(4) + [{"pnl": 1.0, "dd": 1.0}]          # last row has no "knob"
    smp = _stratified_oos_sample(mod, _ramp_arrays(200), cloud, ["knob"], bounds, set(), 50)
    assert len(smp) == 4                                    # the malformed row is skipped
    assert _stratified_oos_sample(mod, _ramp_arrays(200), [], ["knob"], bounds, set(), 5) == []
    assert _stratified_oos_sample(mod, _ramp_arrays(200), cloud, ["knob"], [], set(), 5) == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. full run_validate wiring (both flags), on tests/test_selection.py's fixture
# ─────────────────────────────────────────────────────────────────────────────

_FULL_IDX = pd.date_range(pd.Timestamp("2020-01-01", tz="US/Eastern"),
                          pd.Timestamp("2020-01-26", tz="US/Eastern"), freq="5min",
                          tz="US/Eastern")
_MARKER = 1000.0
_FULL_CLOSE = _MARKER + np.arange(len(_FULL_IDX), dtype=float)
_MASTER = {"filename": "SYN_FOLD_DETAIL.csv", "instrument": "SYN_FD", "timeframe": "5m",
           "date_from": "2020-01-01", "date_to": "2020-01-26", "name": "SYN_FD"}


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


def _pipeline_strategy():
    mod = types.ModuleType("fake_fold_detail_pipeline_strategy")
    mod.STRATEGY_NAME = "SYN FOLD-DETAIL PIPELINE"
    mod.DEFAULT_PARAMS = {"knob": {"type": "float", "min": 0.0, "max": 10.0,
                                   "step": 0.5, "default": 5.0}}

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        n = len(c)
        pnl = 50.0 * (n / 100.0) + (10.0 - abs(float(knob) - 3.0))
        trades_n = 10
        out = {"total_pnl": float(pnl), "num_trades": trades_n, "win_rate": 60.0,
               "profit_factor": 3.0 if pnl > 0 else 0.3, "max_drawdown": -10.0,
               "avg_pnl": pnl / trades_n, "wins": 5, "losses": 5}
        if return_trades:
            out["trades"] = [(i, i + 1, pnl / trades_n, 1, 100.0) for i in range(trades_n)]
        return out

    mod.run_backtest = run_backtest
    return mod


@pytest.fixture(scope="module")
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


@pytest.fixture(scope="module")
def _runs(_patched_data_layer):
    kwargs = dict(instrument="SYN_FD", timeframe="5m", session="rth", source=None,
                  cost_pts=0.0, min_trades=1, n_trials=40, wf_folds=3, seed=42,
                  lockbox_months=0.2, equity_points=200, select_oos_topk=5)
    strat = _pipeline_strategy()
    return {"off": run_validate(strat, **kwargs),
            "on": run_validate(strat, save_fold_detail=True, oos_sample_k=12, **kwargs)}


def test_pipeline_flags_off_saves_no_new_blocks(_runs):
    sel = _runs["off"]["selection"]
    assert "oos_sample" not in sel
    assert "oos_sample_k" not in sel and "folds_trimmed" not in sel
    for c in sel["candidates"] + sel.get("robust", []):
        assert "folds" not in c


def test_pipeline_flags_off_and_on_crown_the_identical_champion(_runs):
    """The evidence blocks must never move the crown: same champion, same verdict,
    same lockbox, with the flags on."""
    off, on = _runs["off"], _runs["on"]
    assert on["best_params"] == off["best_params"]
    assert on["best"] == off["best"]
    assert on["validate"]["verdict"] == off["validate"]["verdict"]
    assert on["validate"]["lockbox"] == off["validate"]["lockbox"]
    assert on["validate"]["checks"] == off["validate"]["checks"]


def test_pipeline_flags_on_writes_fold_detail_and_the_oos_sample(_runs):
    sel = _runs["on"]["selection"]
    assert sel["folds_trimmed"] is False
    assert sel["oos_sample_k"] == 12
    assert "oos_sample_error" not in sel
    for c in sel["candidates"] + sel.get("robust", []):
        assert c["folds"] and sum(f["net"] for f in c["folds"]) == pytest.approx(
            c["wf_oos_pnl"], abs=0.11)
        assert all("from" in f and "to" in f for f in c["folds"])
    smp = sel["oos_sample"]
    assert smp and len(smp) <= 12
    # never a duplicate of a config that was already scored out of sample as a candidate
    cand_sigs = {tuple(sorted((c["params"] or {}).items()))
                 for c in sel["candidates"] + sel.get("robust", [])}
    smp_sigs = [tuple(sorted(s["params"].items())) for s in smp]
    assert len(set(smp_sigs)) == len(smp_sigs)
    assert not (set(smp_sigs) & cand_sigs)
    for s in smp:
        assert set(s) >= {"params", "decile", "is_pnl", "is_dd", "wf_oos_pnl",
                          "folds_held", "n_folds", "folds", "lockbox"}
