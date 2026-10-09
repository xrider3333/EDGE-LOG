"""EOD SETTLE (2026-09-28) -- api/cloud_signal.py emits the day's last-bar exits right after
the close instead of the next morning.

Before: cloud_signal_thread stepped only while 09:30 <= now <= 16:00:00, and the session's
last bar (5m 15:55, 1m 15:59) became usable at 16:00:05 -- so it was first seen the next
morning. Even then, run_leg_trades' AMBIGUOUS BOUNDARY rule read an exit at the newest bar's
own close as "still open". The box's cloud_signal.log showed the result: the backtest's
end-of-day EXIT emitted around 09:35 the next session with the old 15:55 ref_time.

Covered here, with a stub strategy that behaves like ORB_3_6's and NOISE_1_0's end-of-day
flatten (every position closes at the close of the data's last bar):
  * the settle step at 16:00:30 emits the EXIT at the 15:55 bar's close (the backtest's own
    16:00 fill) and never an ENTRY; the next morning emits nothing more for that trade;
  * a leg without eod_flat (ENGUQ holds overnight) is unchanged -- still open;
  * a trade that enters on the last bar is recorded "after_close", never emitted, including a
    regular/stream step that lands exactly on the bell;
  * a recognised half day settles after 13:00;
  * _eod_settle_tick's pacing, stamp, give-up, the shadow-leg hook, and the thread itself
    running the settle step (not the stream wrapper) after the close.
No network: every step here runs with fetch=False against a temp bar cache.
"""
import datetime
import json
import os
import types

import pandas as pd
import pytest

import api.cloud_signal as cs

ET = cs._zi(cs.TZ)
LAST_CLOSE = 736.54        # the 09-28 15:55 bar close the design names (ORB's 16:00 fill)


def _stub(mode="orb"):
    """Per session day in the window: "orb" shorts at the close of the day's 2nd bar and is
    flat at the close of that day's last bar in the data; "last_bar" enters long on the
    last 15:55 bar (or 12:55 on a half day) and is flat on that same bar."""
    mod = types.ModuleType(f"eod_settle_stub_{mode}")
    mod.STRATEGY_NAME = "EOD_SETTLE_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        trades = []
        n = len(closes)
        days = {}
        for i in range(n):
            days.setdefault(int(day_id[i]), []).append(i)
        for bars in days.values():
            last = bars[-1]
            if mode == "orb" and len(bars) >= 2:
                entry = bars[1]
                trades.append((entry, last, float(closes[entry] - closes[last]), -1,
                               float(closes[entry])))
            elif mode == "last_bar":
                t = index[last]
                if (t.hour, t.minute) in ((15, 55), (12, 55)):
                    trades.append((last, last, 0.0, 1, float(closes[last])))
        return {"trades": trades if return_trades else None, "num_trades": len(trades),
                "total_pnl": 0.0, "win_rate": 0, "profit_factor": 0, "max_drawdown": 0,
                "avg_pnl": 0, "wins": 0, "losses": 0}

    mod.run_backtest = run_backtest
    return mod


def _session_bars(day, last_hhmm="15:55", last_close=LAST_CLOSE):
    start = pd.Timestamp(f"{day} 09:30:00", tz=cs.TZ)
    end = pd.Timestamp(f"{day} {last_hhmm}:00", tz=cs.TZ)
    times = list(pd.date_range(start, end, freq="5min"))
    closes = [735.0 + 0.01 * i for i in range(len(times))]
    closes[-1] = last_close
    return pd.DataFrame({
        "time": [int(t.tz_convert("UTC").timestamp()) for t in times],
        "open": closes, "high": [c + 0.2 for c in closes], "low": [c - 0.2 for c in closes],
        "close": closes, "volume": [1000.0] * len(times)})


def _home(tmp_path, df, name="home"):
    paths = cs._paths(home=str(tmp_path / name))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    return paths


def _legs(mode="orb", eod_flat=True):
    cfg = {"strategy": _stub(mode), "timeframe": "5m", "params": {}, "warmup_sessions": 5,
           "max_entry_age_sec": 3600}
    if eod_flat:
        cfg["eod_flat"] = True
    return {"ORB_R6": cfg}


def _at(day, hh, mm, ss=0):
    y, mo, d = (int(x) for x in day.split("-"))
    return datetime.datetime(y, mo, d, hh, mm, ss, tzinfo=ET)


def _arm_and_enter(paths, legs, day="2026-09-28"):
    """Seed on an empty window, then see the 09:35 short enter (a live ENTRY)."""
    seed = cs.step(now=_at(day, 9, 36), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in seed] == ["SEED"]
    entry = cs.step(now=_at(day, 9, 40, 10), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in entry] == ["ENTRY"]
    return entry[0]


# ── the settle step itself ───────────────────────────────────────────────────────────

def test_settle_step_emits_the_eod_exit_at_the_last_bar_close_and_no_entry(tmp_path):
    paths = _home(tmp_path, _session_bars("2026-09-28"))
    legs = _legs()
    entry = _arm_and_enter(paths, legs)

    warnings = {}
    events = cs.step(now=_at("2026-09-28", 16, 0, 30), legs=legs, paths=paths, fetch=False,
                     warnings=warnings, post_close=True)

    assert [e["event"] for e in events] == ["EXIT"]
    ex = events[0]
    assert ex["trade_id"] == entry["trade_id"]
    assert ex["ref_time"] == "2026-09-28T15:55:00-04:00"
    assert ex["ref_price"] == pytest.approx(LAST_CLOSE)
    assert "eod_settle" in ex["reason"]
    assert warnings["eod_settled"] is True
    assert cs._load_state(paths)["eod_settled"]["2026-09-28"]["bars"]["ORB_R6"].startswith(
        "2026-09-28T15:55")


def test_without_the_flag_the_last_bar_exit_still_reads_as_open(tmp_path):
    """The old AMBIGUOUS BOUNDARY behaviour, kept for a leg that holds overnight (ENGUQ)."""
    paths = _home(tmp_path, _session_bars("2026-09-28"))
    legs = _legs(eod_flat=False)
    _arm_and_enter(paths, legs)
    events = cs.step(now=_at("2026-09-28", 16, 0, 30), legs=legs, paths=paths, fetch=False,
                     post_close=True)
    assert events == []


def test_the_real_legs_flag_orb_and_every_noise_but_not_enguq():
    assert cs.CROWN_LEGS["ORB_R6"].get("eod_flat") is True
    assert cs.CROWN_LEGS["NOISE_382"].get("eod_flat") is True
    # the #422 shadow legs are flat at the close like the primary. ENGU-Q, live again since
    # 2026-10-09 with its pre-09-28 cfg, has no eod_flat: its STRATEGY holds overnight in the
    # backtest, and since the 10-09 owner GO (MANAGER #106) the book holds it too: qqq_exec's
    # flat_by flatten keeps ENGU-Q (HOLD_OVERNIGHT_LEGS) and sells it on this EXIT
    for key in ("NOISE_422_PLAIN", "NOISE_422_FIXED", "NOISE_422_KEEL"):
        assert cs.SHADOW_LEGS[key].get("eod_flat") is True, key
    assert "ENGUQ_335" in cs.CROWN_LEGS and "ENGUQ_335" not in cs.SHADOW_LEGS
    assert not cs.CROWN_LEGS["ENGUQ_335"].get("eod_flat")


def test_next_morning_step_emits_nothing_more_for_a_settled_trade(tmp_path):
    day1 = _session_bars("2026-09-28")
    paths = _home(tmp_path, day1)
    legs = _legs()
    _arm_and_enter(paths, legs)
    assert [e["event"] for e in cs.step(now=_at("2026-09-28", 16, 0, 30), legs=legs,
                                        paths=paths, fetch=False, post_close=True)] == ["EXIT"]
    both = pd.concat([day1, _session_bars("2026-09-29", last_hhmm="09:30")], ignore_index=True)
    both.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    assert cs.step(now=_at("2026-09-29", 9, 35, 10), legs=legs, paths=paths, fetch=False) == []


def test_before_the_fix_the_exit_waited_for_the_next_morning(tmp_path):
    """The same bars without the settle step: nothing at 16:00:00 (the thread's last
    in-session tick), and the EXIT only on the next session's first new bar."""
    day1 = _session_bars("2026-09-28")
    paths = _home(tmp_path, day1)
    legs = _legs()
    _arm_and_enter(paths, legs)
    assert cs.step(now=_at("2026-09-28", 16, 0, 0), legs=legs, paths=paths, fetch=False) == []
    both = pd.concat([day1, _session_bars("2026-09-29", last_hhmm="09:30")], ignore_index=True)
    both.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    late = cs.step(now=_at("2026-09-29", 9, 35, 10), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in late] == ["EXIT"], "without the settle step it lands a day late"


# ── no ENTRY after the bell ──────────────────────────────────────────────────────────

def test_a_last_bar_entry_is_recorded_after_close_and_never_emitted(tmp_path):
    paths = _home(tmp_path, _session_bars("2026-09-28"))
    legs = _legs("last_bar")
    cs.step(now=_at("2026-09-28", 9, 36), legs=legs, paths=paths, fetch=False)   # seed
    events = cs.step(now=_at("2026-09-28", 16, 0, 30), legs=legs, paths=paths, fetch=False,
                     post_close=True)
    assert events == []
    leg_state = cs._load_state(paths)["legs"]["ORB_R6"]
    assert leg_state["after_close_skipped"] == 1


def test_a_regular_step_landing_on_the_bell_is_treated_as_after_close(tmp_path):
    """A stream or regular step that sees the last bar at/after 16:00 (post_close not
    passed) must not emit an actionable ENTRY either."""
    paths = _home(tmp_path, _session_bars("2026-09-28"))
    legs = _legs("last_bar")
    cs.step(now=_at("2026-09-28", 9, 36), legs=legs, paths=paths, fetch=False)   # seed
    assert cs.step(now=_at("2026-09-28", 16, 0, 10), legs=legs, paths=paths, fetch=False) == []
    assert cs._load_state(paths)["legs"]["ORB_R6"]["after_close_skipped"] == 1


# ── half day ─────────────────────────────────────────────────────────────────────────

def test_half_day_settles_after_13_00(tmp_path):
    day = "2026-11-27"                     # the day after Thanksgiving: 13:00 close
    assert cs.market_calendar.session_close_et(day) == "13:00"
    paths = _home(tmp_path, _session_bars(day, last_hhmm="12:55"))
    legs = _legs()
    _arm_and_enter(paths, legs, day=day)
    close_dt = cs._eod_settle_close(_at(day, 13, 0, 30))
    assert close_dt == _at(day, 13, 0)
    warnings = {}
    events = cs.step(now=_at(day, 13, 0, 30), legs=legs, paths=paths, fetch=False,
                     warnings=warnings, post_close=True)
    assert [(e["event"], e["ref_time"]) for e in events] == [("EXIT", f"{day}T12:55:00-05:00")]
    assert warnings["eod_settled"] is True


def test_settle_window_bounds():
    assert cs._eod_settle_close(_at("2026-09-28", 16, 0, 0)) is None          # still the bell
    assert cs._eod_settle_close(_at("2026-09-28", 16, 0, 1)) == _at("2026-09-28", 16, 0)
    assert cs._eod_settle_close(_at("2026-09-28", 16, 5, 0)) == _at("2026-09-28", 16, 0)
    assert cs._eod_settle_close(_at("2026-09-28", 16, 5, 1)) is None
    assert cs._eod_settle_close(_at("2026-09-27", 16, 1, 0)) is None          # a Sunday


# ── _eod_settle_tick pacing, stamp, give-up ──────────────────────────────────────────

def _offline_step(monkeypatch, legs, calls):
    real_step = cs.step

    def fake_step(**kw):
        calls.append(kw)
        kw = dict(kw, fetch=False, legs=legs)
        return real_step(**kw)
    monkeypatch.setattr(cs, "step", fake_step)
    # the shadow hook has its own tests; here it would step the real shadow legs on the
    # live store (and fetch)
    monkeypatch.setattr(cs, "_eod_settle_shadow", lambda now, log=print: [])


def _hb(paths):
    with open(paths["heartbeat_path"], encoding="utf-8") as f:
        return json.load(f)


def test_settle_tick_waits_then_steps_once_then_stops(tmp_path, monkeypatch):
    paths = _home(tmp_path, _session_bars("2026-09-28"))
    legs = _legs()
    _arm_and_enter(paths, legs)
    calls = []
    _offline_step(monkeypatch, legs, calls)
    close_dt = _at("2026-09-28", 16, 0)
    mem = {}

    assert cs._eod_settle_tick(_at("2026-09-28", 16, 0, 10), close_dt, mem, paths=paths,
                               log=lambda *a: None) == []
    assert calls == [] and "waiting" in _hb(paths)["note"]

    events = cs._eod_settle_tick(_at("2026-09-28", 16, 0, 31), close_dt, mem, paths=paths,
                                 log=lambda *a: None)
    assert [e["event"] for e in events] == ["EXIT"]
    assert len(calls) == 1 and calls[0]["post_close"] is True and calls[0]["fetch"] is True
    assert _hb(paths)["ok"] is True and "(settled)" in _hb(paths)["note"]

    assert cs._eod_settle_tick(_at("2026-09-28", 16, 1, 10), close_dt, mem, paths=paths,
                               log=lambda *a: None) == []
    assert len(calls) == 1, "settled: no further steps"
    # a restart inside the window reads the stamp and does not step again
    assert cs._eod_settle_tick(_at("2026-09-28", 16, 1, 40), close_dt, {}, paths=paths,
                               log=lambda *a: None) == []
    assert len(calls) == 1


def test_settle_tick_retries_every_30s_then_gives_up(tmp_path, monkeypatch):
    # the 15:55 bar never arrives
    paths = _home(tmp_path, _session_bars("2026-09-28", last_hhmm="15:50"))
    legs = _legs()
    _arm_and_enter(paths, legs)
    calls, lines = [], []
    _offline_step(monkeypatch, legs, calls)
    close_dt = _at("2026-09-28", 16, 0)
    mem = {}
    t = _at("2026-09-28", 16, 0, 30)
    while t <= close_dt + datetime.timedelta(seconds=cs.EOD_SETTLE_WINDOW_SEC):
        assert cs._eod_settle_tick(t, close_dt, mem, paths=paths, log=lines.append) == []
        t += datetime.timedelta(seconds=5)
    assert 8 <= len(calls) <= 10, len(calls)
    assert mem["2026-09-28"]["gave_up"] is True
    assert sum("GAVE UP" in ln for ln in lines) == 1
    assert "eod_settled" not in cs._load_state(paths)


def test_a_failing_settle_step_keeps_the_heartbeat_ok_and_still_writes_gave_up(tmp_path, monkeypatch):
    """2026-09-28 review: a step() that raises inside the window must not turn the heartbeat
    ok=False (qqq_exec would call the engine stalled after the bell), and the last try's
    failure must still write the one-line GAVE UP."""
    paths = _home(tmp_path, _session_bars("2026-09-28"))
    calls, lines = [], []

    def boom(**kw):
        calls.append(kw)
        raise OSError("REST fetch timed out")
    monkeypatch.setattr(cs, "step", boom)
    close_dt = _at("2026-09-28", 16, 0)
    mem = {}
    t = _at("2026-09-28", 16, 0, 30)
    while t <= close_dt + datetime.timedelta(seconds=cs.EOD_SETTLE_WINDOW_SEC):
        before = len(calls)
        assert cs._eod_settle_tick(t, close_dt, mem, paths=paths, log=lines.append) == []
        if len(calls) > before:                   # this pass stepped (and failed)
            hb = _hb(paths)
            assert hb["ok"] is True and hb["note"].startswith("eod settle failed: OSError")
        t += datetime.timedelta(seconds=5)
    assert 8 <= len(calls) <= 10, len(calls)
    assert mem["2026-09-28"]["gave_up"] is True
    assert sum("GAVE UP" in ln for ln in lines) == 1
    assert _hb(paths)["ok"] is True


def test_thread_failure_while_settling_writes_an_ok_heartbeat(tmp_path, monkeypatch):
    import threading
    paths = cs._paths(home=str(tmp_path / "live"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    monkeypatch.setattr(cs, "_serving_hosts_ok", lambda log=print: (True, None))
    monkeypatch.setattr(cs, "log_history_windows", lambda **k: None)
    fixed = _at("2026-09-28", 16, 0, 31)

    class FixedDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    monkeypatch.setattr(cs, "_dt", types.SimpleNamespace(
        datetime=FixedDT, timedelta=datetime.timedelta, time=datetime.time, date=datetime.date))

    def tick_boom(*a, **k):
        raise RuntimeError("state file locked")
    monkeypatch.setattr(cs, "_eod_settle_tick", tick_boom)
    stop = threading.Event()
    monkeypatch.setattr(cs._time, "sleep", lambda s: stop.set())

    cs.cloud_signal_thread(stop=stop, log=lambda *a, **k: None)

    hb = _hb(paths)
    assert hb["ok"] is True and hb["note"].startswith("eod settle failed: RuntimeError")


def test_shadow_hook_runs_only_a_post_close_aware_shadow_step(monkeypatch):
    seen = []

    def aware(now=None, fetch=True, post_close=False, log=print):
        seen.append(post_close)
        return [{"event": "EXIT"}]
    monkeypatch.setattr(cs, "run_shadow_step", aware, raising=False)
    assert cs._eod_settle_shadow(_at("2026-09-28", 16, 0, 31)) == [{"event": "EXIT"}]
    assert seen == [True]

    def unaware(now=None, fetch=True, log=print):
        raise AssertionError("must not be stepped after the bell without post_close")
    monkeypatch.setattr(cs, "run_shadow_step", unaware, raising=False)
    assert cs._eod_settle_shadow(_at("2026-09-28", 16, 0, 31)) == []


def test_the_real_shadow_step_settles_after_the_bell_without_an_entry(tmp_path, monkeypatch):
    """run_shadow_step(post_close=True) -- what _eod_settle_shadow now calls -- writes the
    shadow leg's last-bar EXIT into the shadow store the same evening and no ENTRY, and
    never touches the live store."""
    monkeypatch.setattr(cs, "NOISE_FORWARD_LOG", False)
    paths = _home(tmp_path, _session_bars("2026-09-28"))
    legs = _legs()
    kw = dict(fetch=False, live_legs={}, shadow_legs=legs, live_paths=paths)
    assert [e["event"] for e in cs.run_shadow_step(now=_at("2026-09-28", 9, 36), **kw)] == ["SEED"]
    assert [e["event"] for e in cs.run_shadow_step(now=_at("2026-09-28", 9, 40, 10), **kw)] == ["ENTRY"]
    events = cs.run_shadow_step(now=_at("2026-09-28", 16, 0, 30), post_close=True, **kw)
    assert [e["event"] for e in events] == ["EXIT"]
    assert events[0]["ref_price"] == pytest.approx(LAST_CLOSE)
    assert not os.path.exists(paths["signals_path"])
    assert os.path.exists(cs.shadow_paths(paths)["signals_path"])


# ── the thread runs the settle step (not the stream wrapper) after the close ─────────

def test_thread_runs_the_settle_step_after_the_close(tmp_path, monkeypatch):
    import threading
    paths = cs._paths(home=str(tmp_path / "live"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    monkeypatch.setattr(cs, "_serving_hosts_ok", lambda log=print: (True, None))
    monkeypatch.setattr(cs, "log_history_windows", lambda **k: None)
    fixed = _at("2026-09-28", 16, 0, 31)

    class FixedDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    monkeypatch.setattr(cs, "_dt", types.SimpleNamespace(
        datetime=FixedDT, timedelta=datetime.timedelta, time=datetime.time, date=datetime.date))
    steps = []

    def fake_step(**kw):
        steps.append(kw)
        if kw.get("warnings") is not None:
            kw["warnings"]["eod_settled"] = True
        return []
    monkeypatch.setattr(cs, "step", fake_step)
    from api import cloud_signal_stream as stream_mod

    def no_stream(**kw):
        raise AssertionError("the stream wrapper must not run after the close")
    monkeypatch.setattr(stream_mod, "run_stream_aware_step", no_stream)
    stop = threading.Event()
    sleeps = []

    def fake_sleep(s):
        sleeps.append(s)
        stop.set()
    monkeypatch.setattr(cs._time, "sleep", fake_sleep)

    # the shadow legs settle too (run_shadow_step, post_close): no network here
    monkeypatch.setattr(cs, "fetch_and_merge", lambda tf, p, log=print: (None, "webull", True))
    monkeypatch.setattr(cs, "NOISE_FORWARD_LOG", False)

    cs.cloud_signal_thread(stop=stop, log=lambda *a, **k: None)

    # the live settle step, then the shadow legs' own offline settle step into their store
    assert len(steps) == 2
    assert steps[0]["post_close"] is True and steps[0]["paths"] == paths
    assert steps[1]["post_close"] is True and steps[1]["fetch"] is False
    assert steps[1]["paths"] == cs.shadow_paths(paths)
    assert _hb(paths)["note"].startswith("eod settle")
    assert sleeps == [cs.EOD_SETTLE_POLL_SEC]
