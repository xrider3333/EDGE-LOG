"""Resting ORB stops, part B1 -- the engine's own levels (design section 2, 2026-09-29).

augur_strategies/ORB_3_6.py gains a runtime-only `return_levels` keyword (default False)
reporting, per trade, the initial stop, the target, the breakeven trigger and the bar at
whose close breakeven armed. api/cloud_signal.py passes it for a cfg["resting_levels"] leg
(ORB_R6 only), writes stop_px/target_px on the ENTRY row and one LEVELS row when breakeven
moves the stop.

Coverage:
  1. return_levels is inert: the full result (pickled bytes) with and without it is
     identical on synthetic bars, on the real QQQ fixture and (when reachable) on the NQ
     master, for ORB #314 and for param sets that exercise the partial, the trail, a
     zero target and both directions -- through the plugin and through the engine wrapper.
  2. The levels describe the walk: one row per trade, aligned with out["trades"], and the
     breakeven bar is the first bar after entry whose close crossed the trigger.
  3. Cent rounding in the backtest's own trigger direction, anchored on 09-28's short
     (entry 732.33, range 3.375 -> buy stop 740.77, breakeven trigger 728.11, target
     690.14), reproduced live-style from the Webull 5m fixture at 10:50.
  4. PARITY: the emitted cent levels alone (stop, target, breakeven stop from the bar
     after be_armed_time) reproduce every backtest exit -- bar and price -- over the
     62-session QQQ fixture and over a synthetic multi-day set that hits every exit kind.
  5. cloud_signal: only a flagged leg gets levels; ENTRY carries stop_px/target_px; ONE
     LEVELS row per trade, idempotent across ticks and reruns, never for a skipped trade
     or a trade that closed in the same diff; signals.csv gains the two columns at the end.

Fixture: tests/fixtures/orb_resting_levels/QQQ_5m_20260701_20260928.csv.gz -- the box's own
QQQ 5m bar cache (the bars the live ORB_R6 leg decided on), sessions 2026-07-01..09-28.
"""
import csv
import datetime as dt
import importlib.util
import math
import os
import pickle

import numpy as np
import pandas as pd
import pytest

import api.cloud_signal as cs
from augur_engine.engine import run_backtest as engine_run_backtest
from api import market_calendar
from api.paper import ORB_314

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "orb_resting_levels",
                       "QQQ_5m_20260701_20260928.csv.gz")
SHARED_NQ_MASTER = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_uploads\NOADJ_NQ_5m_RTH.csv"
TZ = cs._zi(cs.TZ)

pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")


def _load(fname):
    spec = importlib.util.spec_from_file_location("_orbrl_" + fname[:-3],
                                                   os.path.join(ROOT, "augur_strategies", fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ORB = _load("ORB_3_6.py")
ORB_R6 = _load("ORB_3_6_R6.py")

# ORB #314 plus param sets that reach every branch the hook touches
PARAM_SETS = {
    "orb314": dict(ORB_314),
    "c230_partial_trail": dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0,
                               breakout_buf=0.25, close_confirm=True, partial_exit_R=3.0,
                               trail_bars=3, target_R=5.5, atr_filter=0.7, vpace_filter=0.7,
                               be_after_R=1.0, flat_eod=True, skip_holidays=True),
    "both_no_target_no_be": dict(ORB_314, trade_mode="Both", target_R=0.0, be_after_R=0.0,
                                 atr_filter=0.0, vpace_filter=0.0),
    "touch_entry_tight": dict(ORB_314, close_confirm=False, stop_frac=0.75, target_R=2.0,
                              be_after_R=0.5, atr_filter=0.0, vpace_filter=0.0),
}


# ── bar sources ─────────────────────────────────────────────────────────────────────────
def _fixture_df():
    df = pd.read_csv(FIXTURE)
    df["time"] = df["time"].astype(int)
    return df.sort_values("time").drop_duplicates("time").reset_index(drop=True)


def _fixture_arrays(now=None, sessions=None):
    df = _fixture_df()
    now = now or dt.datetime(2026, 9, 28, 16, 10, tzinfo=TZ)
    return cs.closed_arrays(df, now, "5m", sessions or 1000)


def _synthetic_epoch_df(n_sessions=90, seed=7):
    """Deterministic cent-grid QQQ-like sessions on real session days (78 x 5m bars): a
    tight opening range, then a random walk with a per-session drift, so every exit kind
    shows up -- initial stop, breakeven stop, target, gap-through and end of day."""
    rng = np.random.default_rng(seed)
    rows = []
    d = dt.date(2026, 3, 2)
    px = 500.0
    made = 0
    while made < n_sessions:
        if market_calendar.is_session(d) and market_calendar.session_close_et(d) != "13:00":
            start = dt.datetime.combine(d, dt.time(9, 30), tzinfo=TZ)
            drift = rng.choice([-0.12, -0.05, 0.0, 0.05, 0.12])
            for b in range(78):
                o = px
                if b < 2:
                    step_ = rng.normal(0.0, 0.03)
                    spread = 0.10
                else:
                    step_ = drift + rng.normal(0.0, 0.18)
                    if rng.random() < 0.02:
                        step_ += rng.choice([-1.5, 1.5])      # an occasional gap bar
                    spread = abs(rng.normal(0.0, 0.10)) + 0.02
                c = round(o + step_, 2)
                h = round(max(o, c) + spread, 2)
                l = round(min(o, c) - spread, 2)
                rows.append((int((start + dt.timedelta(minutes=5 * b)).timestamp()),
                             round(o, 2), h, l, c, float(rng.integers(1_000, 50_000))))
                px = c
            made += 1
        d += dt.timedelta(days=1)
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def _synthetic_arrays():
    df = _synthetic_epoch_df()
    last = pd.to_datetime(df["time"].iloc[-1], unit="s", utc=True).tz_convert(TZ)
    return cs.closed_arrays(df, last.to_pydatetime() + dt.timedelta(minutes=15), "5m", 1000)


def _run(mod, arrays, params, **kw):
    return mod.run_backtest(arrays["open"], arrays["high"], arrays["low"], arrays["close"],
                            volumes=arrays["volume"], day_id=arrays["day_id"], **params, **kw)


def _strip_levels(res):
    res = dict(res)
    res.pop("levels")
    return res


# ── 1. byte-identical with and without return_levels ─────────────────────────────────────
@pytest.mark.parametrize("which", ["synthetic", "fixture"])
@pytest.mark.parametrize("pset", sorted(PARAM_SETS))
def test_return_levels_leaves_every_result_byte_identical(which, pset):
    arrays = _synthetic_arrays() if which == "synthetic" else _fixture_arrays()
    params = PARAM_SETS[pset]
    for want_trades in (True, False):
        base = _run(ORB, arrays, params, return_trades=want_trades)
        with_lv = _run(ORB, arrays, params, return_trades=want_trades, return_levels=True)
        explicit_off = _run(ORB, arrays, params, return_trades=want_trades, return_levels=False)
        assert base is not None and base["num_trades"] > 0
        assert pickle.dumps(explicit_off) == pickle.dumps(base)
        assert "levels" not in base and len(with_lv["levels"]) == base["num_trades"]
        assert pickle.dumps(_strip_levels(with_lv)) == pickle.dumps(base), \
            f"{which}/{pset}: return_levels changed the result"


def test_engine_wrapper_and_r6_wrapper_are_unchanged_too():
    """The live path: augur_engine.engine.run_backtest on ORB_3_6_R6.py (which re-exports
    ORB_3_6's run_backtest) with ORB #314 -- only a trailing "levels" key differs."""
    arrays = _fixture_arrays()
    assert ORB_R6.run_backtest.__code__.co_code == ORB.run_backtest.__code__.co_code
    base = engine_run_backtest("ORB_3_6_R6.py", arrays=arrays, params=dict(ORB_314),
                               cost_pts=0.0, return_trades=True)
    with_lv = engine_run_backtest("ORB_3_6_R6.py", arrays=arrays,
                                  params=dict(ORB_314, return_levels=True),
                                  cost_pts=0.0, return_trades=True)
    assert base["num_trades"] > 20
    assert pickle.dumps(_strip_levels(with_lv)) == pickle.dumps(base)


@pytest.mark.skipif(not os.path.exists(SHARED_NQ_MASTER), reason="NQ 5m master not reachable")
def test_byte_identical_on_the_nq_master():
    df = pd.read_csv(SHARED_NQ_MASTER)
    df = df.sort_values("time").reset_index(drop=True)
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    day_id = pd.factorize(et.dt.date)[0]
    args = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    for params in (dict(ORB_314), PARAM_SETS["c230_partial_trail"]):
        kw = dict(volumes=df["volume"].values, day_id=day_id, return_trades=True, **params)
        base = ORB.run_backtest(*args, **kw)
        with_lv = ORB.run_backtest(*args, **kw, return_levels=True)
        assert base["num_trades"] > 1000
        assert pickle.dumps(_strip_levels(with_lv)) == pickle.dumps(base)


# ── 2. the levels describe the walk ─────────────────────────────────────────────────────
@pytest.mark.parametrize("which", ["synthetic", "fixture"])
def test_levels_align_with_trades_and_breakeven_bar_is_the_first_crossing_close(which):
    arrays = _synthetic_arrays() if which == "synthetic" else _fixture_arrays()
    p = PARAM_SETS["orb314"]
    res = _run(ORB, arrays, p, return_trades=True, return_levels=True)
    c = arrays["close"]
    armed = 0
    for (eb, xb, _pnl, side, entry), lv in zip(res["trades"], res["levels"]):
        assert lv["entry_bar"] == eb and lv["side"] == side and lv["entry"] == entry
        assert not lv["trail"] and not lv["partial"]
        risk = lv["risk"]
        assert lv["stop"] == (entry - risk if side > 0 else entry + risk)
        assert lv["target"] == pytest.approx(entry + side * p["target_R"] * risk, abs=1e-9)
        assert lv["be_trigger"] == pytest.approx(entry + side * p["be_after_R"] * risk, abs=1e-9)
        assert lv["be_stop"] == entry
        crossed = [k for k in range(eb + 1, xb + 1)
                   if (c[k] >= lv["be_trigger"] if side > 0 else c[k] <= lv["be_trigger"])]
        if lv["be_bar"] is None:
            # never armed: no close up to the exit crossed -- except the exit bar itself
            # when a stop fill ended the trade before its close was read
            assert not crossed or crossed == [xb]
        else:
            armed += 1
            assert lv["be_bar"] == crossed[0] and eb < lv["be_bar"] <= xb
    assert armed > 0


def test_partial_or_trail_rows_are_flagged():
    arrays = _synthetic_arrays()
    res = _run(ORB, arrays, PARAM_SETS["c230_partial_trail"], return_trades=True,
               return_levels=True)
    assert res["levels"] and all(lv["trail"] and lv["partial"] for lv in res["levels"])


# ── 3. cent rounding + the 09-28 anchor ─────────────────────────────────────────────────
def test_cent_level_rounds_in_the_trigger_direction_and_ignores_float32_noise():
    assert cs._cent_level(740.7675, up=True) == 740.77      # buy stop UP
    assert cs._cent_level(740.7675, up=False) == 740.76     # sell stop DOWN
    assert cs._cent_level(690.1425, up=False) == 690.14     # buy target DOWN
    assert cs._cent_level(690.1425, up=True) == 690.15      # sell target UP
    # float32 cache noise around a whole cent never moves the level a cent away
    for noisy in (732.330017, 732.3299999, 732.33):
        assert cs._cent_level(noisy, up=True) == 732.33
        assert cs._cent_level(noisy, up=False) == 732.33
    assert cs._cent_level(None, up=True) is None
    assert cs._cent_level(float("inf"), up=True) is None


def test_trade_levels_direction_table():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-09-28 10:45", tz=cs.TZ)] * 3)
    base = dict(entry_bar=0, entry=100.004, risk=1.2345, be_bar=2, trail=False, partial=False)
    long_ = cs._trade_levels(dict(base, side=1, stop=98.7695, target=106.1765, be_trigger=100.6213,
                                  be_stop=100.004), 0, 1, 100.004, idx, 3)
    assert (long_["stop_px"], long_["target_px"], long_["be_stop_px"]) == (98.76, 106.18, 100.0)
    short = cs._trade_levels(dict(base, side=-1, stop=101.2385, target=93.8315, be_trigger=99.3867,
                                  be_stop=100.004), 0, -1, 100.004, idx, 3)
    assert (short["stop_px"], short["target_px"], short["be_stop_px"]) == (101.24, 93.83, 100.01)
    assert long_["be_armed_time"] == idx[2].isoformat()
    # a row for another trade, or one a trail/partial moves, is never used
    assert cs._trade_levels(dict(base, side=1, stop=98.0, target=None, be_trigger=None,
                                 be_stop=None), 1, 1, 100.004, idx, 3) is None
    assert cs._trade_levels(dict(base, side=1, stop=98.0, target=None, be_trigger=None,
                                 be_stop=None, trail=True), 0, 1, 100.004, idx, 3) is None


def test_0928_short_anchor_live_style_at_1050():
    """The live ENTRY of 09-28 (ORB_R6-20260928T144500Z-S, 732.33) from the box's own bars,
    decided at the 10:50 tick exactly as step() does it."""
    df = _fixture_df()
    now = dt.datetime(2026, 9, 28, 10, 50, 5, tzinfo=TZ)
    cfg = cs.CROWN_LEGS["ORB_R6"]
    arrays = cs.closed_arrays(df, now, "5m", cs.leg_warmup_sessions(cfg))
    trades = cs.run_leg_trades(cfg, arrays, "ORB_R6", now=now)
    t = [t for t in trades if t["entry_time"].startswith("2026-09-28")]
    assert len(t) == 1
    t = t[0]
    assert (t["side"], t["entry_time"], t["entry_px"]) == ("short", "2026-09-28T10:45:00-04:00", 732.33)
    assert t["still_open"]
    lv = t["levels"]
    assert (lv["stop_px"], lv["be_trigger_px"], lv["target_px"]) == (740.77, 728.11, 690.14)
    assert lv["be_stop_px"] == 732.33 and lv["be_armed_time"] is None
    # the opening range the task quotes
    s = arrays["index"].normalize() == pd.Timestamp("2026-09-28", tz=cs.TZ)
    rng_ = arrays["high"][s][:2].max() - arrays["low"][s][:2].min()
    assert rng_ == pytest.approx(3.375, abs=1e-9)


# ── 4. PARITY: the emitted levels reproduce the backtest's exits ─────────────────────────
def _simulate_from_levels(t, arrays):
    """Walk the bars after entry using ONLY what the ledger carries: stop_px (then
    be_stop_px from the bar after be_armed_time), target_px, and the session's last bar.
    Stop before target inside a bar; a stop gapped through fills at the open."""
    idx, o, h, l, c = (arrays["index"], arrays["open"], arrays["high"], arrays["low"],
                       arrays["close"])
    did = arrays["day_id"]
    lv = t["levels"]
    eb = t["entry_bar"]
    long_ = t["side"] == "long"
    last = eb
    while last + 1 < len(did) and did[last + 1] == did[eb]:
        last += 1
    be_bar = None
    if lv["be_armed_time"]:
        be_bar = int(np.nonzero(np.array([x.isoformat() for x in idx]) == lv["be_armed_time"])[0][0])
    stop, tgt = lv["stop_px"], lv["target_px"]
    for k in range(eb + 1, last + 1):
        if be_bar is not None and k > be_bar:
            stop = max(stop, lv["be_stop_px"]) if long_ else min(stop, lv["be_stop_px"])
        be_live = be_bar is not None and k > be_bar
        if long_:
            if l[k] <= stop:
                return k, (o[k] if o[k] < stop else stop), ("be" if be_live else "stop")
            if tgt is not None and h[k] >= tgt:
                return k, tgt, "target"
        else:
            if h[k] >= stop:
                return k, (o[k] if o[k] > stop else stop), ("be" if be_live else "stop")
            if tgt is not None and l[k] <= tgt:
                return k, tgt, "target"
    return last, c[last], "eod"


def _raw_levels(cfg, arrays):
    """The engine's unrounded levels for the same call, keyed by entry bar, in the shape
    _simulate_from_levels reads (be_armed_time from the engine's be_bar)."""
    res = engine_run_backtest(cfg["strategy"], arrays=arrays,
                              params=dict(cfg["params"], return_levels=True),
                              cost_pts=0.0, return_trades=True)
    out = {}
    for lv in res["levels"]:
        out[lv["entry_bar"]] = {
            "stop_px": lv["stop"], "target_px": lv["target"], "be_stop_px": lv["be_stop"],
            "be_armed_time": (arrays["index"][lv["be_bar"]].isoformat()
                              if lv["be_bar"] is not None else None),
            "_raw": lv}
    return out


def _on_a_cent(x):
    return x is not None and abs(x * 100.0 - round(x * 100.0)) < 1e-6


def _parity(cfg, arrays):
    """For every trade: (a) the simulator fed the engine's RAW levels reproduces the
    backtest's exit bar and price exactly (the simulator is the backtest's exit rule);
    (b) fed only the ledger's CENT levels it reproduces the exit bar, and the price to
    within the rounding. The one allowed difference in (b) is a float TIE: a raw level
    that is a whole cent up to float noise (entry + 12.5 x an even-cent range, say)
    while a bar's extreme sits exactly on that cent -- the backtest's float compare then
    decides by 1e-13, Webull by the cent. Returns (exit kinds, tie trades)."""
    trades = cs.run_leg_trades(cfg, arrays, "ORB_R6")
    assert trades and all(t["levels"] for t in trades)
    raw = _raw_levels(cfg, arrays)
    idx = arrays["index"]
    kinds, ties = {}, []
    for t in trades:
        if t["still_open"]:
            k, _px, kind = _simulate_from_levels(t, arrays)
            assert k == len(idx) - 1 and kind == "eod"
            continue
        rk, rpx, rkind = _simulate_from_levels(dict(t, levels=raw[t["entry_bar"]]), arrays)
        assert idx[rk].isoformat() == t["exit_time"], (t, rkind)
        assert rpx == pytest.approx(t["exit_px"], abs=1e-4), (t, rkind, rpx)
        k, px, kind = _simulate_from_levels(t, arrays)
        if idx[k].isoformat() != t["exit_time"] or kind != rkind:
            lv = raw[t["entry_bar"]]["_raw"]
            assert any(_on_a_cent(x) for x in (lv["stop"], lv["target"])),                 ("cent levels changed an exit without a float tie", t, kind, rkind)
            ties.append(t)
            continue
        kinds[kind] = kinds.get(kind, 0) + 1
        # a stop/target fills at the cent level; the backtest at its unrounded level
        tol = 0.01 if kind in ("stop", "be", "target") else 1e-4
        assert abs(px - t["exit_px"]) <= tol + 1e-9, (t, kind, px)
    return kinds, ties


def test_parity_levels_reproduce_backtest_exits_on_the_qqq_fixture():
    kinds, ties = _parity(dict(cs.CROWN_LEGS["ORB_R6"]), _fixture_arrays())
    assert ties == [], "no float tie on the real fixture -- every exit reproduced exactly"
    # the fixture has initial-stop, breakeven-stop and end-of-day exits
    assert kinds.get("stop", 0) >= 1 and kinds.get("be", 0) >= 1 and kinds.get("eod", 0) >= 5, kinds


def test_parity_levels_reproduce_backtest_exits_on_synthetic_days_with_every_exit_kind():
    """Cent-grid bars with tight ranges, filters off: every exit kind appears, including
    targets. Cent-grid ranges put many raw levels on a whole cent, so a few float ties
    are expected here (see _parity) -- they must stay a small minority."""
    cfg = dict(cs.CROWN_LEGS["ORB_R6"], params=dict(ORB_314, atr_filter=0.0, vpace_filter=0.0))
    kinds, ties = _parity(cfg, _synthetic_arrays())
    assert all(kinds.get(x, 0) >= 1 for x in ("stop", "be", "target", "eod")), kinds
    assert len(ties) <= max(1, sum(kinds.values()) // 10), (len(ties), kinds)


# ── 5. cloud_signal: ledger rows ───────────────────────────────────────────────────────
def _home(tmp_path):
    paths = cs._paths(home=str(tmp_path / "home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    _fixture_df().to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    return paths


def _ticks(day, start, end):
    t = dt.datetime.combine(day, start, tzinfo=TZ)
    stop = dt.datetime.combine(day, end, tzinfo=TZ)
    while t <= stop:
        yield t + dt.timedelta(seconds=6)
        t += dt.timedelta(minutes=5)


def _replay(paths, legs, day, start=dt.time(9, 35), end=dt.time(15, 55)):
    ev = []
    for now in _ticks(day, start, end):
        ev.extend(cs.step(now=now, legs=legs, paths=paths, fetch=False))
    return ev


def test_0921_long_emits_entry_levels_then_one_levels_row(tmp_path):
    """09-21 on the box's bars: long 09:40 at 730.78; breakeven armed at the close of the
    10:15 bar. ENTRY carries the initial stop/target, then ONE LEVELS row names the moved
    stop -- never repeated on later ticks, never an ENTRY/EXIT."""
    paths = _home(tmp_path)
    legs = {"ORB_R6": cs.CROWN_LEGS["ORB_R6"]}
    # seed on the prior session's close so 09-21's trade is a live one
    cs.step(now=dt.datetime(2026, 9, 18, 16, 10, tzinfo=TZ), legs=legs, paths=paths, fetch=False)
    ev = _replay(paths, legs, dt.date(2026, 9, 21), end=dt.time(15, 50))
    kinds = [e["event"] for e in ev]
    assert kinds == ["ENTRY", "LEVELS"], ev
    entry, levels = ev
    tid = "ORB_R6-20260921T134000Z-L"
    assert entry["trade_id"] == levels["trade_id"] == tid
    assert (entry["ref_price"], entry["stop_px"], entry["target_px"]) == (730.78, 725.53, 757.03)
    assert levels["ref_time"] == "2026-09-21T10:15:00-04:00"
    assert levels["ref_price"] == levels["stop_px"] == 730.78
    assert levels["target_px"] == 757.03
    assert levels["reason"].startswith("breakeven armed at the close of 10:20 (the 10:15 bar)")
    assert levels["size"] == "" and levels["side"] == "long"

    state = cs._load_state(paths)
    rec = state["legs"]["ORB_R6"]["trades"][tid]
    assert rec["be_emitted"] == "2026-09-21T10:15:00-04:00" and rec["stop_px"] == 730.78

    # a rerun of the whole day against the same store emits nothing (idempotent)
    for k in state["legs"].values():
        k.pop("last_bar_epoch", None)
    cs._write_state(state, paths)
    assert _replay(paths, legs, dt.date(2026, 9, 21), end=dt.time(15, 50)) == []

    with open(paths["signals_path"], encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))
        f.seek(0)
        rows = list(csv.DictReader(f))
    assert header == cs.SIGNAL_COLS and header[-2:] == ["stop_px", "target_px"]
    by_ev = {r["event"]: r for r in rows}
    assert by_ev["SEED"]["stop_px"] == "" and by_ev["SEED"]["target_px"] == ""
    assert (by_ev["ENTRY"]["stop_px"], by_ev["ENTRY"]["target_px"]) == ("725.53", "757.03")
    assert (by_ev["LEVELS"]["stop_px"], by_ev["LEVELS"]["target_px"]) == ("730.78", "757.03")


def test_0928_entry_carries_the_anchor_levels_and_no_levels_row(tmp_path):
    paths = _home(tmp_path)
    legs = {"ORB_R6": cs.CROWN_LEGS["ORB_R6"]}
    cs.step(now=dt.datetime(2026, 9, 25, 16, 10, tzinfo=TZ), legs=legs, paths=paths, fetch=False)
    ev = _replay(paths, legs, dt.date(2026, 9, 28), end=dt.time(15, 50))
    assert [e["event"] for e in ev] == ["ENTRY"]
    e = ev[0]
    assert (e["side"], e["ref_price"], e["stop_px"], e["target_px"]) == ("short", 732.33, 740.77, 690.14)
    assert e["trade_id"] == "ORB_R6-20260928T144500Z-S"


def test_unflagged_leg_gets_no_levels_and_no_new_keys(tmp_path):
    """The same strategy without cfg["resting_levels"] (a shadow copy, say): no "levels"
    on its trades, no stop_px/target_px keys on its events, no LEVELS rows."""
    paths = _home(tmp_path)
    cfg = {k: v for k, v in cs.CROWN_LEGS["ORB_R6"].items() if k != "resting_levels"}
    cfg["shadow"] = True
    legs = {"ORB_R6": cfg}
    arrays = _fixture_arrays()
    assert all("levels" not in t for t in cs.run_leg_trades(cfg, arrays, "ORB_R6"))
    cs.step(now=dt.datetime(2026, 9, 18, 16, 10, tzinfo=TZ), legs=legs, paths=paths, fetch=False)
    ev = _replay(paths, legs, dt.date(2026, 9, 21), end=dt.time(15, 50))
    assert [e["event"] for e in ev] == ["ENTRY"]
    assert "stop_px" not in ev[0] and "target_px" not in ev[0]


def _levels_trade(still_open=True, be_time="2026-09-21T10:15:00-04:00"):
    return {"side": "long", "entry_time": "2026-09-21T09:40:00-04:00", "entry_px": 730.78,
            "shares": 136, "exit_time": None if still_open else "2026-09-21T10:30:00-04:00",
            "exit_px": None if still_open else 730.78, "still_open": still_open, "size": 1.0,
            "entry_bar": 3,
            "levels": {"stop_px": 725.53, "target_px": 757.03, "be_trigger_px": 733.4,
                       "be_stop_px": 730.78, "be_armed_time": be_time}}


def test_diff_leg_levels_rules():
    cfg = cs.CROWN_LEGS["ORB_R6"]
    now = dt.datetime(2026, 9, 21, 10, 21, tzinfo=TZ)
    tid = "ORB_R6-20260921T134000Z-L"

    # no LEVELS for a trade whose ENTRY was skipped (late) -- it has no lot
    st = {"seeded": True, "trades": {}}
    ev = cs._diff_leg("ORB_R6", [_levels_trade()], st, now, max_entry_age_sec=60, cfg=cfg)
    assert ev == [] and st["trades"][tid]["skipped"] == "late"

    # entry + breakeven seen in one diff: ENTRY then LEVELS; a second diff adds nothing
    st = {"seeded": True, "trades": {}}
    ev = cs._diff_leg("ORB_R6", [_levels_trade()], st, now, max_entry_age_sec=3600, cfg=cfg)
    assert [e["event"] for e in ev] == ["ENTRY", "LEVELS"]
    assert cs._diff_leg("ORB_R6", [_levels_trade()], st, now, max_entry_age_sec=3600, cfg=cfg) == []

    # the trade closed in the same diff that first shows breakeven: EXIT only
    st = {"seeded": True, "trades": {}}
    cs._diff_leg("ORB_R6", [_levels_trade(be_time=None)], st, now, max_entry_age_sec=3600, cfg=cfg)
    ev = cs._diff_leg("ORB_R6", [_levels_trade(still_open=False)], st, now,
                      max_entry_age_sec=3600, cfg=cfg)
    assert [e["event"] for e in ev] == ["EXIT"]
    assert "stop_px" not in ev[0]

    # after the close: no LEVELS
    st = {"seeded": True, "trades": {}}
    cs._diff_leg("ORB_R6", [_levels_trade(be_time=None)], st, now, max_entry_age_sec=3600, cfg=cfg)
    ev = cs._diff_leg("ORB_R6", [_levels_trade()], st,
                      dt.datetime(2026, 9, 21, 16, 5, tzinfo=TZ), max_entry_age_sec=3600, cfg=cfg)
    assert ev == []

    # a leg without the flag ignores levels entirely
    st = {"seeded": True, "trades": {}}
    ev = cs._diff_leg("ORB_R6", [_levels_trade()], st, now, max_entry_age_sec=3600,
                      cfg={k: v for k, v in cfg.items() if k != "resting_levels"})
    assert [e["event"] for e in ev] == ["ENTRY"] and "stop_px" not in ev[0]


def test_misaligned_engine_levels_fail_to_no_levels(monkeypatch):
    """A levels list that does not line up with the trades is never guessed at: the leg
    still trades, with levels None on every trade."""
    arrays = _fixture_arrays()
    real = cs.engine_run_backtest

    def short_levels(*a, **kw):
        res = real(*a, **kw)
        res["levels"] = res["levels"][:-1]
        return res

    monkeypatch.setattr(cs, "engine_run_backtest", short_levels)
    logs = []
    trades = cs.run_leg_trades(cs.CROWN_LEGS["ORB_R6"], arrays, "ORB_R6", log=logs.append)
    assert trades and all(t["levels"] is None for t in trades)
    assert any("misaligned" in m for m in logs)


def test_only_orb_r6_is_flagged():
    flagged = [k for k, v in {**cs.CROWN_LEGS, **cs.SHADOW_LEGS}.items() if v.get("resting_levels")]
    assert flagged == ["ORB_R6"]
    assert cs._leg_accepts_return_levels("ORB_3_6_R6.py")
    assert not cs._leg_accepts_return_levels("NOISE_1_8_CT304.py")
