"""ENGUQ_1M_ETH_SEL_1_0.py (round 57 research sibling) must be a faithful instrument.

ENGUQ_R57_PREREG.md section 7 item 1 requires, before any cell is read:
  * every new knob OFF reproduces its parents trade for trade (R2 shape, and the R5 hold-cap shape);
  * with each knob ON, the compiled walk and the interpreted walk agree trade for trade
    (the pattern of tests/test_fastloop_parity.py: count, entry bar, exit bar, P&L, entry price);
  * the rules are masks tested at the SIGNAL bar, built only from bars <= that bar;
  * a session-keyed knob with no timestamps raises instead of going silently inert.

Synthetic data, sized for CI (the real masters do not exist there): 110 sessions of 5-minute bars
with a quiet overnight tape, clock-shaped volume spikes at session transitions and a slow daily
swing, so every one of the four rules actually removes signals on this tape.
"""
import importlib.util
import inspect
import os
from collections import defaultdict

import numpy as np
import pandas as pd
import pytest

from augur_engine import fastloop
from augur_engine.engine import run_backtest

SEL = "ENGUQ_1M_ETH_SEL_1_0.py"
_HERE = os.path.dirname(os.path.abspath(__file__))
_SEL_PATH = os.path.join(os.path.dirname(_HERE), "augur_strategies", SEL)


def _load_sel(name="_enguq_sel_test_mod"):
    spec = importlib.util.spec_from_file_location(name, _SEL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bars(n_days=110, step_min=5, seed=11):
    rng = np.random.default_rng(seed)
    per = 1440 // step_min
    n = n_days * per
    idx = pd.date_range("2021-03-01 18:00", periods=n, freq="%dmin" % step_min, tz="US/Eastern")
    hour = idx.hour.to_numpy()
    quiet = (hour >= 18) | (hour < 3)
    sig = np.where(quiet, 0.35, 1.0) * rng.lognormal(0, 0.35, n // per + 1).repeat(per)[:n]
    dayk = np.arange(n) // per
    rets = rng.normal(0.02 * np.sin(dayk / 9.0), 0.9 * sig)
    close = 3000 + np.cumsum(rets)
    close[n // 3::1997] += 7.0                                   # gaps that jump a resting stop
    high = close + np.abs(rng.normal(0, 0.8, n)) * sig
    low = close - np.abs(rng.normal(0, 0.8, n)) * sig
    open_ = close - rng.normal(0, 0.4, n) * sig
    high = np.maximum.reduce([high, open_, close])
    low = np.minimum.reduce([low, open_, close])
    cmin = hour * 60 + idx.minute.to_numpy()
    base = np.where(quiet, 300.0, 1500.0) * (1 + 2.0 * np.isin(cmin, [18 * 60, 3 * 60, 8 * 60 + 30, 9 * 60 + 30]))
    vol = np.round(base * rng.lognormal(0, 0.5, n))
    return {"open": open_, "high": high, "low": low, "close": close, "volume": vol, "index": idx}


R2_SHAPE = dict(buf_atr=0.3, tl_len=60, trail_frac=2.5, limit_atr=0.55, atr_len=20, act_R=1.5,
                breakeven_R=2.0, ema_len=100, er_len=50, stop_mult=1.0, regime_len=0, min_brk=1.0,
                vol_mult=0.8, er_th=0.0)
R5_SHAPE = dict(R2_SHAPE, limit_atr=0.85, max_hold_bars=300)
OFF = dict(quiet_pct=0.0, stretch_max=0.0, rec_min=0.0, vol_clock=0.0)
KNOBS_ON = [("quiet_pct", 30.0), ("stretch_max", 1.0), ("rec_min", 0.8), ("vol_clock", 1.25)]


def _run(fn, params, arrays, slow=False):
    if slow:
        os.environ["EDGELOG_NO_FASTLOOP"] = "1"
    try:
        return run_backtest(fn, arrays=arrays, params=dict(params), cost_pts=0.0, return_trades=True)
    finally:
        if slow:
            os.environ.pop("EDGELOG_NO_FASTLOOP", None)


def _same_trades(a, b):
    assert (a is None) == (b is None)
    if a is None:
        return
    ta, tb = a.get("trades") or [], b.get("trades") or []
    assert len(ta) == len(tb), "trade COUNT differs: %d vs %d" % (len(ta), len(tb))
    for q, (x, y) in enumerate(zip(ta, tb)):
        assert int(x[0]) == int(y[0]), "trade %d entry bar %s vs %s" % (q, x[0], y[0])
        assert int(x[1]) == int(y[1]), "trade %d exit bar %s vs %s" % (q, x[1], y[1])
        assert abs(float(x[2]) - float(y[2])) < 1e-12, "trade %d P&L %r vs %r" % (q, x[2], y[2])
        assert abs(float(x[4]) - float(y[4])) < 1e-12, "trade %d entry price" % q


def _clear_engine_memo():
    from augur_engine.strategies import load_strategy
    load_strategy(SEL)._MEMO.clear()


# ── contract ────────────────────────────────────────────────────────────────────────────────

def test_contract_index_declared_and_knobs_default_off():
    mod = _load_sel()
    sp = inspect.signature(mod.run_backtest).parameters
    assert "index" in sp and sp["index"].default is None, "index=None must be declared explicitly"
    dp = mod.DEFAULT_PARAMS
    for k in OFF:
        assert dp[k]["default"] == 0.0, "%s must default OFF" % k
    assert dp["max_hold_bars"]["default"] == 0
    assert mod._AUGUR_PARENT == "ENGUQ_1M_ETH_R2_1_0.py"
    spec =importlib.util.spec_from_file_location(
        "_r2_ref", os.path.join(os.path.dirname(_HERE), "augur_strategies", "ENGUQ_1M_ETH_R2_1_0.py"))
    r2m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r2m)
    for k, meta in r2m.DEFAULT_PARAMS.items():
        assert dp[k]["default"] == meta["default"], "%s default %r != R2 %r" % (k, dp[k]["default"], meta["default"])


# ── knob-off parity with both parents ───────────────────────────────────────────────────────

@pytest.mark.parametrize("slow", [False, True])
def test_knobs_off_reproduce_r2(slow):
    arrays = _bars()
    ref = _run("ENGUQ_1M_ETH_R2_1_0.py", R2_SHAPE, arrays, slow=slow)
    got = _run(SEL, dict(R2_SHAPE, max_hold_bars=0, **OFF), arrays, slow=slow)
    assert ref is not None and len(ref["trades"]) > 5
    _same_trades(ref, got)


@pytest.mark.parametrize("slow", [False, True])
def test_knobs_off_reproduce_r5(slow):
    arrays = _bars()
    ref = _run("ENGUQ_1M_ETH_R5_1_0.py", R5_SHAPE, arrays, slow=slow)
    got = _run(SEL, dict(R5_SHAPE, **OFF), arrays, slow=slow)
    assert ref is not None and len(ref["trades"]) > 5
    _same_trades(ref, got)


# ── compiled == interpreted with each knob ON ───────────────────────────────────────────────

@pytest.mark.skipif(not fastloop.HAVE_NUMBA, reason="numba not installed")
@pytest.mark.parametrize("knob,value", KNOBS_ON)
@pytest.mark.parametrize("shape", ["R2", "R5"])
def test_each_knob_compiled_matches_interpreted(knob, value, shape):
    arrays = _bars()
    base = R2_SHAPE if shape == "R2" else R5_SHAPE
    params = dict(base, **OFF)
    params[knob] = value
    _clear_engine_memo()
    fast = _run(SEL, params, arrays)
    _clear_engine_memo()                                  # the interpreted run rebuilds every feature
    slow = _run(SEL, params, arrays, slow=True)
    assert fast is not None and len(fast["trades"]) > 5, "fixture produced almost no trades"
    _same_trades(slow, fast)
    off = _run(SEL, dict(base, **OFF), arrays)
    assert off["trades"] != fast["trades"], "%s=%s removed nothing on this tape - the test is vacuous" % (knob, value)


# ── timestamps: a session-keyed knob without an index must raise ────────────────────────────

@pytest.mark.parametrize("knob,value", [kv for kv in KNOBS_ON if kv[0] != "rec_min"])
def test_session_knob_without_index_raises(knob, value):
    mod = _load_sel()
    a = _bars()
    with pytest.raises(ValueError):
        mod.run_backtest(a["open"], a["high"], a["low"], a["close"], volumes=a["volume"],
                         return_trades=True, **dict(R2_SHAPE, **{knob: value}))


def test_engine_hands_index_to_the_file():
    """Through the engine the index arrives (declared), so a session knob runs without raising."""
    arrays = _bars()
    r = _run(SEL, dict(R2_SHAPE, quiet_pct=30.0), arrays)
    assert r is not None


def test_rec_min_needs_no_index():
    mod = _load_sel()
    a = _bars()
    with_ix = mod.run_backtest(a["open"], a["high"], a["low"], a["close"], volumes=a["volume"],
                               index=a["index"], return_trades=True, **dict(R2_SHAPE, rec_min=0.8))
    no_ix = mod.run_backtest(a["open"], a["high"], a["low"], a["close"], volumes=a["volume"],
                             return_trades=True, **dict(R2_SHAPE, rec_min=0.8))
    _same_trades(with_ix, no_ix)


# ── research instrumentation ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("knob,value", KNOBS_ON)
def test_mask_override_with_the_computed_mask_is_identity(knob, value):
    mod = _load_sel()
    a = _bars()
    h, l, c = a["high"], a["low"], a["close"]
    tr = mod._true_range(h, l, c)
    kn = dict(OFF, **{knob: value})
    m = mod._rule_mask(h, l, c, a["volume"], pd.DatetimeIndex(a["index"]), tr, R2_SHAPE["tl_len"],
                       kn["quiet_pct"], kn["stretch_max"], kn["rec_min"], kn["vol_clock"])
    args = (a["open"], h, l, c)
    kw = dict(volumes=a["volume"], index=a["index"], return_trades=True, **dict(R2_SHAPE, **kn))
    ref = mod.run_backtest(*args, **kw)
    got = mod.run_backtest(*args, _mask_override=m, **kw)
    _same_trades(ref, got)
    if knob != "vol_clock":                     # H-D also switches the 20-bar test off
        allpass = mod.run_backtest(*args, _mask_override=np.ones(len(c), bool), **kw)
        off = mod.run_backtest(*args, **dict(kw, **OFF))
        _same_trades(off, allpass)


def test_mask_override_needs_a_knob():
    mod = _load_sel()
    a = _bars()
    with pytest.raises(ValueError):
        mod.run_backtest(a["open"], a["high"], a["low"], a["close"], volumes=a["volume"],
                         index=a["index"], _mask_override=np.ones(len(a["close"]), bool), **R2_SHAPE)


@pytest.mark.parametrize("knob,value", KNOBS_ON)
def test_signal_index_probe_sees_the_mask_at_the_signal_bar(knob, value):
    mod = _load_sel()
    a = _bars()
    h, l, c = a["high"], a["low"], a["close"]
    kn = dict(OFF, **{knob: value})
    m = mod._rule_mask(h, l, c, a["volume"], pd.DatetimeIndex(a["index"]), mod._true_range(h, l, c),
                       R2_SHAPE["tl_len"], kn["quiet_pct"], kn["stretch_max"], kn["rec_min"], kn["vol_clock"])
    on, off = [], []
    base = dict(volumes=a["volume"], index=a["index"], return_trades=True)
    mod.run_backtest(a["open"], h, l, c, _signal_index_probe=on, **base, **dict(R2_SHAPE, **kn))
    p_off = dict(R2_SHAPE, **OFF)
    if knob == "vol_clock":
        p_off["vol_mult"] = 0.0                  # compare against the same volume regime
    mod.run_backtest(a["open"], h, l, c, _signal_index_probe=off, **base, **p_off)
    assert len(on) > 5
    assert all(m[i] for i in on), "a probed signal bar failed its own mask"
    assert any(not m[i] for i in off), "the mask never rejected a knob-off signal bar - vacuous"


# ── feature definitions, brute force, straight from ENGUQ_R57_PREREG.md section 5 ────────────

def _sess_minute(idx):
    keys = [(t + pd.Timedelta(hours=6)).tz_localize(None).date() for t in idx]
    code, sess = {}, np.empty(len(idx), np.int64)
    for k, key in enumerate(keys):
        sess[k] = code.setdefault(key, len(code))
    minute = np.array([t.hour * 60 + t.minute for t in idx])
    return sess, minute


def test_features_match_brute_force_definitions():
    mod = _load_sel()
    a = _bars(n_days=90)
    o, h, l, c, v, idx = a["open"], a["high"], a["low"], a["close"], a["volume"], a["index"]
    n = len(c)
    tl = 60
    F = mod._rule_features(o, h, l, c, v, idx, tl_len=tl)
    sess, minute = _sess_minute(idx)
    ns = int(sess.max()) + 1
    members = defaultdict(list)
    for k in range(n):
        members[sess[k]].append(k)

    tr = np.empty(n); tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))

    # H-A
    atr14 = np.full(n, np.nan)
    for k in range(13, n):
        atr14[k] = tr[k - 13:k + 1].mean()
    q = np.full(n, np.nan)
    for s in range(ns):
        if s < 60:
            continue
        ref = []
        for t in range(max(0, s - 252), s):
            bars_t = members[t]
            ref += [atr14[x] for x in bars_t[::23]]
        ref = np.array([r for r in ref if not np.isnan(r)])
        if len(ref) < 100:
            continue
        for k in members[s]:
            if not np.isnan(atr14[k]):
                q[k] = 100.0 * (ref <= atr14[k]).sum() / len(ref)
    assert np.array_equal(np.isnan(q), np.isnan(F["q"]))
    assert np.nanmax(np.abs(q - F["q"])) < 1e-9 and np.isfinite(F["q"]).sum() > 1000

    # H-B
    Ht = np.array([h[members[t]].max() for t in range(ns)])
    Lt = np.array([l[members[t]].min() for t in range(ns)])
    Ct = np.array([c[members[t][-1]] for t in range(ns)])
    TRd = np.array([Ht[0] - Lt[0]] + [max(Ht[t] - Lt[t], abs(Ht[t] - Ct[t - 1]), abs(Lt[t] - Ct[t - 1]))
                                       for t in range(1, ns)])
    ATRd = np.array([TRd[t - 13:t + 1].mean() if t >= 13 else np.nan for t in range(ns)])
    SMA = np.array([Ct[t - 19:t + 1].mean() if t >= 19 else np.nan for t in range(ns)])
    S = np.full(n, np.nan)
    for k in range(n):
        s = sess[k]
        if s >= 1 and np.isfinite(ATRd[s - 1]) and np.isfinite(SMA[s - 1]) and ATRd[s - 1] > 0:
            S[k] = (c[k] - SMA[s - 1]) / ATRd[s - 1]
    assert np.array_equal(np.isnan(S), np.isnan(F["stretch"]))
    assert np.nanmax(np.abs(S - F["stretch"])) < 1e-9

    # H-C
    rec = np.full(n, np.nan)
    for i in range(tl, n):
        WH = h[i - tl:i].max(); SL = l[i - tl:i + 1].min()
        if WH > SL:
            rec[i] = (c[i] - SL) / (WH - SL)
    assert np.array_equal(np.isnan(rec), np.isnan(F["rec"]))
    assert np.nanmax(np.abs(rec - F["rec"])) < 1e-12

    # H-D
    at = {(sess[k], minute[k]): v[k] for k in range(n)}
    B = np.full(n, np.nan)
    for k in range(n):
        s, m = sess[k], minute[k]
        if s < 21:
            continue
        pr = [at[(t, m)] for t in range(s - 20, s) if (t, m) in at]
        if len(pr) >= 10:
            B[k] = float(np.sum(pr)) / len(pr)
    assert np.array_equal(np.isnan(B), np.isnan(F["clock_base"]))
    assert np.nanmax(np.abs(B - F["clock_base"])) < 1e-9
    assert np.nanmax(np.abs(v / B - F["vol_vs_clock"])) < 1e-9


def test_features_are_causal_under_truncation():
    """Every feature at bar k is unchanged when the frame ends at k: nothing after k is read."""
    mod = _load_sel()
    a = _bars(n_days=100)
    n = len(a["close"])
    full = mod._rule_features(a["open"], a["high"], a["low"], a["close"], a["volume"], a["index"], tl_len=60)
    for cut in (int(n * 0.71) + 7, int(n * 0.9) + 131):
        sl = slice(0, cut)
        part = mod._rule_features(a["open"][sl], a["high"][sl], a["low"][sl], a["close"][sl],
                                  a["volume"][sl], a["index"][sl], tl_len=60)
        for k in ("q", "stretch", "rec", "clock_base", "vol_vs_clock"):
            x, y = full[k][:cut], part[k]
            assert np.array_equal(np.isnan(x), np.isnan(y)), "%s NaN pattern changed at cut %d" % (k, cut)
            fin = np.isfinite(x)
            assert np.array_equal(x[fin], y[fin]), "%s changed when the future was removed (cut %d)" % (k, cut)


def test_memo_never_crosses_tapes_of_the_same_shape():
    mod = _load_sel()
    a, b = _bars(seed=11), _bars(seed=12)                     # same bar count and timestamps
    fa = mod._rule_features(a["open"], a["high"], a["low"], a["close"], a["volume"], a["index"], tl_len=60)
    fb = mod._rule_features(b["open"], b["high"], b["low"], b["close"], b["volume"], b["index"], tl_len=60)
    for k in ("q", "stretch", "rec", "clock_base"):
        assert not np.array_equal(np.nan_to_num(fa[k]), np.nan_to_num(fb[k])), "%s leaked across tapes" % k
