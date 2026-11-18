"""Invariance probe on a binary-exact tick grid (TBIS 11-18, MANAGER GO).

RTY's 0.1 tick is not exact in binary, so price + C changed the rounding of differences and
the shift test scored a truly difference-invariant file below 1.0 (ENGU-Q R2 on RTY: 0.9935).
Non-dyadic roots are now probed on a surrogate grid; dyadic roots (NQ/ES/YM/ZN) are untouched.
"""
import logging
import types

import numpy as np
import pytest

from augur_engine import rolls as R


def _mod(fn):
    m = types.ModuleType("probe_mod")
    m.run_backtest = fn
    return m


def _diff_tie(o, h, l, c, return_trades=False, **_):
    """Difference logic with exact-tick thresholds: enters when a 1-bar rise is >= 3 ticks."""
    tick = _diff_tie.tick
    d = c[1:] - c[:-1]
    trades = [(i + 1, i + 3, 0.0, 1, float(c[i + 1])) for i in np.flatnonzero(d >= 3 * tick)
              if i + 3 < len(c)]
    return {"trades": trades}


def _level(o, h, l, c, return_trades=False, **_):
    """Level logic: enters whenever the close is above a fixed price."""
    trades = [(i, i + 1, 0.0, 1, float(c[i])) for i in np.flatnonzero(c > _level.lvl) if i + 1 < len(c)]
    return {"trades": trades}


def _boom(o, h, l, c, return_trades=False, **_):
    raise ValueError("synthetic crash")


def _tape(tick, base, n=4000, seed=7, noisy=True):
    rng = np.random.default_rng(seed)
    steps = rng.integers(-4, 5, n)
    c = base + np.cumsum(steps) * tick
    if not noisy:                      # exactly representable values, rebuilt from integers
        c = (np.round(base / tick) + np.cumsum(steps)) * tick
    o = np.r_[c[0], c[:-1]]
    t = 1583020800 + 60 * np.arange(n)          # 2020-03-01, minute bars (spans RTY/ZN switches)
    arrays = {"open": o, "high": np.maximum(o, c), "low": np.minimum(o, c), "close": c,
              "meta": {"instrument": "x", "source": "test", "timeframe": "1m"}}
    return arrays, t


@pytest.fixture(autouse=True)
def _fresh_cache():
    R._CLASS_CACHE.clear()
    yield
    R._CLASS_CACHE.clear()


@pytest.mark.parametrize("root", ["NQ", "MNQ", "ES", "MES", "YM", "MYM", "ZN"])
def test_dyadic_roots_take_the_unchanged_path(root):
    assert R.exact_grid(root, np.array([1.0]))[1] is None


@pytest.mark.parametrize("root", ["RTY", "M2K"])
def test_decimal_tick_roots_get_the_surrogate_grid(root):
    (x,), f = R.exact_grid(root, np.array([2000.1, 2000.2, 2000.3]))
    assert f == pytest.approx(1.25)
    assert list(np.diff(x)) == [0.125, 0.125]  # one RTY tick == one exact 1/8 step
    assert abs(x[1] - 2000.2) < 0.125          # levels stay where they were (median anchor)


def test_unknown_root_unchanged():
    assert R.exact_grid("CL", np.array([1.0]))[1] is None


@pytest.mark.parametrize("root,tick,base", [("RTY", 0.1, 2000.0), ("ZN", 1.0 / 64, 120.0)])
@pytest.mark.parametrize("noisy", [True, False])
def test_difference_file_is_shift_invariant(root, tick, base, noisy):
    _diff_tie.tick = tick
    arrays, t = _tape(tick, base, noisy=noisy)
    inv = R.invariance(_mod(_diff_tie), arrays, root, t, 60, strategy_name="probe_%s_%s" % (root, noisy))
    assert inv["trades"] > 50
    assert inv["shift"] == 1.0, inv
    assert "error" not in inv


def test_rty_float_noise_would_have_failed_without_the_grid():
    """The bug itself: on raw 0.1-tick floats a +C shift moves tie trades."""
    _diff_tie.tick = 0.1
    arrays, _t = _tape(0.1, 2000.0)
    c = arrays["close"]
    k0 = R._trade_keys(_diff_tie(None, None, None, c))
    k1 = R._trade_keys(_diff_tie(None, None, None, c + 500.0))
    assert R._match(k0, k1) < 1.0


@pytest.mark.parametrize("root,tick,base", [("RTY", 0.1, 2000.0), ("ZN", 1.0 / 64, 120.0)])
def test_level_file_is_still_level_dependent(root, tick, base):
    arrays, t = _tape(tick, base)
    _level.lvl = float(np.median(arrays["close"]))
    inv = R.invariance(_mod(_level), arrays, root, t, 60, strategy_name="lvl_%s" % root)
    assert inv["trades"] > 0
    assert inv["shift"] < 1.0, inv


def test_probe_crash_is_logged_and_recorded(caplog):
    arrays, t = _tape(0.1, 2000.0)
    with caplog.at_level(logging.ERROR, logger="augur_engine.rolls"):
        inv = R.invariance(_mod(_boom), arrays, "RTY", t, 60, strategy_name="boom")
    assert inv["shift"] == 0.0 and inv["scale"] == 0.0          # still toward the guard
    assert "synthetic crash" in inv["error"]
    assert any("probe FAILED" in r.getMessage() for r in caplog.records)
