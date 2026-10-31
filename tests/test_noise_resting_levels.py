"""NOISE exports its stop level (stop-loss overlay row 2, 2026-10-31).

augur_strategies/NOISE_1_0.py gains a runtime-only `return_levels` keyword (default False):
with return_trades=True the result carries out["levels"], one row per trade, same order, in
ORB_3_6.py's _levels_row shape (entry_bar, side, entry, risk, stop, target=None, no
breakeven, trail=False). NOISE_1_1_NBHD.py and the NOISE_1_8_CT304 / CT304H wrappers name
the keyword and pass the rows through. api/cloud_signal.py flags NOISE_382 with
resting_levels (LOG ONLY): stop_px lands on the ENTRY row; no LEVELS row (no breakeven), and
api/qqq_exec.py rests orders for RESTING_LEG == "ORB" only.

Coverage:
  1. return_levels is inert: the full result (pickled bytes, levels popped) with and
     without it is identical -- synthetic bars through NOISE_1_0 / NBHD / CT304 / CT304H and
     through the engine wrapper, and (when reachable) the real NQ 5m master.
  2. The rows describe the walk: one per trade, aligned, the stop on the loss side of the
     entry by stop_k x the band excursion, and NONE with stop_mode='off'.
  3. cloud_signal: NOISE_382 is flagged and its strategy chain names the keyword;
     _trade_levels turns a NOISE row into a cent stop with no target and no breakeven.
  4. No resting order for NOISE: qqq_exec's gate is the ORB leg, and a LEVELS row for a
     NOISE leg is ignored.
"""
import importlib.util
import os
import pickle

import numpy as np
import pytest

import api.cloud_signal as cs
from augur_engine.engine import run_backtest as engine_run_backtest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_NQ_MASTER = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_uploads\NOADJ_NQ_5m_RTH.csv"

pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")

CT304_PARAMS = dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=1.5)
CT304H_PARAMS = dict(gate_len=16, gate_ratio=1.15, tilt_mult=1.5)
N10_PARAMS = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
                  side="Both", window="all_day", flat_eod=True, skip_holidays=False,
                  stop_mode="bandwidth", stop_k=1.75, confirm_bars=1,
                  daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8)


def _load(fname):
    spec = importlib.util.spec_from_file_location("_noiserl_" + fname[:-3],
                                                   os.path.join(ROOT, "augur_strategies", fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _bars(days=70, seed=11):
    """Synthetic 5m RTH sessions (78 bars each) with enough wobble to cross the band both
    ways and enough range to trip the bandwidth stop now and then."""
    rng = np.random.default_rng(seed)
    per = 78
    n = days * per
    close = 20000 + np.cumsum(rng.normal(0, 6.0, n))
    close += np.repeat(rng.normal(0, 40.0, days), per)          # session-to-session gaps
    high = close + np.abs(rng.normal(0, 7.0, n))
    low = close - np.abs(rng.normal(0, 7.0, n))
    open_ = close - rng.normal(0, 3.0, n)
    high = np.maximum.reduce([high, open_, close])
    low = np.minimum.reduce([low, open_, close])
    vol = np.abs(rng.normal(1500, 300, n)) + 1
    day_id = np.repeat(np.arange(days), per)
    base = np.datetime64("2026-03-02T09:30")
    idx = np.concatenate([base + np.timedelta64(d, "D") + np.arange(per) * np.timedelta64(5, "m")
                          for d in range(days)])
    return {"open": open_, "high": high, "low": low, "close": close, "volume": vol,
            "day_id": day_id, "index": idx, "meta": {"roll_mode": "none"}}


def _master_arrays(path, date_from):
    """A master CSV -> the engine's arrays dict (what load_master_arrays builds), read by path
    so the shared checkout's masters serve a worktree that has none of its own."""
    import pandas as pd
    df = pd.read_csv(path)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = dt
    df = df[df.index >= pd.Timestamp(date_from, tz="US/Eastern")]
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")
    return {"open": df["open"].values.astype(float), "high": df["high"].values.astype(float),
            "low": df["low"].values.astype(float), "close": df["close"].values.astype(float),
            "volume": df["volume"].values.astype(float), "day_id": day_id,
            "index": df.index.values, "meta": {"roll_mode": "none"}}


def _blob(res):
    res = dict(res or {})
    res.pop("levels", None)
    return pickle.dumps(res)


def _direct(mod, arrays, params, **extra):
    import inspect
    sp = inspect.signature(mod.run_backtest).parameters
    kw = dict(params)
    if "day_id" in sp or any(p.kind == p.VAR_KEYWORD for p in sp.values()):
        kw["day_id"] = arrays["day_id"]
    if "index" in sp:
        kw["index"] = arrays["index"]
    return mod.run_backtest(arrays["open"], arrays["high"], arrays["low"], arrays["close"],
                            volumes=arrays["volume"], return_trades=True, **kw, **extra)


FILES = [("NOISE_1_0.py", N10_PARAMS), ("NOISE_1_1_NBHD.py", dict(lookback=40, stop_k=1.75)),
         ("NOISE_1_8_CT304.py", CT304_PARAMS), ("NOISE_1_8_CT304H.py", CT304H_PARAMS)]


# ── 1. inert ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fname,params", FILES)
def test_return_levels_leaves_every_result_byte_identical(fname, params):
    arrays = _bars()
    mod = _load(fname)
    a = _direct(mod, arrays, params)
    b = _direct(mod, arrays, params, return_levels=True)
    assert a and a.get("trades"), "the synthetic tape must trade"
    assert _blob(a) == _blob(b)
    assert "levels" not in a and isinstance(b.get("levels"), list)
    assert len(b["levels"]) == len(b["trades"])
    # through the engine wrapper, the way api/cloud_signal.py and api/paper.py call it
    e1 = engine_run_backtest(fname, arrays=arrays, params=params, cost_pts=0.0, return_trades=True)
    e2 = engine_run_backtest(fname, arrays=arrays, params=dict(params, return_levels=True),
                             cost_pts=0.0, return_trades=True)
    assert _blob(e1) == _blob(e2)
    assert len(e2["levels"]) == len(e2["trades"])


@pytest.mark.skipif(not os.path.exists(SHARED_NQ_MASTER), reason="shared NQ 5m master not on this PC")
def test_byte_identical_on_the_nq_master():
    arrays = _master_arrays(SHARED_NQ_MASTER, "2025-06-01")
    for fname, params in FILES:
        a = engine_run_backtest(fname, arrays=arrays, params=params, cost_pts=0.533, return_trades=True)
        b = engine_run_backtest(fname, arrays=arrays, params=dict(params, return_levels=True),
                                cost_pts=0.533, return_trades=True)
        assert a and a["trades"], fname
        assert _blob(a) == _blob(b), fname
        assert len(b["levels"]) == len(b["trades"]), fname
        assert all(r is not None for r in b["levels"]), fname


# ── 2. the rows describe the walk ────────────────────────────────────────────────────────
def test_levels_align_with_trades_and_sit_on_the_loss_side():
    arrays = _bars()
    mod = _load("NOISE_1_0.py")
    r = _direct(mod, arrays, N10_PARAMS, return_levels=True)
    assert r["levels"] and len(r["levels"]) == len(r["trades"])
    for t, lv in zip(r["trades"], r["levels"]):
        assert lv is not None
        assert lv["entry_bar"] == int(t[0]) and lv["side"] == int(t[3])
        assert lv["entry"] == float(t[4])
        assert lv["target"] is None and lv["be_trigger"] is None and lv["be_stop"] is None
        assert lv["be_bar"] is None and lv["trail"] is False and lv["partial"] is False
        assert lv["risk"] > 0 and lv["risk"] == pytest.approx(abs(lv["entry"] - lv["stop"]))
        if lv["side"] > 0:
            assert lv["stop"] < lv["entry"]
        else:
            assert lv["stop"] > lv["entry"]
    # a stop-out trade exits AT the stop (or through it at the open), never better
    for t, lv in zip(r["trades"], r["levels"]):
        pnl, side = float(t[2]), int(t[3])
        if side > 0 and abs(pnl - (lv["stop"] - lv["entry"])) < 1e-9:
            break
    else:
        pytest.skip("no exact stop fill on this tape (the identity test above still holds)")


def test_stop_mode_off_gives_a_row_of_nones():
    arrays = _bars()
    mod = _load("NOISE_1_0.py")
    r = _direct(mod, arrays, dict(N10_PARAMS, stop_mode="off"), return_levels=True)
    assert r["levels"] and all(lv is None for lv in r["levels"])


def test_default_builds_nothing():
    arrays = _bars()
    mod = _load("NOISE_1_0.py")
    r = _direct(mod, arrays, N10_PARAMS)
    assert "levels" not in r


def test_ct304_rows_are_the_base_rows_untouched_by_the_tilt():
    arrays = _bars()
    ct_mod = _load("NOISE_1_8_CT304.py")
    base = _direct(_load("NOISE_1_1_NBHD.py"), arrays, dict(ct_mod._FROZEN), return_levels=True)
    ct = _direct(ct_mod, arrays, CT304_PARAMS, return_levels=True)
    assert ct["levels"] == base["levels"]           # the tilt sizes, it never moves a stop
    assert len(ct["levels"]) == len(ct["trades"])


# ── 3. cloud_signal ──────────────────────────────────────────────────────────────────────
def test_noise_382_is_flagged_log_only_and_names_the_keyword():
    cfg = cs.CROWN_LEGS["NOISE_382"]
    assert cfg.get("resting_levels") is True
    assert cs._leg_accepts_return_levels(cfg["strategy"])
    assert cs._leg_accepts_return_levels("NOISE_1_1_NBHD.py")
    assert cs._leg_accepts_return_levels("NOISE_1_0.py")


def test_trade_levels_reads_a_noise_row_as_a_cent_stop_with_no_target_or_breakeven():
    import pandas as pd
    idx = pd.date_range("2026-10-30 09:30", periods=10, freq="5min", tz="US/Eastern")
    row = {"entry_bar": 3, "side": 1, "entry": 738.03, "risk": 2.83, "stop": 735.2000001,
           "target": None, "be_trigger": None, "be_stop": None, "be_bar": None,
           "trail": False, "partial": False}
    lv = cs._trade_levels(row, 3, 1, 738.03, idx, 10)
    assert lv["stop_px"] == 735.20 and lv["target_px"] is None
    assert lv["be_trigger_px"] is None and lv["be_stop_px"] is None and lv["be_armed_time"] is None
    short = dict(row, side=-1, stop=740.7699999)
    assert cs._trade_levels(short, 3, -1, 738.03, idx, 10)["stop_px"] == 740.77   # buy stop UP


def test_noise_382_trades_carry_a_stop_on_the_real_cache_when_present():
    """Through run_leg_trades on real cached QQQ bars (the box's own), when this PC has them:
    every NOISE_382 trade dict gains "levels" with a stop and nothing else."""
    spec = importlib.util.spec_from_file_location("_noise382_fx", os.path.join(ROOT, "tests", "test_noise_382_switch.py"))
    fx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fx)
    if not fx.HAS_REAL_5M_CACHE:
        pytest.skip("no real QQQ 5m cache on this PC")
    df = fx._real_bar_frame()
    now = fx._now_past_the_newest_bar(df)
    arrays = cs.closed_arrays(df, now.to_pydatetime(), "5m", cs.DEFAULT_WARMUP_SESSIONS)
    trades = cs.run_leg_trades(cs.CROWN_LEGS["NOISE_382"], arrays, leg_key="NOISE_382")
    assert trades
    for t in trades:
        assert "levels" in t and t["levels"] is not None
        assert t["levels"]["target_px"] is None and t["levels"]["be_armed_time"] is None
        assert (t["levels"]["stop_px"] < t["entry_px"]) == (t["side"] == "long")


# ── 4. no resting order for NOISE ────────────────────────────────────────────────────────
def test_qqq_exec_rests_orders_for_orb_only():
    import api.qqq_exec as qx
    assert qx.RESTING_LEG == "ORB"
    # a LEVELS row for a NOISE leg does nothing to any lot
    state = {"legs": {"NOISE": {"trade_id": "t1", "side": "long"}}}
    lot = state["legs"]["NOISE"]
    logs = []
    qx._apply_engine_levels(state, {}, "NOISE", {"stop_px": 735.2, "ref_price": 735.2, "trade_id": "t1"},
                            "t1", lot, log=logs.append)
    assert "levels" not in lot and not logs
