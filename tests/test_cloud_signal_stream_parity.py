"""api/cloud_signal_stream.py's stream decision must be step()'s decision (2026-09-27).

_dry_run_decision (WEBULL_PAPER_TODO.md item 10) promises "the exact engine path step()
uses", but it had drifted: a flat 60-session window instead of leg_warmup_sessions(cfg)
(262 for NOISE_382), run_leg_trades with no `now`/`paths` (so no vol_prior_ranges daily
bridge -- go-live 3.8 -- and no session_in_progress pass-through -- to-do 15), and no
decide_at_close probe (to-do 16). With stream_config.json's bar_close_from_stream on, a
committed stream decision REPLACES step()'s for that bar, so the drift would have reached
real orders. Both paths now share api.cloud_signal.leg_decision_trades; these tests pin
that down with stub strategies in isolated tmp homes (no network, no live files), the key
one being PARITY: for the same frame, `now` and baseline leg state, the stream decision's
events equal the events step() emits for that bar.
"""
import copy
import datetime as _dt
import os
import types

import numpy as np
import pandas as pd
import pytest

from api import cloud_signal as cs
from api import cloud_signal_stream as css
from api import webull_stream as _wstream

DAY = "2026-09-08"                 # a Tuesday, full session: the session being traded
LEG = "PX"
ABSENT = "ABSENT"


@pytest.fixture(autouse=True)
def _reset_daily_calibration_log():
    """Same once-per-date calibration log reset tests/test_cloud_signal_vol_prior_ranges.py
    uses, so log-order never depends on test order."""
    cs._DAILY_CALIBRATION_LOG.clear()
    yield
    cs._DAILY_CALIBRATION_LOG.clear()


def _quiet(*_a, **_k):
    return None


# ── stub strategy: NOISE_1_0.py's decide-at-close bar loop, plus kwarg recording ──────────
def _stub(decisions=None, lookback=None, vpr=False, sip=False, needs_vpr=False):
    """decisions: {"YYYY-MM-DD HH:MM" of bar D: "long" | "short" | "exit"}, acted on at D's
    close and filled at D+1's open (the same loop as test_cloud_signal_decide_at_close's
    _mech_stub, minus stops); the session's last bar flattens. `vpr`/`sip` make
    run_backtest explicitly NAME vol_prior_ranges / session_in_progress (the reflection
    opt-in); `needs_vpr` makes it trade only when handed non-empty vol_prior_ranges, so a
    path that skips the bridge visibly decides differently. Every call is recorded in
    mod.calls: distinct sessions seen, vol_prior_ranges, session_in_progress."""
    decisions = decisions or {}
    mod = types.ModuleType(f"stream_parity_stub_{id(decisions)}")
    mod.STRATEGY_NAME = "STREAM_PARITY_STUB"
    mod.DEFAULT_PARAMS = {}
    mod.calls = []
    if lookback is not None:
        mod.REQUIRED_LOOKBACK_SESSIONS = lookback

    def core(opens, highs, lows, closes, day_id, index, return_trades, vpr_val, sip_val):
        o, c = np.asarray(opens, float), np.asarray(closes, float)
        did = np.asarray(day_id)
        mod.calls.append({"n_days": len(set(did.tolist())), "vpr": vpr_val, "sip": sip_val})
        if needs_vpr and not (isinstance(vpr_val, list) and vpr_val):
            return None
        n = len(c)
        log = []
        a = 0
        while a < n:
            b = a
            while b < n and did[b] == did[a]:
                b += 1
            pos, entry_px, entry_i, pend, exit_pend = 0, 0.0, -1, 0, False
            for i in range(a, b):
                is_last = i == b - 1
                dec = decisions.get(index[i].strftime("%Y-%m-%d %H:%M"))
                if exit_pend:
                    log.append((entry_i, i, (o[i] - entry_px) * pos, pos, entry_px))
                    pos, exit_pend = 0, False
                if pend and pos == 0:
                    pos, entry_px, entry_i, pend = pend, o[i], i, 0
                if pos and dec == "exit":
                    if is_last:
                        log.append((entry_i, i, (c[i] - entry_px) * pos, pos, entry_px))
                        pos = 0
                    else:
                        exit_pend = True
                if pos == 0 and not is_last and dec in ("long", "short"):
                    pend = 1 if dec == "long" else -1
                if is_last and pos:
                    log.append((entry_i, i, (c[i] - entry_px) * pos, pos, entry_px))
                    pos = 0
            a = b
        if not log:
            return None
        return {"trades": log if return_trades else None, "num_trades": len(log),
                "total_pnl": float(sum(t[2] for t in log)), "win_rate": 0, "profit_factor": 0,
                "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}

    if vpr and sip:
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                         return_trades=False, vol_prior_ranges=None, session_in_progress=ABSENT,
                         **kw):
            return core(opens, highs, lows, closes, day_id, index, return_trades,
                        vol_prior_ranges, session_in_progress)
    elif vpr:
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                         return_trades=False, vol_prior_ranges=None, **kw):
            return core(opens, highs, lows, closes, day_id, index, return_trades,
                        vol_prior_ranges, kw.get("session_in_progress", ABSENT))
    elif sip:
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                         return_trades=False, session_in_progress=ABSENT, **kw):
            return core(opens, highs, lows, closes, day_id, index, return_trades,
                        kw.get("vol_prior_ranges", ABSENT), session_in_progress)
    else:
        def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                         return_trades=False, **kw):
            return core(opens, highs, lows, closes, day_id, index, return_trades,
                        kw.get("vol_prior_ranges", ABSENT), kw.get("session_in_progress", ABSENT))
    mod.run_backtest = run_backtest
    return mod


# ── synthetic bars + isolated homes ───────────────────────────────────────────────────────
def _sessions(n, last=DAY):
    end = pd.Timestamp(last).date()
    days = cs.market_calendar.sessions_between(end - _dt.timedelta(days=int(n * 1.6) + 20), end)
    assert len(days) >= n
    return days[-n:]


def _5m_frame(days, bars_per_day=78, seed=3):
    rng = np.random.default_rng(seed)
    rows, px = [], 500.0
    for d in days:
        base = pd.Timestamp(f"{d} 09:30", tz=cs.TZ)
        for i in range(bars_per_day):
            o = px
            c = o * (1 + rng.normal(0, 0.0012))
            rows.append({"time": int((base + pd.Timedelta(minutes=5 * i)).tz_convert("UTC").timestamp()),
                         "open": o, "high": max(o, c) * (1 + abs(rng.normal(0, 0.0005))),
                         "low": min(o, c) * (1 - abs(rng.normal(0, 0.0005))), "close": c,
                         "volume": 1000.0})
            px = c
    return pd.DataFrame(rows)


def _daily_frame(df5, n_prior=12, exclude=DAY, seed=5):
    """QQQ_1d.csv's shape: one row per FINISHED session. Sessions the 5m frame covers get
    that session's exact H/L/C (5m/daily ratio 1.0, so calibration passes), plus n_prior
    daily-only sessions before it -- what the vol_prior_ranges bridge hands back."""
    rng = np.random.default_rng(seed)
    idx = pd.to_datetime(df5["time"], unit="s", utc=True).dt.tz_convert(cs.TZ)
    g = df5.assign(d=idx.dt.date).groupby("d")
    rows = []
    first = min(g.groups)
    prior = cs.market_calendar.sessions_between(first - _dt.timedelta(days=n_prior * 2 + 10),
                                                first - _dt.timedelta(days=1))[-n_prior:]
    for d in prior:
        r = 0.005 + 0.01 * rng.random()
        rows.append((d, 500.0, 500.0 * (1 + r / 2), 500.0 * (1 - r / 2), 500.0))
    for d, s in g:
        if str(d) == exclude:
            continue
        rows.append((d, float(s["open"].iloc[0]), float(s["high"].max()), float(s["low"].min()),
                     float(s["close"].iloc[-1])))
    return pd.DataFrame([{"time": int(pd.Timestamp(f"{d} 00:00", tz=cs.TZ).tz_convert("UTC").timestamp()),
                          "open": o, "high": h, "low": l, "close": c, "volume": 1.0}
                         for d, o, h, l, c in rows])


def _home(tmp_path, df5, name="home", daily=None):
    paths = cs._paths(home=str(tmp_path / name))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    df5.to_csv(cs._cache_path("5m", paths), index=False)
    if daily is not None:
        daily.to_csv(cs._cache_path("1d", paths), index=False)
    return paths


def _bar_epoch(hhmm, day=DAY):
    return int(pd.Timestamp(f"{day} {hhmm}", tz=cs.TZ).tz_convert("UTC").timestamp())


def _eff(hhmm, day=DAY):
    """The stream's own synthetic `now` for the bar starting at hhmm (its close + grace)."""
    return css._effective_now_for_bar(_bar_epoch(hhmm, day) + 300, cs.CLOSE_GRACE_SECONDS)


def _hhmms(start, end, day=DAY):
    t, stop, out = pd.Timestamp(f"{day} {start}"), pd.Timestamp(f"{day} {end}"), []
    while t <= stop:
        out.append(t.strftime("%H:%M"))
        t += pd.Timedelta(minutes=5)
    return out


def _cfg(stub, **extra):
    cfg = {"strategy": stub, "timeframe": "5m", "params": {}}
    cfg.update(extra)
    return cfg


def _seed(paths, legs, hhmm="09:30", day=DAY):
    seed = cs.step(now=_eff(hhmm, day), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in seed] == ["SEED"]


def _baseline(paths, leg=LEG):
    return copy.deepcopy(cs._load_state(paths)["legs"][leg])


def _strip(events):
    return [{k: v for k, v in e.items() if k != "emitted_at"} for e in (events or [])]


def _pre_change_dry_run_decision(leg_key, cfg, df, now_et, leg_state, bar_source, log):
    """_dry_run_decision exactly as it was before 2026-09-27 -- the reference for 'a leg
    that uses none of the new features decides exactly as before'."""
    warmup = cfg.get("warmup_sessions", cs.DEFAULT_WARMUP_SESSIONS)
    arrays = cs.closed_arrays(df, now_et, "5m", warmup)
    if arrays is None:
        return None, None
    trades = cs.run_leg_trades(cfg, arrays, leg_key=leg_key, log=log)
    leg_state_copy = copy.deepcopy(leg_state)
    max_age = cfg.get("max_entry_age_sec", 3 * cs.TIMEFRAME_SECONDS["5m"])
    events = cs._diff_leg(leg_key, trades, leg_state_copy, now_et, max_entry_age_sec=max_age,
                          bar_source=bar_source, cfg=cfg, arrays=arrays, log=log)
    return events, leg_state_copy


def _no_network(monkeypatch):
    """Records (never performs) every refresh/fetch the daily bridge or the 5m cache could
    make. Recorded, not raised: vol_prior_ranges_for_leg swallows exceptions by design, so
    a raise would pass silently."""
    calls = []
    monkeypatch.setattr(cs, "_maybe_refresh_daily_cache", lambda *a, **k: calls.append("refresh"))
    monkeypatch.setattr(cs, "fetch_and_merge_daily", lambda *a, **k: calls.append("daily"))
    monkeypatch.setattr(cs, "_fetch_yf_daily", lambda *a, **k: calls.append("yf_daily"))
    monkeypatch.setattr(cs, "fetch_and_merge", lambda *a, **k: calls.append("5m"))
    return calls


# ── (a) the history window ──────────────────────────────────────────────────────────────
def test_stream_window_is_leg_warmup_sessions_not_a_flat_60(tmp_path):
    days = _sessions(90)
    paths = _home(tmp_path, _5m_frame(days, bars_per_day=2))
    now = _eff("09:35")
    deep = _stub(lookback=70)                                  # 70 + 10 margin = 80 > 60
    cfg = _cfg(deep)
    assert cs.leg_warmup_sessions(cfg) == 80
    css._dry_run_decision(LEG, cfg, cs.historical_bars("5m", paths), now, {"trades": {}},
                          "stream", _quiet, paths=paths)
    assert deep.calls[-1]["n_days"] == 80

    _pre_change_dry_run_decision(LEG, cfg, cs.historical_bars("5m", paths), now, {"trades": {}},
                                 "stream", _quiet)
    assert deep.calls[-1]["n_days"] == 60, "the old flat window -- what this fix removes"

    for extra, want in (({"warmup_sessions": 5}, 5), ({}, cs.DEFAULT_WARMUP_SESSIONS)):
        plain = _stub()
        css._dry_run_decision(LEG, _cfg(plain, **extra), cs.historical_bars("5m", paths), now,
                              {"trades": {}}, "stream", _quiet, paths=paths)
        assert plain.calls[-1]["n_days"] == want


# ── (b) the vol_prior_ranges bridge, never touching the network ──────────────────────────
def _vpr_home(tmp_path, name="vpr", n_sessions=30, n_prior=12):
    df5 = _5m_frame(_sessions(n_sessions))
    return _home(tmp_path, df5, name, daily=_daily_frame(df5, n_prior=n_prior)), n_prior


def test_stream_hands_vol_prior_ranges_only_with_paths_and_never_fetches(tmp_path, monkeypatch):
    paths, n_prior = _vpr_home(tmp_path)
    calls = _no_network(monkeypatch)
    stub = _stub(lookback=30, vpr=True)
    cfg = _cfg(stub, warmup_sessions=5)
    df = cs.historical_bars("5m", paths)

    css._dry_run_decision(LEG, cfg, df, _eff("10:00"), {"trades": {}}, "stream", _quiet,
                          paths=paths)
    got = stub.calls[-1]["vpr"]
    assert isinstance(got, list) and len(got) == n_prior
    assert stub.calls[-1]["n_days"] == 30                       # 30+10 wanted, 30 cached

    # the SAME bridge output step() itself computes for this bar
    arrays = cs.closed_arrays(df, _eff("10:00"), "5m", cs.leg_warmup_sessions(cfg))
    assert got == cs.vol_prior_ranges_for_leg(cfg, arrays, _eff("10:00"), paths=paths,
                                              fetch=False, log=_quiet)

    css._dry_run_decision(LEG, cfg, df, _eff("10:00"), {"trades": {}}, "stream", _quiet)
    assert stub.calls[-1]["vpr"] is None, "paths=None (old callers) must skip the bridge"
    assert calls == [], "the stream path must never refresh the daily cache or fetch"


def test_handoff_and_rest_resolve_pass_their_paths_through(tmp_path, monkeypatch):
    """Integration via the real handoff/resolve halves: the stream decision and its REST
    what-if both get the bridge (and the probe), agree, and nothing fetches."""
    df5 = _5m_frame(_sessions(30))
    daily = _daily_frame(df5)
    cut = _bar_epoch("10:00")
    paths = _home(tmp_path, df5[df5["time"] < cut], "handoff", daily=daily)
    stub = _stub({f"{DAY} 10:00": "long"}, lookback=30, vpr=True, needs_vpr=True)
    legs = {LEG: _cfg(stub, warmup_sessions=5, decide_at_close=True)}
    _seed(paths, legs, "09:55")
    calls = _no_network(monkeypatch)

    row = df5[df5["time"] == cut].iloc[0]
    bar = {k: float(row[k]) for k in ("open", "high", "low", "close", "volume")}
    bar["time"] = cut
    _wstream.write_closed_bar_handoff(bar, timeframe="5m", home=paths["home"],
                                      extra={"connected": True, "fresh": True,
                                             "bars_since_connect": 3, "reconnects": 0,
                                             "published_epoch": cut + 301.5})
    now = _eff("10:00")
    css._handle_handoff_window(now, legs, paths, {"bar_close_from_stream": False}, _quiet)
    rec = css._load_shadow(paths)[LEG][str(cut)]
    assert [(e["event"], e["side"]) for e in rec["events"]] == [("ENTRY", "long")]
    assert cs.DECIDE_AT_CLOSE_TAG in rec["events"][0]["reason"]

    df5[df5["time"] <= cut].to_csv(cs._cache_path("5m", paths), index=False)   # REST lands
    logs = []
    css._resolve_pending_against_rest(now + pd.Timedelta(seconds=30), legs, paths, logs.append)
    assert any("shadow MATCH" in m for m in logs), logs
    assert all(isinstance(c["vpr"], list) and c["vpr"] for c in stub.calls[-3:])
    assert calls == []


# ── session_in_progress ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("day,want", [(DAY, True), ("2026-11-27", ABSENT)])   # full / half day
def test_stream_passes_session_in_progress_exactly_when_step_does(tmp_path, day, want):
    paths = _home(tmp_path, _5m_frame(_sessions(8, last=day)), f"sip_{day}")
    stub = _stub(sip=True)
    legs = {LEG: _cfg(stub, warmup_sessions=5)}
    _seed(paths, legs, day=day)
    for h in ("09:35", "10:00", "11:20"):
        now = _eff(h, day)
        css._dry_run_decision(LEG, legs[LEG], cs.historical_bars("5m", paths), now,
                              _baseline(paths), "stream", _quiet, paths=paths)
        stream_sip = stub.calls[-1]["sip"]
        cs.step(now=now, legs=legs, paths=paths, fetch=False)
        assert stream_sip == stub.calls[-1]["sip"] == want, h


# ── decide_at_close ───────────────────────────────────────────────────────────────────────
def test_stream_emits_the_probe_entry_at_the_decision_close_like_step(tmp_path):
    df5 = _5m_frame(_sessions(3))
    paths = _home(tmp_path, df5, "dac")
    stub = _stub({f"{DAY} 10:00": "long"})
    legs = {LEG: _cfg(stub, warmup_sessions=5, decide_at_close=True)}
    _seed(paths, legs, "09:55")

    events, _ = css._dry_run_decision(LEG, legs[LEG], cs.historical_bars("5m", paths),
                                      _eff("10:00"), _baseline(paths), None, _quiet, paths=paths)
    assert [(e["event"], e["side"]) for e in events] == [("ENTRY", "long")]
    e = events[0]
    assert e["ref_time"] == pd.Timestamp(f"{DAY} 10:05", tz=cs.TZ).isoformat()
    close_10 = float(df5.loc[df5["time"] == _bar_epoch("10:00"), "close"].iloc[0])
    assert e["ref_price"] == pytest.approx(round(close_10, 4))
    assert cs.DECIDE_AT_CLOSE_TAG in e["reason"]

    old, _ = _pre_change_dry_run_decision(LEG, legs[LEG], cs.historical_bars("5m", paths),
                                          _eff("10:00"), _baseline(paths), None, _quiet)
    assert old == [], "the pre-fix stream path only saw the entry one bar later"

    step_events = cs.step(now=_eff("10:00"), legs=legs, paths=paths, fetch=False)
    assert _strip(events) == _strip(step_events)


# ── PARITY: the stream decision IS step()'s decision, bar by bar ───────────────────────────
def _walk_parity(paths, legs, hhmms, seed_at="09:30"):
    _seed(paths, legs, seed_at)
    compared = emitted = 0
    for h in hhmms:
        now = _eff(h)
        baseline = _baseline(paths)
        stream_events, _ = css._dry_run_decision(LEG, legs[LEG], cs.historical_bars("5m", paths),
                                                 now, baseline, None, _quiet, paths=paths)
        step_events = cs.step(now=now, legs=legs, paths=paths, fetch=False)
        assert css._canonical_events(stream_events) == css._canonical_events(step_events), h
        assert _strip(stream_events) == _strip(step_events), h
        compared += 1
        emitted += len(step_events)
    return compared, emitted


DECISIONS = {f"{DAY} 10:00": "long", f"{DAY} 10:30": "exit", f"{DAY} 11:00": "short",
             f"{DAY} 11:40": "exit", f"{DAY} 12:10": "long"}


def test_parity_plain_leg(tmp_path):
    paths = _home(tmp_path, _5m_frame(_sessions(8)), "parity_plain")
    legs = {LEG: _cfg(_stub(DECISIONS), warmup_sessions=5)}
    compared, emitted = _walk_parity(paths, legs, _hhmms("09:35", "12:30"))
    assert compared == 36 and emitted == 5          # 3 ENTRY + 2 EXIT (12:15 entry still open)


def test_parity_decide_at_close_and_vol_bridge_leg(tmp_path):
    paths, _n = _vpr_home(tmp_path, "parity_dac")
    stub = _stub(DECISIONS, lookback=30, vpr=True, sip=True, needs_vpr=True)
    legs = {LEG: _cfg(stub, warmup_sessions=5, decide_at_close=True)}
    compared, emitted = _walk_parity(paths, legs, _hhmms("09:35", "12:30"))
    assert compared == 36 and emitted == 5
    assert all(isinstance(c["vpr"], list) and c["vpr"] for c in stub.calls)

    # the pre-fix path, handed the same bar, would have decided nothing (no bridge ->
    # the vol-gated stub stands down): exactly the drift this fix removes.
    paths2, _n = _vpr_home(tmp_path, "parity_dac_old")
    stub2 = _stub(DECISIONS, lookback=30, vpr=True, sip=True, needs_vpr=True)
    legs2 = {LEG: _cfg(stub2, warmup_sessions=5, decide_at_close=True)}
    _seed(paths2, legs2, "09:55")
    old, _ = _pre_change_dry_run_decision(LEG, legs2[LEG], cs.historical_bars("5m", paths2),
                                          _eff("10:00"), _baseline(paths2), None, _quiet)
    assert old == []
    new = cs.step(now=_eff("10:00"), legs=legs2, paths=paths2, fetch=False)
    assert [e["event"] for e in new] == ["ENTRY"]


# ── default unchanged: a leg using none of the features decides exactly as before ────────
def test_plain_leg_output_is_identical_to_the_pre_change_stream_path(tmp_path):
    paths = _home(tmp_path, _5m_frame(_sessions(8)), "unchanged")
    stub = _stub(DECISIONS)
    for extra in ({"warmup_sessions": 5}, {}):
        cfg = _cfg(stub, **extra)
        df = cs.historical_bars("5m", paths)
        state = {"trades": {}, "seeded": True}
        n_events = 0
        for h in _hhmms("09:35", "12:30"):
            now = _eff(h)
            new_ev, new_state = css._dry_run_decision(LEG, cfg, df, now, state, "stream", _quiet,
                                                      paths=paths)
            old_ev, old_state = _pre_change_dry_run_decision(LEG, cfg, df, now, state, "stream",
                                                             _quiet)
            assert _strip(new_ev) == _strip(old_ev), h
            assert new_state == old_state, h
            state = new_state
            n_events += len(new_ev)
        assert n_events == 5


# ── follow-up 1: the stream never sends step()'s KEEL scoring-time fallback push ────────────
def test_stream_scoring_never_pushes_the_keel_fallback(tmp_path, monkeypatch):
    """_diff_leg's `fetch` only gates the scoring-time KEEL fallback ntfy push; the stream
    must pass False (its dedupe would land on the throwaway copy, so it would repeat).
    A keel block whose state file does not exist falls back to 1.0 with a reason string,
    which is exactly the push case on the box."""
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    paths = _home(tmp_path, _5m_frame(_sessions(3)), "keel")
    keel = {"state_path": str(tmp_path / "no_such_keel_state.joblib")}
    legs = {LEG: _cfg(_stub({f"{DAY} 10:00": "long"}), warmup_sessions=5,
                      decide_at_close=True, keel=keel)}
    _seed(paths, legs, "09:55")

    events, _ = css._dry_run_decision(LEG, legs[LEG], cs.historical_bars("5m", paths),
                                      _eff("10:00"), _baseline(paths), "stream", _quiet,
                                      paths=paths)
    assert [(e["event"], e["keel_size"]) for e in events] == [("ENTRY", 1.0)]
    assert pushed == [], "the stream path must never page"

    # the old _diff_leg call (no fetch= -> True) on the same entry does page: what this guards
    arrays = cs.closed_arrays(cs.historical_bars("5m", paths), _eff("10:00"), "5m", 5)
    trades, diff_arrays = cs.leg_decision_trades(legs[LEG], arrays, LEG, "5m", _eff("10:00"),
                                                 paths, False, log=_quiet)
    base = _baseline(paths)
    cs._diff_leg(LEG, trades, base, _eff("10:00"), cfg=legs[LEG],
                 arrays=diff_arrays, log=_quiet)
    # WEBULL PUSH PLAN 10-07: the plain note on the phone, the reason on the leg's record
    assert len(pushed) == 1 and "KEEL sizing model could not be read" in pushed[0]
    assert base["keel_alert"]["last_reason"] == "keel state unavailable"


# ── follow-up 2: first bar of the day vs the not-yet-refreshed daily cache ────────────────
def test_daily_cache_refresh_due_is_exactly_the_refresh_gate(tmp_path, monkeypatch):
    """cs._daily_cache_refresh_due must say True exactly when _maybe_refresh_daily_cache
    would fetch -- the stream's hold-back rule reuses it, so the two cannot drift."""
    fetched = []
    monkeypatch.setattr(cs, "fetch_and_merge_daily", lambda *a, **k: fetched.append(1))
    df5 = _5m_frame(_sessions(10))
    daily = _daily_frame(df5)
    dates = pd.to_datetime(daily["time"], unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date
    now = _eff("10:00")
    needed = cs._last_completed_session_date(now)
    stale = daily[dates < needed]
    same_day = pd.Timestamp(f"{DAY} 09:31", tz=cs.TZ).timestamp()
    cases = [("fresh", daily, None, False), ("stale", stale, None, True),
             ("missing", None, None, True), ("stale, tried today", stale, same_day, False)]
    for name, frame, mtime, want in cases:
        paths = _home(tmp_path, df5, name.replace(",", "").replace(" ", "_"), daily=frame)
        if mtime is not None:
            os.utime(cs._cache_path("1d", paths), (mtime, mtime))
        fetched.clear()
        assert cs._daily_cache_refresh_due(now, paths) is want, name
        cs._maybe_refresh_daily_cache(now, paths, log=_quiet)
        assert bool(fetched) is want, name


def test_handoff_leaves_a_bridge_legs_bar_to_step_while_the_daily_cache_is_due(tmp_path,
                                                                               monkeypatch):
    """run_stream_aware_step runs the stream BEFORE step(), and step() refreshes QQQ_1d.csv
    only when it processes a new bar -- so on the first bar of the day the stream would read
    a cache missing D-1 while step() and the REST what-if read the refreshed one. That bar
    is left to classic step() for a bridge leg (logged once), never for a plain leg, and the
    stream decides again as soon as the cache holds the last finished session."""
    df5 = _5m_frame(_sessions(30))
    daily = _daily_frame(df5)
    cut = _bar_epoch("10:00")
    now = _eff("10:00")
    dates = pd.to_datetime(daily["time"], unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date
    stale = daily[dates < cs._last_completed_session_date(now)]
    paths = _home(tmp_path, df5[df5["time"] < cut], "gate", daily=stale)
    bridge = _stub({f"{DAY} 10:00": "long"}, lookback=30, vpr=True)
    plain = _stub({f"{DAY} 10:00": "long"})
    legs = {LEG: _cfg(bridge, warmup_sessions=5, decide_at_close=True),
            "PLAIN": _cfg(plain, warmup_sessions=5, decide_at_close=True)}
    seed = cs.step(now=_eff("09:55"), legs=legs, paths=paths, fetch=False)
    assert sorted(e["event"] for e in seed) == ["SEED", "SEED"]
    calls = _no_network(monkeypatch)
    css._DAILY_GATE_LOGGED.clear()

    row = df5[df5["time"] == cut].iloc[0]
    bar = {k: float(row[k]) for k in ("open", "high", "low", "close", "volume")}
    bar["time"] = cut
    _wstream.write_closed_bar_handoff(bar, timeframe="5m", home=paths["home"],
                                      extra={"connected": True, "fresh": True,
                                             "bars_since_connect": 3, "reconnects": 0,
                                             "published_epoch": cut + 301.5})
    logs = []
    for tick in (0, 1):                                       # two ~1s hand-off ticks
        css._handle_handoff_window(now + pd.Timedelta(seconds=tick), legs, paths,
                                   {"bar_close_from_stream": False}, logs.append)
    shadow = css._load_shadow(paths)
    assert str(cut) not in (shadow.get(LEG) or {}), "bridge leg must be left to step()"
    assert [(e["event"], e["side"]) for e in shadow["PLAIN"][str(cut)]["events"]] == \
        [("ENTRY", "long")], "a plain leg is never held back"
    held = [m for m in logs if "no stream decision" in m]
    assert len(held) == 1 and LEG in held[0], logs

    daily.to_csv(cs._cache_path("1d", paths), index=False)   # step()'s refresh lands
    css._handle_handoff_window(now + pd.Timedelta(seconds=2), legs, paths,
                               {"bar_close_from_stream": False}, logs.append)
    rec = css._load_shadow(paths)[LEG][str(cut)]
    assert [(e["event"], e["side"]) for e in rec["events"]] == [("ENTRY", "long")]
    assert calls == [], "the hold-back check itself must never fetch"
