"""ENGU-Q R62 (session-window sibling) - the guards its docstring promises.

Written after the 2026-09-30 audit found the docstring claiming "asserted by the round's own
harness" when no harness existed. The precedent is tests/test_enguq_sel_parity.py, which does the
same job for the round-57 sibling.

What is locked down here:
  1. window OFF reproduces the parent TRADE FOR TRADE (not just counts);
  2. compiled and interpreted walks agree trade for trade with the window ON;
  3. narrowing the window with NO bar index raises instead of going silently inert;
  4. an index of the wrong length raises instead of being read out of bounds by the njit walk,
     which is compiled without boundscheck;
  5. the declared search grid can actually reach the OFF cell and both deployed arms - an
     Auto-Validate that cannot evaluate the cell it is validating is worse than no validate.
"""
import importlib.util
import os

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.join(ROOT, "augur_strategies", "ENGUQ_1M_ETH_R2_1_0.py")
CHILD = os.path.join(ROOT, "augur_strategies", "ENGUQ_1M_ETH_R62_1_0.py")


def _load(path):
    spec = importlib.util.spec_from_file_location("s_" + os.path.basename(path), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bars():
    """A long random walk with intraday shape - enough to make this engine actually trade."""
    rng = np.random.default_rng(20260930)
    n = 120_000
    step = rng.normal(0, 1.6, n).cumsum()
    close = 15000.0 + step + 40.0 * np.sin(np.arange(n) / 720.0)
    wig = np.abs(rng.normal(0, 1.4, n))
    high = close + wig
    low = close - np.abs(rng.normal(0, 1.4, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.integers(40, 900, n).astype(float)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="America/New_York")
    return dict(open=open_, high=high, low=low, close=close, volume=vol, index=idx)


def _run(mod, bars, **over):
    p = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    p.update(over)
    sig = mod.run_backtest.__code__.co_varnames[:mod.run_backtest.__code__.co_argcount]
    kw = {k: v for k, v in p.items() if k in sig}
    if "index" in sig:
        kw["index"] = bars["index"]
    return mod.run_backtest(bars["open"], bars["high"], bars["low"], bars["close"],
                            volumes=bars["volume"], return_trades=True, **kw)


def test_window_off_reproduces_the_parent_trade_for_trade(bars):
    parent, child = _load(PARENT), _load(CHILD)
    shared = {k: v["default"] for k, v in parent.DEFAULT_PARAMS.items()}
    a = _run(parent, bars, **shared)
    b = _run(child, bars, sess_from=0, sess_to=2400, **shared)
    assert len(a["trades"]) > 20, "fixture produced too few trades to be a real parity check"
    assert a["trades"] == b["trades"]


def test_compiled_and_interpreted_agree_with_the_window_on(bars, monkeypatch):
    child = _load(CHILD)
    on = _run(child, bars, sess_from=930, sess_to=1600)
    monkeypatch.setenv("EDGELOG_NO_FASTLOOP", "1")
    slow = _load(CHILD)
    monkeypatch.setattr(slow, "_fl", None, raising=False)
    assert on["trades"] == _run(slow, bars, sess_from=930, sess_to=1600)["trades"]


def test_a_narrowed_window_without_an_index_raises(bars):
    child = _load(CHILD)
    p = {k: v["default"] for k, v in child.DEFAULT_PARAMS.items()}
    p.update(sess_from=930, sess_to=1600)
    p.pop("index", None)
    with pytest.raises(ValueError, match="no bar index"):
        child.run_backtest(bars["open"], bars["high"], bars["low"], bars["close"],
                           volumes=bars["volume"], index=None, **p)


def test_a_short_index_raises_rather_than_reading_out_of_bounds(bars):
    child = _load(CHILD)
    p = {k: v["default"] for k, v in child.DEFAULT_PARAMS.items()}
    p.update(sess_from=930, sess_to=1600)
    with pytest.raises(ValueError, match="timestamps for"):
        child.run_backtest(bars["open"], bars["high"], bars["low"], bars["close"],
                           volumes=bars["volume"], index=bars["index"][:-5], **p)


@pytest.mark.parametrize("knob,value", [
    ("sess_from", 0), ("sess_from", 800), ("sess_from", 930),
    ("sess_to", 1600), ("sess_to", 1700), ("sess_to", 2400),
])
def test_the_search_grid_can_reach_the_cells_we_actually_run(knob, value):
    """augur_engine/auto.py walks an int knob as lo + step*k, so a cell off that lattice can
    never be evaluated. The OFF cell and both shadow arms must be on it."""
    m = _load(CHILD).DEFAULT_PARAMS[knob]
    lo, hi, step = int(m["min"]), int(m["max"]), int(m["step"])
    assert lo <= value <= hi, "%s=%d outside declared range %d..%d" % (knob, value, lo, hi)
    assert (value - lo) % step == 0, "%s=%d is off the lo+step*k lattice" % (knob, value)
