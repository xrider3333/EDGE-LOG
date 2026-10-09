"""FEED HEALTH on the signal engine's heartbeat (sweep 2026-10-05, findings 6 + 15).

Before: the heartbeat said ok=True every tick whether or not a new bar had arrived, so a frozen
Webull tail produced no ENTRY or EXIT while everything looked healthy, and a fall-back to
yfinance was a log line. Now the heartbeat carries newest_closed_bar_et, bar_age_s, bars_due,
bars_missing and a stalled verdict (ok keeps its meaning -- see api/qqq_exec.py
_check_feed_engine), and the engine pushes once per episode: bars stopped for more than 11 min
in session, or the live 5m bars on yfinance for 3+ fetches in a row (each with a recovery
push). No network: steps run offline (fetch=False) on a temp bar cache, and the push is a
recorder.

EVERY LIVE TIMEFRAME (2026-10-09, ENGU-Q back on the book on 1m bars): the 1m feed is watched
too -- a fetch tick with the 1m bars from yfinance counts toward "backup prices", and a frozen
1m tail pages "prices stopped" once it has been silent for the 5m's own 660 s (not at its own
180 s verdict, so a 1m tail a few bars behind never flaps a page). The heartbeat keeps its 5m
top-level figures and adds stalled_timeframes + feed_by_timeframe.
"""
import datetime
import json
import os
import threading
import types

import pandas as pd
import pytest

import api.cloud_signal as cs

ET = cs._zi(cs.TZ)
DAY = "2026-10-05"            # a Monday


def at(hh, mm, ss=0, day=DAY):
    y, mo, d = (int(x) for x in day.split("-"))
    return datetime.datetime(y, mo, d, hh, mm, ss, tzinfo=ET)


def bars(day, first="09:30", last="10:00", prev_day=None):
    """5m bars from `first` to `last` (bar START times) on `day`, optionally with the
    previous session's 15:55 bar in front."""
    times = list(pd.date_range(pd.Timestamp(f"{day} {first}:00", tz=cs.TZ),
                               pd.Timestamp(f"{day} {last}:00", tz=cs.TZ), freq="5min"))
    if prev_day:
        times = [pd.Timestamp(f"{prev_day} 15:55:00", tz=cs.TZ)] + times
    ep = [int(t.tz_convert("UTC").timestamp()) for t in times]
    n = len(ep)
    return pd.DataFrame({"time": ep, "open": [600.0] * n, "high": [601.0] * n,
                         "low": [599.0] * n, "close": [600.5] * n, "volume": [1000.0] * n})


# -- bar_health (pure) --------------------------------------------------------------------------
def test_frozen_tail_reads_stalled_with_the_missing_bars():
    h = cs.bar_health(bars(DAY, last="10:00"), at(10, 20), "5m")
    assert h["newest_closed_bar_et"].startswith("2026-10-05T10:00")
    assert h["bar_age_s"] == 900.0                      # closed 10:05, now 10:20
    assert h["bars_due"] == 9 and h["bars_missing"] == 2   # 09:30..10:10 due, 10:05+10:10 gone
    assert h["stalled"] is True


def test_a_normal_lag_is_not_a_stall():
    h = cs.bar_health(bars(DAY, last="10:00"), at(10, 10, 30), "5m")
    assert h["bar_age_s"] == 330.0 and h["stalled"] is False
    assert h["bars_missing"] == 1, "the 10:05 bar is 25 s late: counted, not a stall"


def test_before_the_first_bar_is_due_nothing_is_stalled_then_0941_is():
    frame = bars("2026-10-02", first="15:55", last="15:55")   # only Friday's last bar
    early = cs.bar_health(frame, at(9, 34), "5m")
    assert early["bars_due"] == 0 and early["stalled"] is False
    assert cs.bar_health(frame, at(9, 40, 59), "5m")["stalled"] is False
    late = cs.bar_health(frame, at(9, 41, 30), "5m")
    assert late["stalled"] is True and late["bars_missing"] == late["bars_due"] == 2


def test_off_session_never_stalls():
    frame = bars("2026-10-02", last="15:55")
    sat = cs.bar_health(frame, at(12, 0, day="2026-10-03"), "5m")
    assert sat["bars_due"] == 0 and sat["stalled"] is False
    after = cs.bar_health(frame, at(17, 0, day="2026-10-02"), "5m")
    assert after["stalled"] is False and after["bars_missing"] == 0


def test_step_reports_bar_health_through_warnings(tmp_path):
    paths = cs._paths(home=str(tmp_path / "home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    bars(DAY, last="10:00").to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    w = {}
    cs.step(now=at(10, 20), legs=_legs(), paths=paths, fetch=False, warnings=w,
            bar_sources={"5m": "webull"})
    h = w["bar_health"]["5m"]
    assert h["stalled"] is True and h["source"] == "webull" and h["fetched"] is False


# -- _feed_health: heartbeat fields + one push per episode ------------------------------------
@pytest.fixture
def pushes(monkeypatch):
    out = []

    def rec(msg, title, priority="high", paths=None, log=print):
        out.append({"msg": msg, "title": title, "priority": priority})
        return True
    monkeypatch.setattr(cs, "_engine_push", rec)
    return out


def _lint(p):
    """Every engine push is a plain() note (api/ntfy_push PLAIN FORMAT) and passes lint()."""
    from api import ntfy_push
    return ntfy_push.lint({"title": p["title"], "message": p["msg"], "priority": p["priority"]})


def _legs():
    mod = types.ModuleType("feed_health_stub")
    mod.STRATEGY_NAME = "STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(*a, return_trades=False, **kw):
        return {"trades": [] if return_trades else None, "num_trades": 0, "total_pnl": 0.0,
                "win_rate": 0, "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0,
                "wins": 0, "losses": 0}
    mod.run_backtest = run_backtest
    return {"ORB_R6": {"strategy": mod, "timeframe": "5m", "params": {}, "warmup_sessions": 3}}


def _tick(paths, now, source=None, fetched=False):
    """One in-session live tick as the thread does it: step -> _feed_health -> heartbeat."""
    w = {}
    cs.step(now=now, legs=_legs(), paths=paths, fetch=False, warnings=w,
            bar_sources={"5m": source} if source else None)
    if fetched:
        w["bar_health"]["5m"]["fetched"] = True
    health = cs._feed_health(now, w, paths, log=lambda *a: None)
    cs._write_heartbeat(paths, ok=True, note="x", health=health)
    with open(paths["heartbeat_path"], encoding="utf-8") as f:
        return json.load(f)


def _cache(paths, frame):
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    frame.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)


def test_heartbeat_goes_stalled_during_a_frozen_tail_and_recovers(tmp_path, pushes):
    paths = cs._paths(home=str(tmp_path / "home"))
    _cache(paths, bars(DAY, last="10:00", prev_day="2026-10-02"))
    hb = _tick(paths, at(10, 6))
    assert hb["ok"] is True and hb["verdict"] == "ok" and hb["stalled"] is False
    assert hb["newest_closed_bar_et"].startswith("2026-10-05T10:00")
    # the tail freezes: every tick from 10:16 on is stalled, ok stays True, ONE push
    for m in range(16, 40, 1):
        hb = _tick(paths, at(10, m, 10))
    assert hb["ok"] is True, "ok keeps its meaning (the step ran)"
    assert hb["verdict"] == "stalled" and hb["stalled"] is True
    assert hb["bars_missing"] >= 5 and hb["bar_age_s"] > 660
    assert [p["title"] for p in pushes] == ["QQQ book: prices stopped"]
    assert pushes[0]["priority"] == "high" and _lint(pushes[0]) == []
    # the 10:00 ET bar closed 10:05 ET = 07:05 on the owner's clock (America/Phoenix)
    assert "since 07:05." in pushes[0]["msg"]
    assert pushes[0]["msg"].startswith("Trading: AFFECTED - the QQQ book cannot enter or exit")
    # bars arrive again: verdict ok, one low back-to-normal push
    _cache(paths, bars(DAY, last="10:35", prev_day="2026-10-02"))
    hb = _tick(paths, at(10, 41))
    assert hb["verdict"] == "ok" and hb["stalled"] is False and hb["bars_missing"] == 0
    assert [p["title"] for p in pushes] == ["QQQ book: prices stopped", "QQQ book: OK"]
    assert pushes[1]["priority"] == "low" and _lint(pushes[1]) == []
    assert "Back to normal (was: prices stopped for about" in pushes[1]["msg"]
    for m in range(42, 50):
        _tick(paths, at(10, m))
    assert len(pushes) == 2


def test_a_restart_mid_stall_does_not_page_again(tmp_path, pushes):
    paths = cs._paths(home=str(tmp_path / "home"))
    _cache(paths, bars(DAY, last="10:00"))
    _tick(paths, at(10, 20))
    assert len(pushes) == 1
    # a new process: nothing in memory, the episode is in feed_alerts.json
    _tick(paths, at(10, 25))
    assert len(pushes) == 1
    assert json.load(open(os.path.join(paths["state_dir"], "feed_alerts.json")))["stall"]["pushed"]


def test_a_stall_left_open_overnight_closes_quietly_at_the_day_change(tmp_path, pushes):
    paths = cs._paths(home=str(tmp_path / "home"))
    _cache(paths, bars(DAY, last="10:00"))
    _tick(paths, at(10, 20))
    _cache(paths, bars("2026-10-06", last="09:35", prev_day=DAY))
    hb = _tick(paths, at(9, 41, day="2026-10-06"))
    assert hb["verdict"] == "ok"
    assert len(pushes) == 1, "no 'bars back' push for yesterday's episode"


def test_yfinance_for_three_fetches_pushes_once_then_webull_recovers(tmp_path, pushes, monkeypatch):
    paths = cs._paths(home=str(tmp_path / "home"))
    _cache(paths, bars(DAY, last="10:00"))
    monkeypatch.setitem(cs._WEBULL_LAST_ERR, "text", "ReadTimeout: read timeout=25")
    _tick(paths, at(10, 6), source="yfinance", fetched=True)
    _tick(paths, at(10, 6, 20), source="yfinance")               # a fast tick: not counted
    hb = _tick(paths, at(10, 6, 30), source="yfinance", fetched=True)
    assert pushes == [] and hb["yf_fallback_streak"] == 2
    hb = _tick(paths, at(10, 7), source="yfinance", fetched=True)
    assert [p["title"] for p in pushes] == ["QQQ book: backup prices"]
    assert pushes[0]["priority"] == "high" and _lint(pushes[0]) == []
    assert "ReadTimeout" not in pushes[0]["msg"], "the Webull error is log detail, not phone text"
    assert hb["bar_source"] == "yfinance" and hb["yf_fallback_streak"] == 3
    for s in range(5):
        _tick(paths, at(10, 8, s * 10), source="yfinance", fetched=True)
    assert len(pushes) == 1, "one push per episode"
    _tick(paths, at(10, 9), source="webull", fetched=True)
    assert [p["title"] for p in pushes][-1] == "QQQ book: OK"
    assert pushes[-1]["priority"] == "low" and _lint(pushes[-1]) == []
    hb = _tick(paths, at(10, 9, 30), source="webull", fetched=True)
    assert hb["yf_fallback_streak"] == 0 and len(pushes) == 2


def test_a_pending_webull_token_pages_high(tmp_path, pushes, monkeypatch):
    """HIGH like "backup prices" (trades on late prices) -- urgent is kept for "shares may be
    stuck at Webull"."""
    paths = cs._paths(home=str(tmp_path / "home"))
    _cache(paths, bars(DAY, last="10:00"))
    monkeypatch.setitem(cs._WEBULL_LAST_ERR, "text", "ServerException: ERROR_INIT_TOKEN status:PENDING")
    for s in range(3):
        _tick(paths, at(10, 6 + s), source="yfinance", fetched=True)
    assert len(pushes) == 1 and pushes[0]["priority"] == "high"
    assert pushes[0]["title"] == "QQQ book: approve Webull login" and _lint(pushes[0]) == []
    assert pushes[0]["msg"].endswith("Do: approve the login in the Webull app.")


def test_a_broken_health_check_never_breaks_the_heartbeat(tmp_path, monkeypatch):
    paths = cs._paths(home=str(tmp_path / "home"))
    assert cs._feed_health(at(10, 0), {"bar_health": {"5m": object()}}, paths,
                           log=lambda *a: None) == {}
    cs._write_heartbeat(paths, ok=True, note="x", health={})
    hb = json.load(open(paths["heartbeat_path"]))
    assert hb["ok"] is True and "stalled" not in hb


def test_the_thread_writes_the_fields_on_the_live_heartbeat(tmp_path, monkeypatch, pushes):
    paths = cs._paths(home=str(tmp_path / "live"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    monkeypatch.setattr(cs, "_serving_hosts_ok", lambda log=print: (True, None))
    monkeypatch.setattr(cs, "log_history_windows", lambda **k: None)
    monkeypatch.setattr(cs, "_shadow_tick", lambda now, fetch, log=print: [])
    fixed = at(10, 20, 10)

    class FixedDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    monkeypatch.setattr(cs, "_dt", types.SimpleNamespace(
        datetime=FixedDT, timedelta=datetime.timedelta, time=datetime.time, date=datetime.date))
    _cache(paths, bars(DAY, last="10:00"))
    from api import cloud_signal_stream as stream_mod

    def classic(now=None, fetch=True, paths=None, warnings=None, log=print, legs=None):
        return cs.step(now=now, legs=_legs(), paths=paths, fetch=False, warnings=warnings,
                       bar_sources={"5m": "webull"})
    monkeypatch.setattr(stream_mod, "run_stream_aware_step", classic)
    stop = threading.Event()
    monkeypatch.setattr(cs._time, "sleep", lambda s: stop.set())
    cs.cloud_signal_thread(stop=stop, log=lambda *a, **k: None)
    hb = json.load(open(paths["heartbeat_path"]))
    assert hb["ok"] is True and hb["verdict"] == "stalled" and hb["stalled"] is True
    assert hb["bars_missing"] == 3 and "STALLED" in hb["note"]   # 10:05, 10:10, 10:15
    assert len(pushes) == 1


def test_a_yfinance_streak_does_not_carry_over_to_the_next_morning(tmp_path, pushes, monkeypatch):
    """Two yfinance fetches at the end of one day plus one the next morning must NOT page
    (the streak ends at the day change, like a stall episode); and a pushed episode still open
    at the close sends no 'back on Webull' push the next morning."""
    paths = cs._paths(home=str(tmp_path / "home"))
    _cache(paths, bars(DAY, last="15:45"))
    monkeypatch.setitem(cs._WEBULL_LAST_ERR, "text", "ReadTimeout: read timeout=25")
    _tick(paths, at(15, 52), source="yfinance", fetched=True)
    _tick(paths, at(15, 53), source="yfinance", fetched=True)
    nxt = "2026-10-06"
    _cache(paths, bars(nxt, last="09:30", prev_day=DAY))
    hb = _tick(paths, at(9, 36, day=nxt), source="yfinance", fetched=True)
    assert pushes == [] and hb["yf_fallback_streak"] == 1
    # a fresh morning episode still pages on its own 3rd fetch
    _tick(paths, at(9, 37, day=nxt), source="yfinance", fetched=True)
    _tick(paths, at(9, 38, day=nxt), source="yfinance", fetched=True)
    assert [p["title"] for p in pushes] == ["QQQ book: backup prices"]
    # left open overnight: the next morning's Webull fetch sends no 'again' push
    nxt2 = "2026-10-07"
    _cache(paths, bars(nxt2, last="09:30", prev_day=nxt))
    _tick(paths, at(9, 36, day=nxt2), source="webull", fetched=True)
    assert len(pushes) == 1


def test_a_none_return_from_webull_never_keeps_an_old_error(tmp_path, monkeypatch):
    """_WEBULL_LAST_ERR used to keep an old error (e.g. token PENDING) across a later call that
    returned None for another reason, so a fallback could page URGENT with the wrong cause."""
    monkeypatch.setitem(cs._WEBULL_LAST_ERR, "text", "ServerException: ERROR_INIT_TOKEN status:PENDING")
    keys = tmp_path / "keys.json"
    keys.write_text('{"app_key": "", "app_secret": ""}', encoding="utf-8")
    monkeypatch.setattr(cs, "WEBULL_KEYS", str(keys))
    assert cs._fetch_webull("5m", log=lambda *a: None) is None
    assert cs._WEBULL_LAST_ERR["text"] == "no Webull keys set"


# -- the executor's entry gate ignores the new fields (the DECIDED note in _check_feed_engine) --
def test_the_executor_entry_gate_ignores_stalled(tmp_path, monkeypatch):
    """A fresh heartbeat with ok=true, stalled=true, verdict='stalled' must read exactly like a
    plain ok=true heartbeat: feed not stale, no feed_down event, no SIGNAL STALL page -- even
    with an open lot. Wiring `stalled` into this gate is a decision, not a drive-by edit."""
    from api import qqq_exec as qe
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: sent.append(a))
    results = []
    for extra in ({}, {"stalled": True, "verdict": "stalled", "bar_age_s": 1500.0,
                       "bars_due": 9, "bars_missing": 3}):
        paths = cs._paths(home=str(tmp_path / f"h{len(results)}"))
        monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
        os.makedirs(paths["state_dir"], exist_ok=True)
        hb = dict({"ts": datetime.datetime.now(ET).isoformat(), "ok": True, "note": "x"}, **extra)
        with open(paths["heartbeat_path"], "w", encoding="utf-8") as f:
            json.dump(hb, f)
        state = {"legs": {"NOISE": {"shares": 5}}, "feed_stale": False}
        stale = qe._check_feed_engine(state, log=lambda *a: None)
        results.append((stale, state.get("feed_stale"), [e["kind"] for e in state.get("events", [])]))
    assert results[0] == results[1] == (False, False, [])
    assert sent == []


def test_feed_pushes_leave_the_engine_thread(tmp_path, pushes, monkeypatch):
    """Review 10-07: a FEED HEALTH push ran synchronously on the engine thread (up to 4 s of
    socket timeout before the heartbeat write and the next step). Live, the network send is
    handed to _engine_push_background; the repeat rule and feed_alerts.json stay in line."""
    bg = []
    monkeypatch.setattr(cs, "FEED_PUSH_BACKGROUND", True)
    monkeypatch.setattr(cs, "_engine_push_background",
                        lambda msg, title, priority="high", paths=None, log=print:
                        bg.append({"msg": msg, "title": title, "priority": priority})
                        or "background")
    paths = cs._paths(home=str(tmp_path / "home"))
    _cache(paths, bars(DAY, last="10:00", prev_day="2026-10-02"))
    _tick(paths, at(10, 6))
    _tick(paths, at(10, 20, 10))
    assert pushes == [], "nothing sent on the engine thread"
    assert [p["title"] for p in bg] == ["QQQ book: prices stopped"]
    _tick(paths, at(10, 21, 10))
    assert len(bg) == 1, "the episode bookkeeping still holds the repeat"


# -- EVERY LIVE TIMEFRAME (2026-10-09): the 1m feed ENGU-Q trades on --------------------------
def bars_1m(day, first="09:30", last="10:00"):
    """1m bars from `first` to `last` (bar START times) on `day`."""
    times = list(pd.date_range(pd.Timestamp(f"{day} {first}:00", tz=cs.TZ),
                               pd.Timestamp(f"{day} {last}:00", tz=cs.TZ), freq="1min"))
    ep = [int(t.tz_convert("UTC").timestamp()) for t in times]
    n = len(ep)
    return pd.DataFrame({"time": ep, "open": [600.0] * n, "high": [601.0] * n,
                         "low": [599.0] * n, "close": [600.5] * n, "volume": [1000.0] * n})


def _cache_1m(paths, frame):
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    frame.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)


def _two_legs():
    """ORB (5m) plus a 1m leg, as the live book reads since ENGU-Q's return."""
    legs = _legs()
    legs["ENGUQ_335"] = dict(legs["ORB_R6"], timeframe="1m")
    return legs


def _tick2(paths, now, sources=None, fetched=(), logs=None):
    """One live tick over both timeframes: step -> _feed_health -> heartbeat."""
    w = {}
    cs.step(now=now, legs=_two_legs(), paths=paths, fetch=False, warnings=w,
            bar_sources=sources)
    for tf in fetched:
        w["bar_health"][tf]["fetched"] = True
    health = cs._feed_health(now, w, paths, log=(logs.append if logs is not None
                                                 else (lambda *a: None)))
    cs._write_heartbeat(paths, ok=True, note="x", health=health)
    with open(paths["heartbeat_path"], encoding="utf-8") as f:
        return json.load(f)


def test_1m_bars_on_yfinance_page_backup_prices_once_while_5m_is_on_webull(
        tmp_path, pushes, monkeypatch):
    paths = cs._paths(home=str(tmp_path / "home"))
    _cache(paths, bars(DAY, last="10:00"))
    _cache_1m(paths, bars_1m(DAY, last="10:05"))
    monkeypatch.setitem(cs._WEBULL_LAST_ERR, "text", "HTTP 429 Too Many Requests")
    logs = []
    both = ("5m", "1m")
    for s in range(2):
        hb = _tick2(paths, at(10, 6, 10 + 20 * s), {"5m": "webull", "1m": "yfinance"}, both, logs)
    assert pushes == [] and hb["yf_fallback_streak"] == 2
    hb = _tick2(paths, at(10, 6, 50), {"5m": "webull", "1m": "yfinance"}, both, logs)
    assert [p["title"] for p in pushes] == ["QQQ book: backup prices"]
    assert pushes[0]["priority"] == "high" and _lint(pushes[0]) == []
    assert hb["yf_fallback_streak"] == 3
    assert hb["bar_source"] == "webull", "the top-level figures stay the 5m's"
    assert hb["feed_by_timeframe"]["1m"]["source"] == "yfinance"
    assert hb["feed_by_timeframe"]["5m"]["source"] == "webull"
    assert any("live 1m bars from yfinance for 3 fetches" in m for m in logs)
    for s in range(3):
        _tick2(paths, at(10, 7, 10 * s), {"5m": "webull", "1m": "yfinance"}, both)
    assert len(pushes) == 1, "one push per episode"
    hb = _tick2(paths, at(10, 7, 40), {"5m": "webull", "1m": "webull"}, both)
    assert [p["title"] for p in pushes] == ["QQQ book: backup prices", "QQQ book: OK"]
    assert hb["yf_fallback_streak"] == 0


def test_a_frozen_1m_tail_pages_prices_stopped_after_660_s_not_at_its_own_180(tmp_path, pushes):
    paths = cs._paths(home=str(tmp_path / "home"))
    _cache(paths, bars(DAY, last="10:30"))                 # the 5m keeps arriving
    _cache_1m(paths, bars_1m(DAY, last="10:09"))           # the 1m freezes: newest closed 10:10
    hb = _tick2(paths, at(10, 14))                         # 1m silent 240 s
    assert hb["feed_by_timeframe"]["1m"]["stalled"] is True, "its own verdict (> 180 s)"
    assert hb["stalled_timeframes"] == [] and hb["verdict"] == "ok" and pushes == [], \
        "a 1m tail a few bars behind never pages"
    hb = _tick2(paths, at(10, 21, 10))                     # silent 670 s > 660 s
    assert [p["title"] for p in pushes] == ["QQQ book: prices stopped"]
    assert pushes[0]["priority"] == "high" and _lint(pushes[0]) == []
    assert "since 07:10." in pushes[0]["msg"], "the 1m bar that closed 10:10 ET (07:10 MST)"
    assert hb["stalled_timeframes"] == ["1m"] and hb["verdict"] == "stalled"
    assert hb["stalled"] is False and hb["bar_timeframe"] == "5m", \
        "the top-level stalled stays the 5m's (tools/webull_freshness.py reads it as 5m)"
    for m in range(22, 26):
        _tick2(paths, at(10, m, 10))
    assert len(pushes) == 1, "one push per episode"
    _cache_1m(paths, bars_1m(DAY, last="10:25"))
    logs = []
    hb = _tick2(paths, at(10, 26, 10), logs=logs)
    assert logs == ["[cloud-signal] FEED recovered: 1m bars arriving again (newest 10:25 ET)"]
    assert hb["stalled_timeframes"] == [] and hb["verdict"] == "ok"
    assert [p["title"] for p in pushes] == ["QQQ book: prices stopped", "QQQ book: OK"]


def test_a_5m_only_book_reads_exactly_as_before(tmp_path, pushes):
    """No 1m leg: the new fields hold only the 5m, nothing else changes."""
    paths = cs._paths(home=str(tmp_path / "home"))
    _cache(paths, bars(DAY, last="10:00"))
    hb = _tick(paths, at(10, 6))
    assert hb["stalled_timeframes"] == [] and set(hb["feed_by_timeframe"]) == {"5m"}
    hb = _tick(paths, at(10, 20))
    assert hb["stalled_timeframes"] == ["5m"] and hb["stalled"] is True
    assert [p["title"] for p in pushes] == ["QQQ book: prices stopped"]
