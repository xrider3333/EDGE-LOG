"""api/cloud_signal.py's decide_at_close probe (WEBULL_PAPER_TODO.md item 16, 2026-09-26).

A decide-at-close plugin (NOISE_1_0.py) decides at bar D's close and fills at D+1's open;
the live engine only sees closed bars, so without the probe every such order goes out a
bar after the backtest's own fill. These tests drive the real step()/_diff_leg pipeline
with a stub that copies NOISE_1_0.py's bar loop (STEP A fills queued at the previous
close, STEP A2 stop skipped on the entry bar, STEP C/D decisions at the close, STEP E
end-of-data flatten) on a schedule keyed by bar time, plus the real NOISE_1_0.py on
synthetic bars through tools/decide_at_close_replay.py. No network, no live files.
"""
import os
import types

import numpy as np
import pandas as pd
import pytest

import api.cloud_signal as cs
from api import trade_id

DAY = "2026-09-08"                        # a Tuesday, full session
LEG = "NZ"


def _mech_stub(decisions, stop_pts=None):
    """decisions: {"HH:MM" of bar D: "long" | "short" | "exit"} acted on at D's close."""
    mod = types.ModuleType("dac_mech_stub")
    mod.STRATEGY_NAME = "DAC_MECH_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        o, h, l, c = (np.asarray(x, float) for x in (opens, highs, lows, closes))
        n = len(c)
        did = np.asarray(day_id)
        log = []
        a = 0
        while a < n:
            b = a
            while b < n and did[b] == did[a]:
                b += 1
            pos, entry_px, entry_k, pend, exit_pend, stop = 0, 0.0, -1, 0, False, None
            for k in range(b - a):
                i = a + k
                is_last = i == b - 1
                dec = decisions.get(index[i].strftime("%H:%M"))
                if exit_pend:                                       # STEP A
                    log.append((a + entry_k, i, (o[i] - entry_px) * pos, pos, entry_px))
                    pos, exit_pend = 0, False
                if pend and pos == 0:
                    pos, entry_px, entry_k, pend = pend, o[i], k, 0
                    stop = entry_px - pos * stop_pts if stop_pts else None
                if pos and k != entry_k and stop is not None:       # STEP A2
                    hit = (o[i] < stop or l[i] <= stop) if pos > 0 else (o[i] > stop or h[i] >= stop)
                    if hit:
                        gap = o[i] < stop if pos > 0 else o[i] > stop
                        px = o[i] if gap else stop
                        log.append((a + entry_k, i, (px - entry_px) * pos, pos, entry_px))
                        pos = 0
                if pos and dec == "exit":                           # STEP C
                    if is_last:
                        log.append((a + entry_k, i, (c[i] - entry_px) * pos, pos, entry_px))
                        pos = 0
                    else:
                        exit_pend = True
                if pos == 0 and not is_last and dec in ("long", "short"):   # STEP D
                    pend = 1 if dec == "long" else -1
                if is_last and pos:                                 # STEP E
                    log.append((a + entry_k, i, (c[i] - entry_px) * pos, pos, entry_px))
                    pos = 0
            a = b
        if not log:
            return None
        return {"trades": log if return_trades else None, "num_trades": len(log),
                "total_pnl": float(sum(t[2] for t in log)), "win_rate": 0, "profit_factor": 0,
                "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}

    mod.run_backtest = run_backtest
    return mod


def _bars(overrides=None, day=DAY):
    """78 five-minute RTH bars; overrides: {"HH:MM": (open, high, low, close)}."""
    base = pd.Timestamp(f"{day} 09:30", tz=cs.TZ)
    times = [base + pd.Timedelta(minutes=5 * i) for i in range(78)]
    rows = []
    for i, t in enumerate(times):
        c = 700.0 + 0.1 * i
        o, hi, lo = c - 0.05, c + 0.2, c - 0.25
        if overrides and t.strftime("%H:%M") in overrides:
            o, hi, lo, c = overrides[t.strftime("%H:%M")]
        rows.append({"time": int(t.tz_convert("UTC").timestamp()), "open": o, "high": hi,
                     "low": lo, "close": c, "volume": 1000.0})
    return pd.DataFrame(rows)


def _home(tmp_path, df, name="home"):
    paths = cs._paths(home=str(tmp_path / name))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    return paths


def _legs(stub, flag):
    return {LEG: {"strategy": stub, "timeframe": "5m", "params": {}, "warmup_sessions": 5,
                  "decide_at_close": flag}}


def _after(hhmm, day=DAY):
    """step()'s `now` 10 s after the bar starting at hhmm has closed."""
    return (pd.Timestamp(f"{day} {hhmm}", tz=cs.TZ) + pd.Timedelta(seconds=310)).to_pydatetime()


def _ts(hhmm, day=DAY):
    return pd.Timestamp(f"{day} {hhmm}", tz=cs.TZ).isoformat()


def _run(paths, legs, *hhmms):
    """SEED at the first bar, then one tick per bar: {hhmm: [events]}."""
    seed = cs.step(now=_after("09:30"), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in seed] == ["SEED"]
    return {h: cs.step(now=_after(h), legs=legs, paths=paths, fetch=False) for h in hhmms}


def _close(df, hhmm):
    t = int(pd.Timestamp(f"{DAY} {hhmm}", tz=cs.TZ).tz_convert("UTC").timestamp())
    return float(df.loc[df["time"] == t, "close"].iloc[0])


def _open(df, hhmm):
    t = int(pd.Timestamp(f"{DAY} {hhmm}", tz=cs.TZ).tz_convert("UTC").timestamp())
    return float(df.loc[df["time"] == t, "open"].iloc[0])


TICKS = ["09:35", "09:40", "09:45", "09:50", "09:55", "10:00", "10:05", "10:10", "10:15",
         "10:20", "10:25", "10:30", "10:35", "10:40", "10:45"]


# ── probe off / on ──────────────────────────────────────────────────────────────────────

def test_probe_off_entry_waits_for_the_fill_bar_to_close(tmp_path):
    df = _bars()
    out = _run(_home(tmp_path, df), _legs(_mech_stub({"10:00": "long"}), False), *TICKS)
    assert out["10:00"] == []
    assert [e["event"] for e in out["10:05"]] == ["ENTRY"]
    e = out["10:05"][0]
    assert e["ref_time"] == _ts("10:05")
    assert e["ref_price"] == pytest.approx(_open(df, "10:05"))
    assert e["reason"] == ""


def test_probe_on_entry_goes_out_at_the_decision_close_and_never_twice(tmp_path):
    df = _bars()
    paths = _home(tmp_path, df)
    out = _run(paths, _legs(_mech_stub({"10:00": "long"}), True), *TICKS)
    assert [e["event"] for e in out["10:00"]] == ["ENTRY"]
    e = out["10:00"][0]
    assert e["ref_time"] == _ts("10:05")                  # the fill bar, only just starting
    assert e["ref_price"] == pytest.approx(_close(df, "10:00"))
    assert e["side"] == "long"
    assert e["trade_id"] == trade_id.make(LEG, _ts("10:05"), "long")
    assert cs.DECIDE_AT_CLOSE_TAG in e["reason"] and "10:00" in e["reason"]
    # the real 10:05 bar closes: same trade, already recorded -> nothing new, ever
    assert all(out[h] == [] for h in TICKS[TICKS.index("10:05"):])
    recs = cs._load_state(paths)["legs"][LEG]["trades"]
    assert list(recs) == [e["trade_id"]]


def test_probe_on_exit_queued_at_close_is_emitted_at_that_close(tmp_path):
    df = _bars()
    stub = _mech_stub({"10:00": "long", "10:30": "exit"})
    on = _run(_home(tmp_path, df, "on"), _legs(stub, True), *TICKS)
    assert [e["event"] for e in on["10:30"]] == ["EXIT"]
    x = on["10:30"][0]
    assert x["ref_time"] == _ts("10:35")
    assert x["ref_price"] == pytest.approx(_close(df, "10:30"))
    assert x["reason"].startswith("strategy_exit; " + cs.DECIDE_AT_CLOSE_TAG)
    assert x["trade_id"] == trade_id.make(LEG, _ts("10:05"), "long")
    assert on["10:35"] == [] and on["10:40"] == []

    off = _run(_home(tmp_path, df, "off"), _legs(stub, False), *TICKS)
    assert off["10:30"] == []
    assert [e["event"] for e in off["10:35"]] == ["EXIT"]
    assert off["10:35"][0]["ref_time"] == _ts("10:35")
    assert off["10:35"][0]["ref_price"] == pytest.approx(_open(df, "10:35"))
    assert off["10:35"][0]["reason"] == "strategy_exit"


def test_force_close_at_the_stand_in_is_not_an_exit(tmp_path):
    """An open position with no exit decision is flattened by the plugin at the end of the
    stand-in data; that must never read as an EXIT."""
    df = _bars()
    paths = _home(tmp_path, df)
    out = _run(paths, _legs(_mech_stub({"10:00": "long"}), True), *TICKS)
    assert [e["event"] for h in TICKS for e in out[h]] == ["ENTRY"]
    recs = cs._load_state(paths)["legs"][LEG]["trades"]
    assert [r["exit_emitted"] for r in recs.values()] == [False]


def test_stop_on_the_stand_in_is_ignored_and_the_real_stop_still_goes_out(tmp_path):
    """Entry fills at the 10:05 open; that bar CLOSES below the stop (the stub, like
    NOISE_1_0.py, never checks a stop on the entry bar), so the flat stand-in for 10:10
    would stop out at its open -- a guess about a bar that has not happened. Nothing may
    be emitted for it; the real 10:10 bar's stop goes out through the normal path."""
    df = _bars({"10:05": (700.5, 700.6, 697.0, 697.2),       # entry at 700.5, stop 699.5
                "10:10": (697.3, 697.5, 696.9, 697.1)})      # gaps through the stop
    out = _run(_home(tmp_path, df), _legs(_mech_stub({"10:00": "long"}, stop_pts=1.0), True), *TICKS)
    assert [e["event"] for e in out["10:00"]] == ["ENTRY"]
    assert out["10:05"] == []                                # the stand-in stop, ignored
    assert [e["event"] for e in out["10:10"]] == ["EXIT"]
    x = out["10:10"][0]
    assert x["ref_time"] == _ts("10:10")
    assert x["ref_price"] == pytest.approx(697.3)
    assert x["reason"] == "strategy_exit"


@pytest.mark.parametrize("side", ["long", "short"])
def test_exit_decided_on_the_entry_bar_goes_out_via_the_confirm_run(tmp_path, side):
    """Entered at the 10:05 open, exit queued at the 10:05 close (the stop is never
    checked on the entry bar, so the flat stand-in alone cannot tell this from a stop):
    the confirm run proves it was queued, and it goes out at the 10:05 close."""
    df = _bars()
    stub = _mech_stub({"10:00": side, "10:05": "exit"}, stop_pts=0.01)   # stop sits AT D's close side
    out = _run(_home(tmp_path, df), _legs(stub, True), *TICKS)
    assert [e["event"] for e in out["10:00"]] == ["ENTRY"]
    assert [e["event"] for e in out["10:05"]] == ["EXIT"]
    x = out["10:05"][0]
    assert x["ref_time"] == _ts("10:10")
    assert x["ref_price"] == pytest.approx(_close(df, "10:05"))
    assert cs.DECIDE_AT_CLOSE_TAG in x["reason"]
    assert out["10:10"] == []


def test_probe_skipped_on_the_sessions_last_bar():
    """No D+1 exists in the session: the probe must not even run the leg."""
    calls = []

    def boom(arrays):                      # the probe swallows exceptions, so count calls
        calls.append(arrays)
        return []

    for day, last in ((DAY, "15:55"), ("2026-11-27", "12:55")):   # full day, half day
        df = _bars(day=day)
        arrays = cs.build_arrays(df)
        cut = arrays["index"] <= pd.Timestamp(f"{day} {last}", tz=cs.TZ)
        arrays = {k: v[cut] for k, v in arrays.items()}
        now = _after(last, day=day)
        trades = [{"entry_time": "x", "side": "long", "still_open": True}]
        got, arr = cs._decide_at_close_probe(arrays, trades, "5m", now, boom, log=lambda *a: None)
        assert got is trades and arr is arrays
    assert calls == []
    assert cs._is_session_last_bar(pd.Timestamp(f"{DAY} 15:50", tz=cs.TZ), "5m") is False
    assert cs._is_session_last_bar(pd.Timestamp("2026-11-27 12:50", tz=cs.TZ), "5m") is False


def test_probe_skipped_when_the_newest_bar_is_from_an_earlier_session():
    arrays = cs.build_arrays(_bars())
    arrays = {k: v[:20] for k, v in arrays.items()}
    now = (pd.Timestamp("2026-09-09 09:31", tz=cs.TZ)).to_pydatetime()
    calls = []
    got, _ = cs._decide_at_close_probe(arrays, [], "5m", now, lambda a: calls.append(a) or [],
                                        log=lambda *a: None)
    assert got == [] and calls == []


def test_probe_failure_falls_back_to_the_closed_bar_signals():
    arrays = cs.build_arrays(_bars())
    arrays = {k: v[:20] for k, v in arrays.items()}
    msgs = []

    def broken(_arrays):
        raise RuntimeError("plugin blew up")
    trades = [{"entry_time": "x", "side": "long", "still_open": True}]
    got, arr = cs._decide_at_close_probe(arrays, trades, "5m", _after("11:05"), broken, log=msgs.append)
    assert got is trades and arr is arrays
    assert msgs and "falling back" in msgs[0]


def test_stand_in_arrays_shape():
    arrays = cs.build_arrays(_bars())
    arrays = {k: v[:20] for k, v in arrays.items()}
    p = cs._stand_in_arrays(arrays, "5m")
    assert len(p["close"]) == 22 and len(p["index"]) == 22
    last = float(arrays["close"][-1])
    for k in ("open", "high", "low", "close"):
        assert list(p[k][-2:]) == [last, last]
        assert np.array_equal(p[k][:20], arrays[k])
    assert list(p["volume"][-2:]) == [0.0, 0.0]
    assert list(p["day_id"][-2:]) == [arrays["day_id"][-1]] * 2
    assert p["index"][-2] == arrays["index"][-1] + pd.Timedelta(minutes=5)
    assert p["index"][-1] == arrays["index"][-1] + pd.Timedelta(minutes=10)
    assert len(arrays["close"]) == 20                         # input untouched


def test_flag_is_on_for_noise_382_only():
    assert cs.CROWN_LEGS["NOISE_382"].get("decide_at_close") is True
    assert not cs.CROWN_LEGS["ORB_R6"].get("decide_at_close")
    # ENGUQ_335 is a shadow leg since 2026-09-28; the #422 shadow legs carry the flag like
    # NOISE_382 does (they are the same decide-at-close NOISE core)
    assert not cs.SHADOW_LEGS["ENGUQ_335"].get("decide_at_close")
    for k in ("NOISE_422_PLAIN", "NOISE_422_FIXED", "NOISE_422_KEEL"):
        assert cs.SHADOW_LEGS[k].get("decide_at_close") is True, k


# ── the real NOISE_1_0.py, bar by bar, flag off vs on (tools/decide_at_close_replay.py) ──

def _noise_bars(n_sessions=9, seed=7):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2026-06-01", periods=n_sessions + 2)
    days = [d for d in days if d.strftime("%Y-%m-%d") != "2026-06-19"][:n_sessions]
    rows, px = [], 500.0
    for d in days:
        base = pd.Timestamp(f"{d.date()} 09:30", tz=cs.TZ)
        drift = rng.normal(0, 0.0015)
        for i in range(78):
            o = px
            c = o * (1 + drift + rng.normal(0, 0.0018))
            rows.append({"time": int((base + pd.Timedelta(minutes=5 * i)).tz_convert("UTC").timestamp()),
                         "open": o, "high": max(o, c) * (1 + abs(rng.normal(0, 0.0006))),
                         "low": min(o, c) * (1 - abs(rng.normal(0, 0.0006))), "close": c,
                         "volume": float(rng.integers(5000, 20000))})
            px = c
        px *= 1 + rng.normal(0, 0.004)
    return pd.DataFrame(rows)


def test_replay_real_noise_flag_on_removes_the_bar_of_lag_and_changes_nothing_else(tmp_path):
    from tools import decide_at_close_replay as R
    legs = {"NOISE_T": {"strategy": "NOISE_1_0.py", "timeframe": "5m", "warmup_sessions": 60,
                        "params": {"lookback": 5, "band_mult_long": 0.35, "band_mult_short": 0.35,
                                   "exit_mode": "vwap", "stop_mode": "bandwidth", "stop_k": 1.0}}}
    df = _noise_bars(seed=11)
    scores = {}
    for flag in (False, True):
        run = R.replay(df, "NOISE_T", R.leg_cfg("NOISE_T", flag, legs), 3, str(tmp_path / f"s{flag}"))
        scores[flag] = R.score(run)
    off, on = scores[False], scores[True]
    assert off["trades"] >= 5, "synthetic tape too quiet to prove anything"
    for sc in (off, on):
        assert sc["missed_entries"] == [] and sc["extra_trade_ids"] == []
        assert sc["duplicates"] == {} and sc["side_mismatch"] == [] and sc["exit_bar_mismatch"] == []
        assert sc["exits_missing"] == []
    assert off["entry_lag_s"] == {"300": off["trades"]}              # one bar late, every one
    assert on["entry_lag_s"] == {"0": on["trades"]}                  # at the decision close
    assert on["probe_entries"] == on["trades"]
    assert set(off["exit_lag_s_by_kind"]["open"]) <= {"300"}
    queued = [r for r in on["rows"] if r.get("exit_probe")]
    assert queued and all(r["exit_lag_s"] == 0 for r in queued)
    # every open-fill exit went out early unless its trade entered on the decision bar
    for r in on["rows"]:
        if r["exit_kind"] == "open" and "exit_lag_s" in r and not r.get("exit_probe"):
            assert r["exit_lag_s"] == 300
    assert [r["trade_id"] for r in off["rows"]] == [r["trade_id"] for r in on["rows"]]
