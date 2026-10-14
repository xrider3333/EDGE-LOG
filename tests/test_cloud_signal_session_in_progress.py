"""api/cloud_signal.py -- the `session_in_progress` pass-through (WEBULL_PAPER_TODO.md
item 15). See augur_strategies/ORB_3_6.py's own "LIVE-ENGINE ADDITION" note and
tests/test_orb_session_in_progress.py for the strategy-side half of this fix.

GENERIC BY DESIGN: this module never mentions ORB by name for this feature.
_leg_accepts_session_in_progress detects support purely by reflecting on whatever
run_backtest a leg's cfg["strategy"] resolves to, and _session_in_progress decides
purely off `arrays`' own last bar date vs `now` and the market calendar -- so every
test below uses a synthetic stub strategy, never a real one, to prove the mechanism
itself rather than ORB's particular fix.
"""
import datetime
import types

import pandas as pd
import pytest

import api.cloud_signal as cs


# ── _leg_accepts_session_in_progress: reflection, explicit declaration only ─────────────
def test_explicit_declaration_is_detected():
    mod = types.ModuleType("stub_declares_sip")
    mod.run_backtest = lambda o, h, l, c, day_id=None, session_in_progress=False, **kw: None
    assert cs._leg_accepts_session_in_progress(mod) is True


def test_bare_kwargs_catchall_does_not_count_as_support():
    """Unlike volumes/day_id (conventions every plugin tolerates via **kw), a bare
    catch-all must NOT be treated as opting in to a live-only correctness decision."""
    mod = types.ModuleType("stub_catchall_only")
    mod.run_backtest = lambda o, h, l, c, day_id=None, **kw: None
    assert cs._leg_accepts_session_in_progress(mod) is False


def test_no_declaration_at_all_is_not_support():
    mod = types.ModuleType("stub_plain")
    mod.run_backtest = lambda o, h, l, c, day_id=None: None
    assert cs._leg_accepts_session_in_progress(mod) is False


def test_unresolvable_strategy_string_is_best_effort_false():
    assert cs._leg_accepts_session_in_progress("NOT_A_REAL_FILE_xyz.py") is False


# ── _session_in_progress: last-session-date-vs-today + calendar check ───────────────────
def _arrays_ending(last_ts):
    idx = pd.DatetimeIndex([last_ts - pd.Timedelta(minutes=5), last_ts])
    return {"index": idx}


def test_true_when_last_session_is_today_and_not_a_half_day():
    now = pd.Timestamp("2026-09-18 10:15:00", tz=cs.TZ)
    arrays = _arrays_ending(pd.Timestamp("2026-09-18 10:10:00", tz=cs.TZ))
    assert cs._session_in_progress(arrays, now.to_pydatetime()) is True


def test_false_when_last_session_is_not_today():
    now = pd.Timestamp("2026-09-18 10:15:00", tz=cs.TZ)
    arrays = _arrays_ending(pd.Timestamp("2026-09-17 15:55:00", tz=cs.TZ))   # yesterday
    assert cs._session_in_progress(arrays, now.to_pydatetime()) is False


def test_false_on_a_real_recognised_half_day():
    """A GENUINE half day (day after Thanksgiving) must NOT be exempted even though the
    last session shares today's date -- only skip_holidays' own length test, unchanged,
    should fire there."""
    now = pd.Timestamp("2026-11-27 10:15:00", tz=cs.TZ)
    arrays = _arrays_ending(pd.Timestamp("2026-11-27 10:10:00", tz=cs.TZ))
    assert cs._session_in_progress(arrays, now.to_pydatetime()) is False


def test_false_and_never_raises_on_missing_or_bad_inputs():
    assert cs._session_in_progress({"index": pd.DatetimeIndex([])}, datetime.datetime.now()) is False
    assert cs._session_in_progress({}, datetime.datetime.now()) is False
    arrays = _arrays_ending(pd.Timestamp("2026-09-18 10:10:00", tz=cs.TZ))
    assert cs._session_in_progress(arrays, None) is False


# ── run_leg_trades: the actual pass-through into a leg's params ─────────────────────────
def _spy_stub(declares_param=True):
    seen = {}
    if declares_param:
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                         session_in_progress=False, return_trades=False, **kw):
            seen["session_in_progress"] = session_in_progress
            seen["kwargs"] = dict(kw)
            return {"trades": [], "num_trades": 0, "total_pnl": 0, "win_rate": 0,
                   "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}
    else:
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                         return_trades=False, **kw):
            seen["kwargs"] = dict(kw)
            seen["session_in_progress" ] = ("session_in_progress" in kw)
            return {"trades": [], "num_trades": 0, "total_pnl": 0, "win_rate": 0,
                   "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}
    mod = types.ModuleType(f"stub_spy_{declares_param}")
    mod.run_backtest = run_backtest
    return mod, seen


def _today_arrays():
    now = pd.Timestamp("2026-09-18 10:15:00", tz=cs.TZ)
    idx = pd.DatetimeIndex([now - pd.Timedelta(minutes=5), now - pd.Timedelta(minutes=0)])
    arrays = {"index": idx, "open": [100.0, 100.5], "high": [100.5, 101.0],
             "low": [99.5, 100.0], "close": [100.0, 100.5], "day_id": [0, 0]}
    return arrays, now


def test_run_leg_trades_sets_the_flag_when_supported_and_last_session_is_today():
    mod, seen = _spy_stub(declares_param=True)
    arrays, now = _today_arrays()
    cs.run_leg_trades({"strategy": mod, "params": {}}, arrays, now=now.to_pydatetime())
    assert seen["session_in_progress"] is True


def test_run_leg_trades_leaves_the_flag_off_when_now_is_omitted():
    """No `now` (every pre-existing call site) must reproduce today's behaviour exactly
    -- cfg["params"] untouched, the leg's own default used."""
    mod, seen = _spy_stub(declares_param=True)
    arrays, _ = _today_arrays()
    cs.run_leg_trades({"strategy": mod, "params": {}}, arrays)   # now defaults to None
    assert seen["session_in_progress"] is False


def test_run_leg_trades_leaves_the_flag_off_when_last_session_is_not_today():
    mod, seen = _spy_stub(declares_param=True)
    arrays, now = _today_arrays()
    stale_now = now + pd.Timedelta(days=1)
    cs.run_leg_trades({"strategy": mod, "params": {}}, arrays, now=stale_now.to_pydatetime())
    assert seen["session_in_progress"] is False


def test_run_leg_trades_never_hands_the_flag_to_a_strategy_that_did_not_opt_in():
    mod, seen = _spy_stub(declares_param=False)
    arrays, now = _today_arrays()
    cs.run_leg_trades({"strategy": mod, "params": {}}, arrays, now=now.to_pydatetime())
    assert seen["session_in_progress"] is False   # never appeared in kw at all


def test_run_leg_trades_does_not_mutate_cfg_params():
    """A per-call copy only -- cfg["params"] itself must be the SAME dict, untouched,
    so the next call (a different `now`) recomputes the flag fresh rather than
    inheriting a stale True from a previous tick."""
    mod, seen = _spy_stub(declares_param=True)
    params = {}
    cfg = {"strategy": mod, "params": params}
    arrays, now = _today_arrays()
    cs.run_leg_trades(cfg, arrays, now=now.to_pydatetime())
    assert params == {}
    assert cfg["params"] is params


# ── step(): end-to-end, a leg that opts in gets the flag on its own live tick ────────────
def test_step_passes_now_through_to_a_session_in_progress_leg(tmp_path):
    mod, seen = _spy_stub(declares_param=True)
    base = pd.Timestamp("2026-09-18 09:30:00", tz=cs.TZ)
    times = [base + pd.Timedelta(minutes=5 * i) for i in range(4)]
    epoch = [int(t.tz_convert("UTC").timestamp()) for t in times]
    epoch_df = pd.DataFrame({
        "time": epoch, "open": [100.0] * 4, "high": [100.5] * 4,
        "low": [99.5] * 4, "close": [100.0] * 4, "volume": [1000.0] * 4,
    })
    paths = cs._paths(home=str(tmp_path / "sip_home"))
    import os
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(cs._cache_path("5m", paths), index=False)

    legs = {"SIP": {"strategy": mod, "timeframe": "5m", "params": {}, "warmup_sessions": 5}}
    now = (times[-1] + pd.Timedelta(minutes=1)).to_pydatetime()
    cs.step(now=now, legs=legs, paths=paths, fetch=False)

    assert seen.get("session_in_progress") is True


# ════════════════════════════════════════════════════════════════════════════════════════
# HALF-DAY RULE PINNED (owner 2026-10-14 via MANAGER #162/#163: "make sure it does not happen
# again"). The tests above prove the mechanism on stubs; the ones below pin it to the SHIPPED
# legs and to the real ORB_R6 config, so the 09-21..09-25 drops (five ORB entries recorded
# "late" because today's still-building session read as a half day until ~14:05) cannot
# come back through a new leg, a new strategy file or a cfg edit:
#   - every CROWN_LEGS / SHADOW_LEGS leg whose strategy runs the half-day skip accepts the
#     flag (and so no shipped leg is refused);
#   - the real ORB_R6 config, on a synthetic 60-session cache with today cut short, emits its
#     09:40 breakout at 09:50 -- and does not without the flag (the rule really fires);
#   - a LIVE leg whose strategy runs the skip but cannot take the flag is REFUSED loudly (a
#     log line, the not-ready page once a day), never silently run; a shadow leg runs anyway.
# ════════════════════════════════════════════════════════════════════════════════════════
import os

from api import market_calendar
from api import ntfy_push


def _shipped_legs():
    out = dict(cs.CROWN_LEGS)
    out.update(cs.SHADOW_LEGS)
    assert len(out) == len(cs.CROWN_LEGS) + len(cs.SHADOW_LEGS), "a key in both dicts"
    return out


def test_every_skip_holidays_leg_accepts_session_in_progress():
    ruled = {k for k, cfg in _shipped_legs().items() if cs._leg_has_half_day_rule(cfg)}
    assert "ORB_R6" in ruled, "the leg the rule bit must be detected, or this test pins nothing"
    for key in sorted(ruled):
        cfg = _shipped_legs()[key]
        assert cs._leg_accepts_session_in_progress(cfg["strategy"]) is True, (
            f"{key} ({cfg['strategy']}) skips short sessions as half days but cannot be told "
            f"today's session is still in progress -- its morning entries would be dropped late")


def test_no_shipped_leg_is_refused_by_the_half_day_guard():
    for key, cfg in _shipped_legs().items():
        assert cs.half_day_rule_refusal(cfg) is None, key


def test_half_day_rule_detection_on_the_shipped_files():
    """ORB_R6: skip_holidays=True in ORB_314 itself. The NOISE legs: NOISE_1_8_CT304*.py pin
    skip_holidays False in _FROZEN (their base file has the rule; they run it off). DIP:
    never through run_leg_trades. ENGU-Q: no such rule."""
    assert cs._leg_has_half_day_rule(cs.CROWN_LEGS["ORB_R6"]) is True
    assert cs._leg_has_half_day_rule(cs.CROWN_LEGS["NOISE_382"]) is False
    assert cs._leg_has_half_day_rule(cs.SHADOW_LEGS["NOISE_422_PLAIN"]) is False
    assert cs._leg_has_half_day_rule(cs.CROWN_LEGS["DIP_424"]) is False
    assert cs._leg_has_half_day_rule(cs.SHADOW_LEGS["ENGUQ_335"]) is False
    # the source the cfg does not name: the strategy's own default
    orb = cs.CROWN_LEGS["ORB_R6"]
    no_key = dict(orb, params={k: v for k, v in orb["params"].items() if k != "skip_holidays"})
    assert cs._leg_has_half_day_rule(no_key) is True        # ORB_3_6.run_backtest's default
    off = dict(no_key, params=dict(no_key["params"], skip_holidays=False))
    assert cs._leg_has_half_day_rule(off) is False


# ── the real ORB_R6 config end to end ─────────────────────────────────────────────────────
TODAY = datetime.date(2026, 10, 14)          # a normal full session (not an early close)


def _sessions_before(day, n):
    out, d = [], day - datetime.timedelta(days=1)
    while len(out) < n:
        if market_calendar.is_session(d):
            out.append(d)
        d -= datetime.timedelta(days=1)
    return out[::-1]


def _epoch(day, hhmm):
    return int(pd.Timestamp(f"{day} {hhmm}", tz=cs.TZ).tz_convert("UTC").timestamp())


def _orb_cache(paths, n_hist=62):
    """n_hist quiet full sessions (78 bars, a 1.00 range, closes flat at the open: no
    breakout), then TODAY cut at 10:00 -- an opening range 99.50-100.60 that closes up on
    its second bar (First-candle dir: long), and a 09:40 bar closing at 101.00, past
    100.60 + 0.25 x 1.10 = 100.875. Volume flat: the volume-pace and vol-regime filters
    both pass on the trailing sessions."""
    rows = []
    for d in _sessions_before(TODAY, n_hist):
        t0 = _epoch(d, "09:30")
        for b in range(78):
            rows.append((t0 + 300 * b, 100.0, 100.5, 99.5, 100.0, 1000.0))
    today = [("09:30", 100.0, 100.5, 99.5, 100.2), ("09:35", 100.2, 100.6, 100.0, 100.4),
             ("09:40", 100.4, 101.2, 100.3, 101.0), ("09:45", 101.0, 101.2, 100.8, 101.1),
             ("09:50", 101.1, 101.3, 100.9, 101.2), ("09:55", 101.2, 101.4, 101.0, 101.3)]
    for hhmm, o, h, l, c in today:
        rows.append((_epoch(TODAY, hhmm), o, h, l, c, 1000.0))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]).to_csv(
        cs._cache_path("5m", paths), index=False)


def _at(hh, mm, ss=10):
    return pd.Timestamp(f"{TODAY} {hh:02d}:{mm:02d}:{ss:02d}", tz=cs.TZ).to_pydatetime()


def _orb_morning(tmp_path, name):
    paths = cs._paths(home=str(tmp_path / name))
    _orb_cache(paths)
    legs = {"ORB_R6": cs.CROWN_LEGS["ORB_R6"]}            # the real config, untouched
    seed = cs.step(now=_at(9, 31, 0), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in seed] == ["SEED"]
    assert "cold start: absorbed 0 historical trade(s)" in seed[0]["reason"]
    # 09:50:30: the 09:30..09:45 bars have closed (four bars -- ORB needs more than or_bars+1)
    events = cs.step(now=_at(9, 50, 30), legs=legs, paths=paths, fetch=False)
    return events, cs._load_state(paths)["legs"]["ORB_R6"]


def test_orb_r6_morning_entry_emits_on_in_progress_session(tmp_path):
    events, leg_state = _orb_morning(tmp_path, "orb_live")
    assert [e["event"] for e in events] == ["ENTRY"]
    (e,) = events
    assert e["leg"] == "ORB_R6" and e["side"] == "long"
    assert str(e["ref_time"]).startswith(f"{TODAY}T09:40:00") and float(e["ref_price"]) == 101.0
    assert int(leg_state.get("late_skipped", 0)) == 0
    assert all(not r.get("skipped") for r in leg_state["trades"].values())


def test_orb_r6_morning_entry_is_gone_without_the_flag(tmp_path, monkeypatch):
    """The control: the same tape with the pass-through off is the 09-21 bug -- today's four
    bars are under 70% of the median session, so ORB skips the day as a half day. Proves the
    test above exercises the rule, not a tape on which it never fires."""
    monkeypatch.setattr(cs, "_session_in_progress", lambda arrays, now: False)
    events, leg_state = _orb_morning(tmp_path, "orb_control")
    assert events == []
    assert leg_state["trades"] == {}


# ── the guard: a live leg that cannot take the flag is refused, loudly ───────────────────
def _skip_holidays_stub(declares_flag=False):
    """Runs a half-day skip (skip_holidays=True by default) and enters at the last session's
    09:35 bar; with declares_flag it also names session_in_progress. Returns (module, calls)."""
    calls = []

    def _body(index, closes, return_trades):
        calls.append(1)
        last_day = index[-1].date()
        out = [(i, len(closes) - 1, 0.0, 1, float(closes[i])) for i, ts in enumerate(index)
               if ts.date() == last_day and ts.strftime("%H:%M") == "09:35"]
        return {"trades": out if return_trades else None, "num_trades": len(out),
                "total_pnl": 0.0, "win_rate": 0, "profit_factor": 0, "max_drawdown": 0,
                "avg_pnl": 0, "wins": 0, "losses": 0}

    if declares_flag:
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                         skip_holidays=True, session_in_progress=False, return_trades=False,
                         **kw):
            return _body(index, closes, return_trades)
    else:
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                         skip_holidays=True, return_trades=False, **kw):
            return _body(index, closes, return_trades)
    mod = types.ModuleType(f"stub_half_day_{declares_flag}")
    mod.DEFAULT_PARAMS = {}
    mod.run_backtest = run_backtest
    return mod, calls


def _flat_bars(days, last_until):
    rows = []
    for d in days:
        t, stop = _epoch(d, "09:30"), _epoch(d, last_until if d == days[-1] else "16:00")
        while t < stop:
            rows.append((t, 600.0, 600.5, 599.5, 600.0, 1000.0))
            t += 300
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def test_the_guard_reads_each_shape():
    mod, _ = _skip_holidays_stub(declares_flag=False)
    live = {"strategy": mod, "timeframe": "5m", "params": {}}
    why = cs.half_day_rule_refusal(live)
    assert why and "session_in_progress" in why and "half day" in why
    assert cs.half_day_rule_refusal(dict(live, params={"skip_holidays": False})) is None
    ok, _ = _skip_holidays_stub(declares_flag=True)
    assert cs.half_day_rule_refusal(dict(live, strategy=ok)) is None


def test_a_live_leg_whose_strategy_cannot_take_the_flag_is_refused_loudly(
        tmp_path, monkeypatch, capsys):
    mod, calls = _skip_holidays_stub(declares_flag=False)
    legs = {"HDSTUB": {"strategy": mod, "timeframe": "5m", "params": {}, "warmup_sessions": 5}}
    paths = cs._paths(home=str(tmp_path / "refused"))
    os.makedirs(paths["state_dir"], exist_ok=True)
    days = _sessions_before(TODAY, 3) + [TODAY]
    pushes = []

    def fake_push(msg, title, priority="high", paths=None, log=print):
        pushes.append({"title": title, "message": msg, "priority": priority})
        return "background"

    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    monkeypatch.setattr(cs, "_engine_push_background", fake_push)
    monkeypatch.setattr(cs, "_HALF_DAY_REFUSAL_LOGGED", {})
    monkeypatch.setattr(cs, "_LIVE_NOT_READY_NOTED", {})

    for until, now in (("09:50", _at(9, 50)), ("09:55", _at(9, 55))):   # two new bars
        frame = _flat_bars(days, until)
        monkeypatch.setattr(cs, "fetch_and_merge",
                            lambda tf, paths=None, log=print, _f=frame: (_f, "webull", True))
        warnings = {}
        assert cs.step(now=now, legs=legs, paths=paths, fetch=True, warnings=warnings) == []
        assert warnings["legs_not_ready"]["HDSTUB"]["reason"] == "half_day_rule"

    assert calls == [], "a refused leg's strategy is never run"
    out = capsys.readouterr().out
    assert out.count("HDSTUB: REFUSED live") == 1, "one line a day, not one per bar"
    assert "does not accept session_in_progress" in out
    assert len(pushes) == 1, "the not-ready page, once a day"
    note = pushes[0]
    assert note["title"] == "HDSTUB: not trading" and note["priority"] == "high"
    assert ntfy_push.lint(note) == []
    assert "half day" in note["message"]
    st = cs._load_state(paths)["legs"]["HDSTUB"]
    assert not st.get("seeded") and st.get("trades") == {}, "no SEED, no record: it never ran"


def test_a_shadow_leg_with_the_same_strategy_runs_with_a_warning(tmp_path, monkeypatch, capsys):
    mod, calls = _skip_holidays_stub(declares_flag=False)
    legs = {"HDSHADOW": {"strategy": mod, "timeframe": "5m", "params": {}, "warmup_sessions": 5,
                         "shadow": True}}
    paths = cs._paths(home=str(tmp_path / "shadow"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    _flat_bars(_sessions_before(TODAY, 3) + [TODAY], "09:50").to_csv(
        cs._cache_path("5m", paths), index=False)
    monkeypatch.setattr(cs, "_HALF_DAY_REFUSAL_LOGGED", {})
    events = cs.step(now=_at(9, 50), legs=legs, paths=paths, fetch=False)
    # it ran: a SEED (a shadow seed may also carry its open trade as an ENTRY)
    assert events and events[0]["event"] == "SEED" and calls
    assert "HDSHADOW: WARNING (shadow leg, run anyway" in capsys.readouterr().out


def test_the_stream_path_makes_no_decision_for_a_refused_leg():
    from api import cloud_signal_stream as stream
    mod, calls = _skip_holidays_stub(declares_flag=False)
    cfg = {"strategy": mod, "timeframe": "5m", "params": {}, "warmup_sessions": 5}
    df = _flat_bars(_sessions_before(TODAY, 3) + [TODAY], "09:50")
    events, mutated = stream._dry_run_decision("HDSTUB", cfg, df, _at(9, 50),
                                               {"trades": {}, "seeded": True}, "stream",
                                               lambda *a, **k: None)
    assert events is None and mutated is None and calls == []
