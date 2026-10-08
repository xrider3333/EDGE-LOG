"""A failing whole-window backtest must not destroy the run, and must say why it failed.

THE CRASH. All four whole-run figures (Sharpe, Sortino, drawdown, trade count) come from one
extra full-window backtest of the champion, wrapped in `except Exception: full = None` so that a
failure there is survivable. It was not. The IS|WF split date was initialised INSIDE the gate
block, which is entered only when there is a champion, the full arrays loaded and that backtest
returned trades - so when the backtest failed, the name was unbound and run_validate died with
UnboundLocalError while assembling the report, after the tuning, the walk-forward, the lockbox and
the gate had all been paid for. The swallowing except made the crash MORE likely rather than
safer.

WHAT THESE TESTS PIN. That the run survives, that the figures are absent rather than wrong, and
that the reason is recorded - because four nulls on their own are indistinguishable from a run
saved before those fields existed, which is exactly why EXPLORE can only print a bare dash for
them.

NOT a test of the figures' values; test_selection.py already drives the champion path.
"""
import types

import numpy as np
import pandas as pd
import pytest

from augur_engine.validate import run_validate

_LO = pd.Timestamp("2020-01-01", tz="US/Eastern")
_HI = pd.Timestamp("2020-01-26", tz="US/Eastern")
_IDX = pd.date_range(_LO, _HI, freq="5min", tz="US/Eastern")
_CLOSE = 1000.0 + np.arange(len(_IDX), dtype=float)
_MASTER = {"filename": "SYN_WHOLERUN.csv", "instrument": "SYN_WR", "timeframe": "5m",
           "date_from": _LO.date().isoformat(), "date_to": _HI.date().isoformat(),
           "name": "SYN_WR"}


def _fake_find_master(instrument, timeframe, session=None, source=None):
    return dict(_MASTER)


def _fake_load_master_arrays(master, date_from=None, date_to=None):
    mask = np.ones(len(_IDX), dtype=bool)
    if date_from:
        mask &= (_IDX >= pd.Timestamp(date_from, tz="US/Eastern"))
    if date_to:
        mask &= (_IDX < pd.Timestamp(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
    si, sc = _IDX[mask], _CLOSE[mask]
    n = len(sc)
    day_id = (pd.factorize(pd.Series(si).dt.date)[0].astype("int64")
              if n else np.array([], dtype="int64"))
    return {"open": sc.copy(), "high": sc + 1.0, "low": sc - 1.0, "close": sc.copy(),
            "volume": np.full(n, 1000.0), "day_id": day_id, "index": si, "meta": master}


def _strategy(fail_whole_window):
    """One knob so the tuner has something to search; optionally raises on the whole-window call.

    The whole-window backtest is the one asking for trades over a slice as long as the entire
    dataset, which is what `fail_whole_window` keys off - the same shape a real failure takes.
    """
    mod = types.ModuleType("fake_wholerun_strategy")
    mod.STRATEGY_NAME = "SYN WHOLE-RUN FIGURES TEST"
    mod.DEFAULT_PARAMS = {
        "knob": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0},
    }

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        n = len(c)
        if fail_whole_window and return_trades and n >= len(_CLOSE):
            raise RuntimeError("synthetic whole-window failure")
        pnl = 50.0 * (n / 100.0) + (10.0 - abs(float(knob or 0.0) - 3.0))
        tn = 10
        out = {"total_pnl": float(pnl), "num_trades": tn, "win_rate": 60.0,
               "profit_factor": 3.0 if pnl > 0 else 0.3, "max_drawdown": -10.0,
               "avg_pnl": pnl / tn, "wins": 5, "losses": 5}
        if return_trades:
            step = max(1, (n - 2) // tn)
            out["trades"] = [(i * step, i * step + 1, pnl / tn, 1, 100.0) for i in range(tn)]
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


_KWARGS = dict(instrument="SYN_WR", timeframe="5m", session="rth", source=None,
               cost_pts=0.0, min_trades=1, n_trials=4, wf_folds=3, seed=42,
               lockbox_months=0.2, date_from=None, date_to=None, equity_points=200,
               discover="auto", warm_days=0)


@pytest.fixture(scope="module")
def failed_run(_patched_data_layer):
    return run_validate(_strategy(True), **_KWARGS)


@pytest.fixture(scope="module")
def good_run(_patched_data_layer):
    return run_validate(_strategy(False), **_KWARGS)


def test_a_failed_whole_window_backtest_does_not_destroy_the_run(failed_run):
    """THE CRASH. This raised UnboundLocalError while assembling the report - every stage of the
    run computed and then thrown away. Reaching a report at all is the thing being pinned."""
    assert isinstance(failed_run, dict)
    v = failed_run.get("validate")
    assert isinstance(v, dict) and v, "the run produced no validate report"
    assert failed_run.get("best_params"), "the champion is gone, so this is a different failure"


def test_the_split_date_is_absent_rather_than_fatal(failed_run):
    """The gate block's own comment promises a failure there just leaves the split absent. It
    could not keep that promise while the name it sets was initialised inside the block."""
    assert "wf_split" in failed_run["validate"]["windows"]
    assert failed_run["validate"]["windows"]["wf_split"] is None


def test_the_four_whole_run_figures_are_absent_not_wrong(failed_run):
    """Absent is the honest answer: the backtest they come from never returned."""
    v = failed_run["validate"]
    for k in ("total_sharpe", "total_sortino", "total_dd", "total_trades"):
        assert v.get(k) is None, (k, v.get(k))


def test_the_reason_is_recorded_and_names_the_failure(failed_run):
    """Four nulls alone are indistinguishable from a run saved before these fields existed, which
    is why EXPLORE can only print a bare dash. The reason is what lets a dash explain itself."""
    err = failed_run["validate"].get("total_err")
    assert err, "the figures are missing with no reason recorded"
    assert "whole-window backtest" in err
    assert "RuntimeError" in err and "synthetic whole-window failure" in err


def test_a_healthy_run_records_no_reason_and_keeps_its_figures(good_run):
    """The fix must not make every run look broken: with the backtest working, the figures are
    there and there is nothing to explain."""
    v = good_run["validate"]
    assert v.get("total_err") is None, v.get("total_err")
    assert v.get("total_trades"), "a healthy run saved no whole-run trade count"
    assert v.get("total_dd") is not None
