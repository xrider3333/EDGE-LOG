"""Unit tests for #88 — OOS-checked champion selection (augur_engine.validate).

Motivating evidence (see augur_engine/validate.py's Stage A.5 comment block): run
#167 crowned the sharpest realism-gated IN-SAMPLE config (IS $257,873) which then
collapsed on the lockbox ($35,083, PBO gate fired, verdict WEAK), while run #165's
WEAKER-IS champion had DOUBLE the lockbox PnL. `select_oos_topk` re-scores the
top-K in-sample candidates by their walk-forward-fold OOS PnL and crowns the
steadiest one instead of the raw IS-max; the lockbox still only ever sees the ONE
crowned config.

Two layers, mirroring tests/test_auto_expand.py's / test_steering.py's own
conventions:
  1. Direct unit tests of `_select_oos_champion` (augur_engine.validate) — synthetic
     hand-built A/wf_anch fixtures + a tiny synthetic strategy + raw arrays, NO
     find_master/load_master_arrays/run_auto involved at all, so these run in well
     under a second and pin down the candidate-building / dedupe / crowning /
     equity-curve rules precisely.
  2. Full `run_validate(...)` integration tests (monkeypatching `find_master` /
     `load_master_arrays` in every module that imports them directly — validate,
     auto, engine, optimize — with an in-memory synthetic master/strategy) proving
     the flag threads through the real pipeline end-to-end: flag off is byte-
     identical on champion/verdict, flag on actually re-crowns a steadier config in
     a run #165-vs-#167-shaped fixture. These are slower (~5-10s each — Stage A's
     hardcoded compute_surrogate=True/auto_steer=True machinery fits several sklearn
     models regardless of data size) so the module-scoped fixture computes each
     select_oos_topk value's run exactly once and every test function reuses it.
"""
import types

import numpy as np
import pandas as pd
import pytest

from augur_engine.validate import _select_oos_champion, run_validate


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — direct unit tests of _select_oos_champion (no find_master, no run_auto)
# ─────────────────────────────────────────────────────────────────────────────

def _metric_row(knob, total_pnl, num_trades=10, wins=5, losses=5, profit_factor=2.0):
    """A row shaped like one of A["top"]'s entries / A["plateau_pick"]["metrics"] —
    the param dict merged with the _METRIC_KEYS subset real run_auto rows carry."""
    return {"knob": knob, "total_pnl": total_pnl, "num_trades": num_trades,
            "win_rate": 60.0, "profit_factor": profit_factor, "max_drawdown": -10.0,
            "avg_pnl": total_pnl / num_trades, "wins": wins, "losses": losses}


def _make_arrays(n, const=100.0):
    """Tiny constant OHLC — content only matters via `len(c)`/`c[0]` for the
    strategies below, which are pure functions of the slice bounds they're called
    on (mirrors test_auto_expand.py's `_make_arrays` convention)."""
    c = np.full(n, const)
    return {"open": c.copy(), "high": c + 1.0, "low": c - 1.0, "close": c.copy(),
            "volume": None, "day_id": None, "index": None}


def _linear_strategy():
    """total_pnl = knob * (number of bars in the slice) — deterministic, so equity
    curves / fold scores are hand-verifiable exactly."""
    mod = types.ModuleType("fake_linear_strategy")
    mod.STRATEGY_NAME = "SYN LINEAR (selection test)"

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        n = len(c)
        pnl = float(knob) * n
        trades_n = 10
        out = {"total_pnl": pnl, "num_trades": trades_n, "win_rate": 60.0,
               "profit_factor": 2.0 if pnl >= 0 else 0.4, "max_drawdown": -10.0,
               "avg_pnl": pnl / trades_n, "wins": 5, "losses": 5}
        if return_trades:
            out["trades"] = [(i, i + 1, pnl / trades_n, 1, 100.0) for i in range(trades_n)]
        return out

    mod.run_backtest = run_backtest
    return mod


def _is_max_trap_strategy():
    """knob==9.0 is spectacular ONLY when evaluated on a slice whose FIRST close
    value is exactly MARKER (i.e. bar 0 of the array it's handed — the "IS window"
    in this test's usage) and catastrophic anywhere else; every other knob is a
    modest, steady, POSITIVE edge everywhere, peaking near knob=3.0. This is the
    run #165-vs-#167 shape: an IS-max that is pure overfit vs. a steadier runner-up."""
    MARKER = 1000.0
    mod = types.ModuleType("fake_ismax_trap_strategy")
    mod.STRATEGY_NAME = "SYN IS-MAX TRAP (selection test)"

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        n = len(c)
        is_window_start = n > 0 and abs(float(c[0]) - MARKER) < 1e-6
        if abs(float(knob) - 9.0) < 1e-6:
            pnl = 50000.0 if is_window_start else -8000.0 * (n / 100.0)
        else:
            pnl = 50.0 * (n / 100.0) + (10.0 - abs(float(knob) - 3.0))
        trades_n = 10
        pf = 3.0 if pnl > 0 else 0.3
        out = {"total_pnl": float(pnl), "num_trades": trades_n, "win_rate": 60.0,
               "profit_factor": pf, "max_drawdown": -10.0, "avg_pnl": pnl / trades_n,
               "wins": 5, "losses": 5}
        if return_trades:
            out["trades"] = [(i, i + 1, pnl / trades_n, 1, 100.0) for i in range(trades_n)]
        return out

    mod.run_backtest = run_backtest
    return mod, MARKER


# (b) THE KEY TEST — IS-max engineered to do WORSE across folds than candidate #2 ──

def test_is_max_loses_to_steadier_candidate_on_wf_oos_folds():
    mod, MARKER = _is_max_trap_strategy()
    n = 200
    arrays = _make_arrays(n, const=MARKER)   # close[0] == MARKER -> "IS window" shape
    # NOTE: every bar is MARKER here (constant array), matching how make_slice_evaluator
    # slices arrays[a:b] -- a fold test slice (a>0) starts at bar `a`, so its own
    # c[0] would ALSO read MARKER on a truly constant array. To make fold slices look
    # like "not bar 0 of the ORIGINAL IS window" (the real run_validate wiring: the
    # opt-window array's bar 0 is the true IS-window start, and every anchored fold's
    # TEST slice starts strictly after it), build a ramp so only index 0 equals MARKER.
    close = np.full(n, MARKER + 1.0)
    close[0] = MARKER
    arrays = {"open": close.copy(), "high": close + 1, "low": close - 1,
              "close": close.copy(), "volume": None, "day_id": None, "index": None}

    champ = {"knob": 9.0}
    bestA = {"total_pnl": 50000.0, "num_trades": 10, "profit_factor": 3.0, "max_drawdown": -10.0}
    A = {
        "top": [_metric_row(9.0, 50000.0), _metric_row(3.0, 2062.0), _metric_row(3.5, 2061.5)],
        "bars": n,
        "plateau_pick": {},
    }
    wf_anch = {"ran": True, "folds": [
        {"train_bars": 60, "test_bars": 70},     # test slice (60,130) -> a=60 (not bar 0)
        {"train_bars": 130, "test_bars": 70},    # test slice (130,200)
    ]}

    new_champ, new_bestA, sel = _select_oos_champion(mod, arrays, champ, bestA, A, wf_anch,
                                                      cost_pts=0.0, k=5)

    assert sel["error"] is None if "error" in sel else True
    assert sel["mode"] == "wf_oos_topk" and sel["k"] == 5
    assert sel["is_max_crowned"] is False          # the whole point of #88
    assert new_champ == {"knob": 3.0}              # steadier runner-up crowned
    assert new_champ != champ                       # actually changed from IS-max

    by_knob = {c["params"]["knob"]: c for c in sel["candidates"]}
    assert by_knob[9.0]["wf_oos_pnl"] < 0           # IS-max collapses OOS
    assert by_knob[9.0]["folds_held"] == 0
    assert by_knob[3.0]["wf_oos_pnl"] > 0            # steadier config holds up
    assert by_knob[3.0]["folds_held"] == 2
    assert by_knob[3.0]["crowned"] is True
    assert by_knob[9.0]["crowned"] is False
    assert sum(1 for c in sel["candidates"] if c["crowned"]) == 1


# (a) is_max_crowned True when the IS-max ALSO wins the OOS-fold race ──────────

def test_is_max_wins_folds_too_stays_crowned():
    mod = _linear_strategy()
    n = 200
    arrays = _make_arrays(n)
    champ = {"knob": 5.0}
    # NOTE: in a real run_validate call, bestA == A["best"] -- the _METRIC_KEYS-only
    # subset of the same row A["top"][0] carries (params + metrics merged) -- so this
    # test mirrors that shape (metrics only, no "knob" param key) instead of a
    # hand-picked partial dict that would never actually occur.
    bestA = {k: v for k, v in _metric_row(5.0, 1000.0).items() if k != "knob"}
    A = {"top": [_metric_row(5.0, 1000.0), _metric_row(2.0, 400.0)], "bars": n,
         "plateau_pick": {}}
    wf_anch = {"ran": True, "folds": [{"train_bars": 100, "test_bars": 100}]}

    new_champ, new_bestA, sel = _select_oos_champion(mod, arrays, champ, bestA, A, wf_anch,
                                                      cost_pts=0.0, k=5)
    assert sel["is_max_crowned"] is True
    assert new_champ == champ
    assert new_bestA == bestA


# (c) candidate-set construction: K respected, dedupe, plateau reserved-slot +
#     backfill-on-duplicate, exactly one crowned, well-formed equity curves ───────

def test_candidate_set_respects_k_and_dedupes_and_backfills_duplicate_plateau_pick():
    mod = _linear_strategy()
    n = 300
    arrays = _make_arrays(n)
    rows = [_metric_row(kb, is_pnl) for kb, is_pnl in
            [(1.0, 600.0), (2.0, 500.0), (2.0, 500.0),   # exact duplicate of the 2.0 row
             (3.0, 400.0), (4.0, 300.0), (5.0, 200.0)]]
    champ = {"knob": 1.0}
    bestA = _metric_row(1.0, 600.0)
    A = {"top": rows, "bars": n,
         # plateau pick duplicates the (already-included, since budget=k-1=3 takes the
         # first 3 distinct rows: knob 1,2,3) knob=2.0 candidate -> must be skipped and
         # backfilled from the ranked list (knob=4.0) instead, still landing on K=4 total.
         "plateau_pick": {"params": {"knob": 2.0}, "metrics": _metric_row(2.0, 500.0)}}
    wf_anch = {"ran": True, "folds": [{"train_bars": 100, "test_bars": 100},
                                      {"train_bars": 200, "test_bars": 100}]}

    _, _, sel = _select_oos_champion(mod, arrays, champ, bestA, A, wf_anch, cost_pts=0.0, k=4)

    cands = sel["candidates"]
    assert len(cands) == 4                                     # K respected exactly
    knobs = [c["params"]["knob"] for c in cands]
    assert len(set(knobs)) == 4                                # no duplicate signatures
    assert knobs == [1.0, 2.0, 3.0, 4.0]                        # dup plateau -> backfilled with #4
    assert sum(1 for c in cands if c["crowned"]) == 1           # exactly one crowned

    for c in cands:
        eq = c["equity"]
        assert isinstance(eq, dict) and "cum" in eq and "final" in eq
        assert len(eq["cum"]) <= 160
        # _linear_strategy's total_pnl == knob * n_bars, evaluated over the WHOLE
        # passed-in `arrays` (the optimize window, len==n==300) with keep_trades=True,
        # split into 10 equal per-trade slivers that sum back to the exact total —
        # proves the curve covers exactly the optimize window, nothing more/less.
        assert eq["final"] == pytest.approx(round(c["params"]["knob"] * n, 1), abs=0.05)


def test_candidate_set_includes_distinct_plateau_pick_when_not_a_duplicate():
    mod = _linear_strategy()
    n = 100
    arrays = _make_arrays(n)
    rows = [_metric_row(1.0, 600.0), _metric_row(2.0, 500.0)]
    champ = {"knob": 1.0}
    bestA = _metric_row(1.0, 600.0)
    A = {"top": rows, "bars": n,
         "plateau_pick": {"params": {"knob": 7.0}, "metrics": _metric_row(7.0, 50.0)}}
    wf_anch = {"ran": True, "folds": [{"train_bars": 50, "test_bars": 50}]}

    _, _, sel = _select_oos_champion(mod, arrays, champ, bestA, A, wf_anch, cost_pts=0.0, k=3)
    knobs = {c["params"]["knob"] for c in sel["candidates"]}
    assert knobs == {1.0, 2.0, 7.0}                              # plateau pick's own reserved slot


# (c2) robustness split (#88b): CROWN pool stays == k, extra top-IS configs land in
#      `robust` (display-only, never crowned), display_k caps the combined set ─────────
def test_robustness_split_crown_pool_capped_at_k_extras_go_to_robust():
    mod = _linear_strategy()
    n = 300
    arrays = _make_arrays(n)
    # 12 distinct configs, descending IS PnL -> IS-max = knob 12
    rows = [_metric_row(float(kb), float(kb) * 100.0) for kb in range(12, 0, -1)]
    champ = {"knob": 12.0}
    bestA = _metric_row(12.0, 1200.0)
    A = {"top": rows, "bars": n, "plateau_pick": {}}
    wf_anch = {"ran": True, "folds": [{"train_bars": 100, "test_bars": 100},
                                      {"train_bars": 200, "test_bars": 100}]}

    _, _, sel = _select_oos_champion(mod, arrays, champ, bestA, A, wf_anch, cost_pts=0.0, k=5)

    assert sel["display_k"] == 10                                 # max(k, 10)
    assert len(sel["candidates"]) == 5                            # crown pool == k exactly
    assert "robust" in sel and len(sel["robust"]) == 5           # widened to display_k total (5+5)
    # crown pool = the 5 highest-IS configs (knobs 12..8); robust = the next 5 (7..3)
    assert {c["params"]["knob"] for c in sel["candidates"]} == {12.0, 11.0, 10.0, 9.0, 8.0}
    assert {c["params"]["knob"] for c in sel["robust"]} == {7.0, 6.0, 5.0, 4.0, 3.0}
    # exactly one crowned, and it is one of the crown-pool candidates (never a robust extra)
    assert sum(1 for c in sel["candidates"] if c["crowned"]) == 1
    assert all("equity" in c and c["equity"]["cum"] for c in sel["candidates"] + sel["robust"])


# (d) graceful no-op paths — never raises, always returns a well-formed selection dict

def test_no_candidates_returns_untouched_champion_with_error():
    mod = _linear_strategy()
    arrays = _make_arrays(50)
    champ = {"knob": 1.0}
    bestA = _metric_row(1.0, 100.0)
    A = {"top": [], "bars": 50, "plateau_pick": {}}
    wf_anch = {"ran": True, "folds": [{"train_bars": 25, "test_bars": 25}]}

    new_champ, new_bestA, sel = _select_oos_champion(mod, arrays, champ, bestA, A, wf_anch,
                                                      cost_pts=0.0, k=5)
    assert new_champ == champ and new_bestA == bestA
    assert sel["candidates"] == [] and sel["is_max_crowned"] is True
    assert "no realism-gated candidates" in sel["error"]


def test_no_anchored_folds_returns_untouched_champion_with_error():
    mod = _linear_strategy()
    arrays = _make_arrays(50)
    champ = {"knob": 1.0}
    bestA = _metric_row(1.0, 100.0)
    A = {"top": [_metric_row(1.0, 100.0), _metric_row(2.0, 90.0)], "bars": 50,
         "plateau_pick": {}}
    wf_anch_not_ran = {"ran": False, "folds": []}

    new_champ, new_bestA, sel = _select_oos_champion(mod, arrays, champ, bestA, A,
                                                      wf_anch_not_ran, cost_pts=0.0, k=5)
    assert new_champ == champ and new_bestA == bestA
    assert sel["candidates"] == [] and sel["is_max_crowned"] is True
    assert "no anchored walk-forward folds" in sel["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — full run_validate() integration (monkeypatched find_master/
# load_master_arrays across every module that imports them directly).
# ─────────────────────────────────────────────────────────────────────────────

_FULL_LO = pd.Timestamp("2020-01-01", tz="US/Eastern")
_FULL_HI = pd.Timestamp("2020-01-26", tz="US/Eastern")
_FULL_IDX = pd.date_range(_FULL_LO, _FULL_HI, freq="5min", tz="US/Eastern")
_MARKER = 1000.0
_FULL_CLOSE = _MARKER + np.arange(len(_FULL_IDX), dtype=float)   # bar i's close == MARKER + i
_MASTER = {"filename": "SYN_SELECTION_TEST.csv", "instrument": "SYN_SEL", "timeframe": "5m",
           "date_from": _FULL_LO.date().isoformat(), "date_to": _FULL_HI.date().isoformat(),
           "name": "SYN_SEL"}


def _fake_find_master(instrument, timeframe, session=None, source=None):
    return dict(_MASTER)


def _fake_load_master_arrays(master, date_from=None, date_to=None):
    idx = _FULL_IDX
    mask = np.ones(len(idx), dtype=bool)
    if date_from:
        mask &= (idx >= pd.Timestamp(date_from, tz="US/Eastern"))
    if date_to:
        mask &= (idx < pd.Timestamp(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
    sub_idx = idx[mask]
    sub_close = _FULL_CLOSE[mask]
    n = len(sub_close)
    day_id = (pd.factorize(pd.Series(sub_idx).dt.date)[0].astype("int64")
              if n else np.array([], dtype="int64"))
    return {"open": sub_close.copy(), "high": sub_close + 1.0, "low": sub_close - 1.0,
            "close": sub_close.copy(), "volume": np.full(n, 1000.0), "day_id": day_id,
            "index": sub_idx, "meta": master}


def _make_selection_strategy():
    """Same run #165-vs-#167 shape as `_is_max_trap_strategy` above, but keyed off
    the ABSOLUTE bar-0 marker (MARKER) of the full synthetic dataset — knob=9.0 is
    spectacular ONLY when hit with a slice literally starting at the very first bar
    of the whole master (i.e. Stage A's IS-window evaluation, which always starts at
    bar 0 of the [opt_from, opt_to] window here since opt_from == the master's own
    date_from); every anchored walk-forward fold's TEST slice starts strictly later,
    so knob=9.0 cannot cheat there. Every other knob is a modest, steady, POSITIVE
    edge everywhere, peaking near knob=3.0 -- the steadier runner-up."""
    mod = types.ModuleType("fake_full_pipeline_selection_strategy")
    mod.STRATEGY_NAME = "SYN FULL-PIPELINE SELECTION TEST"
    mod.DEFAULT_PARAMS = {
        "knob": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0},
    }

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        n = len(c)
        is_window_start = n > 0 and abs(float(c[0]) - _MARKER) < 1e-6
        if abs(float(knob) - 9.0) < 1e-6:
            pnl = 500000.0 if is_window_start else -20000.0 * (n / 100.0)
        else:
            pnl = 50.0 * (n / 100.0) + (10.0 - abs(float(knob) - 3.0))
        trades_n = 10
        pf = 3.0 if pnl > 0 else 0.3
        out = {"total_pnl": float(pnl), "num_trades": trades_n, "win_rate": 60.0,
               "profit_factor": pf, "max_drawdown": -10.0, "avg_pnl": pnl / trades_n,
               "wins": 5, "losses": 5}
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
            m.find_master = fm
            m.load_master_arrays = lma


@pytest.fixture(scope="module")
def validate_runs(_patched_data_layer):
    """Runs the real run_validate() pipeline exactly 3 times (select_oos_topk=0/1/3)
    against the run #165-vs-#167-shaped synthetic fixture above, cached at module
    scope so every test function below reuses the same results instead of re-paying
    the ~5-10s/call cost of Stage A's hardcoded compute_surrogate/auto_steer
    machinery (sklearn model fits, independent of data size)."""
    strat = _make_selection_strategy()
    kwargs = dict(instrument="SYN_SEL", timeframe="5m", session="rth", source=None,
                  cost_pts=0.0, min_trades=1, n_trials=40, wf_folds=3, seed=42,
                  lockbox_months=0.2, date_from=None, date_to=None,
                  equity_points=200, discover="auto")
    return {
        "k0": run_validate(strat, select_oos_topk=0, **kwargs),
        "k1": run_validate(strat, select_oos_topk=1, **kwargs),
        "k3": run_validate(strat, select_oos_topk=3, **kwargs),
    }


# (a) flag off (0 or 1) -> champion + verdict identical, today's behavior untouched ──

def test_flag_off_topk0_and_topk1_champion_and_verdict_are_identical(validate_runs):
    out0, out1 = validate_runs["k0"], validate_runs["k1"]
    assert out0.get("selection") is None
    assert out1.get("selection") is None
    assert out0["best_params"] == out1["best_params"]
    assert out0["best"] == out1["best"]
    v0, v1 = out0["validate"], out1["validate"]
    assert v0["verdict"] == v1["verdict"]
    assert v0["checks"] == v1["checks"]
    assert v0["champion"] == v1["champion"]
    assert v0["lockbox"] == v1["lockbox"]
    # sanity: the untouched legacy path really does crown the IS-max trap (knob=9.0)
    # in this fixture -- proves the flag-off path is genuinely doing "today's thing".
    assert out0["best_params"] == {"knob": 9.0}


# (b)/(c) flag on, full pipeline: crowns the steadier config, not IS-max ─────────

def test_flag_on_full_pipeline_crowns_steadier_config_not_is_max(validate_runs):
    out0, out3 = validate_runs["k0"], validate_runs["k3"]
    sel = out3.get("selection")
    assert sel is not None
    assert sel["mode"] == "wf_oos_topk" and sel["k"] == 3
    assert sel["is_max_crowned"] is False
    # the crowned champion actually differs from the untouched IS-max path's champion
    assert out3["best_params"] != out0["best_params"]
    assert out3["best_params"]["knob"] != 9.0
    assert out3["validate"]["champion"] == out3["best_params"]   # report + return dict agree


def test_flag_on_candidates_well_formed(validate_runs):
    out3 = validate_runs["k3"]
    sel = out3["selection"]
    cands = sel["candidates"]
    assert 1 <= len(cands) <= 3                                 # K respected
    assert len(set(tuple(sorted(c["params"].items())) for c in cands)) == len(cands)  # deduped
    assert sum(1 for c in cands if c["crowned"]) == 1            # exactly one crowned
    crowned = next(c for c in cands if c["crowned"])
    assert crowned["params"] == out3["best_params"]              # crowned candidate == final champion
    for c in cands:
        assert "is_pnl" in c and "wf_oos_pnl" in c and "folds_held" in c
        eq = c["equity"]
        assert isinstance(eq, dict) and "cum" in eq and "final" in eq
        assert isinstance(eq["cum"], list) and len(eq["cum"]) <= 160
