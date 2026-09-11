"""The compiled hot loops must agree with the interpreted ones EXACTLY.

This is the test that lets augur_engine/fastloop.py exist at all. Every crowned run, paper
leg and book card in this project was earned by the Python loops; a faster engine that
disagrees with them by even one trade would silently invalidate the whole run history, and it
would do so in a way nobody would notice until a live fill came in wrong.

So each case below runs the SAME strategy twice over the same bars - once with the compiled
path available, once with EDGELOG_NO_FASTLOOP forcing the interpreted loop - and requires the
trade lists to match: same count, same entry bar, same exit bar, same P&L to the last bit,
same entry price.

The data is synthetic and small on purpose: this runs in CI, where the real masters do not
exist. It is shaped to exercise the branches that actually decide trades - trends that trigger
the trendline break, pullbacks deep enough to fill the resting limit, gaps that jump a stop,
and long holds that a time cap can cut short.
"""
import os

import numpy as np
import pytest

from augur_engine.engine import run_backtest
from augur_engine import fastloop


def _bars(n=9000, seed=7):
    """A tape with trend, pullbacks and the occasional gap - enough to fire every branch."""
    rng = np.random.default_rng(seed)
    drift = np.linspace(0, 40, n)
    wobble = np.cumsum(rng.normal(0, 0.6, n))
    close = 1000 + drift + wobble
    close[n // 3::997] += 6.0                 # gaps that jump a resting stop
    high = close + np.abs(rng.normal(0, 0.8, n))
    low = close - np.abs(rng.normal(0, 0.8, n))
    open_ = close - rng.normal(0, 0.4, n)
    high = np.maximum.reduce([high, open_, close])
    low = np.minimum.reduce([low, open_, close])
    vol = np.abs(rng.normal(1000, 200, n))
    idx = np.datetime64("2020-01-01T00:00") + np.arange(n) * np.timedelta64(1, "m")
    return {"open": open_, "high": high, "low": low, "close": close, "volume": vol,
            "index": idx}


CASES = [
    ("ENGUQ_1M_ETH_R2_1_0.py", dict(buf_atr=0.3, tl_len=60, trail_frac=2.5, limit_atr=0.55,
                                    atr_len=20, act_R=1.5, breakeven_R=2.0, ema_len=100,
                                    er_len=50, stop_mult=1.0, regime_len=0, min_brk=1.0,
                                    vol_mult=0.0, er_th=0.0)),
    # the limit switched OFF exercises the other entry branch (fill at the signal close)
    ("ENGUQ_1M_ETH_R2_1_0.py", dict(buf_atr=0.3, tl_len=60, trail_frac=2.5, limit_atr=0.0,
                                    atr_len=20, act_R=1.5, breakeven_R=2.0, ema_len=100,
                                    er_len=50, stop_mult=1.0, regime_len=0, min_brk=1.0,
                                    vol_mult=0.0, er_th=0.0)),
    # the efficiency gate and the volume filter both ON
    ("ENGUQ_1M_ETH_R2_1_0.py", dict(buf_atr=0.3, tl_len=60, trail_frac=2.5, limit_atr=0.55,
                                    atr_len=20, act_R=1.5, breakeven_R=2.0, ema_len=100,
                                    er_len=50, stop_mult=1.0, regime_len=0, min_brk=1.0,
                                    vol_mult=0.8, er_th=0.05)),
    # the hold cap, which only the R3/R5 shape carries
    ("ENGUQ_1M_ETH_R3_1_0.py", dict(buf_atr=0.3, tl_len=60, trail_frac=2.5, limit_atr=0.55,
                                    atr_len=20, act_R=1.5, breakeven_R=2.0, ema_len=100,
                                    er_len=50, stop_mult=1.0, regime_len=0, min_brk=1.0,
                                    vol_mult=0.0, er_th=0.0, max_hold_bars=400)),
    ("ENGUQ_1M_ETH_R5_1_0.py", dict(buf_atr=0.3, tl_len=60, trail_frac=2.0, limit_atr=0.85,
                                    atr_len=20, act_R=1.5, breakeven_R=1.5, ema_len=100,
                                    er_len=50, stop_mult=1.0, regime_len=0, min_brk=1.0,
                                    vol_mult=0.0, er_th=0.0, max_hold_bars=300)),
]


def _run(fn, params, arrays):
    return run_backtest(fn, arrays=arrays, params=dict(params), cost_pts=0.0,
                        return_trades=True)


@pytest.mark.skipif(not fastloop.HAVE_NUMBA, reason="numba not installed")
@pytest.mark.parametrize("fn,params", CASES)
def test_compiled_matches_interpreted(fn, params):
    arrays = _bars()

    os.environ["EDGELOG_NO_FASTLOOP"] = "1"          # force the original Python loops
    try:
        slow = _run(fn, params, arrays)
    finally:
        os.environ.pop("EDGELOG_NO_FASTLOOP", None)
    fast = _run(fn, params, arrays)

    assert (slow is None) == (fast is None)
    if slow is None:
        return
    st, ft = slow.get("trades") or [], fast.get("trades") or []
    assert len(st) > 5, "the fixture produced almost no trades - it is not testing anything"
    assert len(ft) == len(st), "trade COUNT differs: %d compiled vs %d interpreted" % (
        len(ft), len(st))
    for q, (a, b) in enumerate(zip(st, ft)):
        assert int(a[0]) == int(b[0]), "trade %d entry bar %s vs %s" % (q, a[0], b[0])
        assert int(a[1]) == int(b[1]), "trade %d exit bar %s vs %s" % (q, a[1], b[1])
        assert abs(float(a[2]) - float(b[2])) < 1e-12, "trade %d P&L %r vs %r" % (q, a[2], b[2])
        assert abs(float(a[4]) - float(b[4])) < 1e-12, "trade %d entry price" % q
    assert abs(slow["total_pnl"] - fast["total_pnl"]) < 1e-9
    assert slow["num_trades"] == fast["num_trades"]


@pytest.mark.skipif(not fastloop.HAVE_NUMBA, reason="numba not installed")
def test_probes_force_the_interpreted_path():
    """Research instrumentation must still work - the compiled walk cannot carry it.

    The probes are a strategy-level argument, not an engine one, so this calls the strategy
    function directly (which is also how the research drivers use them).
    """
    import importlib.util as ilu
    import os as _os
    arrays = _bars()
    path = _os.path.join("augur_strategies", "ENGUQ_1M_ETH_R2_1_0.py")
    spec = ilu.spec_from_file_location("_engu_probe_mod", path)
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    probe = []
    r = mod.run_backtest(arrays["open"], arrays["high"], arrays["low"], arrays["close"],
                         volumes=arrays["volume"], return_trades=True,
                         _signal_probe=probe, **dict(CASES[0][1]))
    assert r is not None
    assert len(probe) > 0, "the signal probe collected nothing, so the fallback did not run"


def test_switch_is_respected():
    """EDGELOG_NO_FASTLOOP must turn the compiled path off even when numba is installed."""
    os.environ["EDGELOG_NO_FASTLOOP"] = "1"
    try:
        assert fastloop.enabled() is False
        assert fastloop.ema(np.arange(10, dtype=float), 3) is None
    finally:
        os.environ.pop("EDGELOG_NO_FASTLOOP", None)
