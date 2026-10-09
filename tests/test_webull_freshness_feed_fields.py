"""tools/webull_freshness.py reads the engine's new FEED HEALTH heartbeat fields (2026-10-05,
api/cloud_signal.py: newest_closed_bar_epoch, bars_due, bars_missing, stalled, verdict).

A FRESH heartbeat that says stalled=true fails bar_age even when the cached 5m file still looks
current, and the alert names the engine's missing-bar count; a stale heartbeat's verdict is not
trusted; a heartbeat without the fields (an older engine) changes nothing. Reuses the fixture
home from tests/test_webull_freshness.py. No push, no systemctl, no live file.
"""
import datetime as dt
import importlib.util
import json
import os

import pytest

_spec = importlib.util.spec_from_file_location(
    "webull_freshness_helpers",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_webull_freshness.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)


@pytest.fixture(autouse=True)
def _no_ping(monkeypatch):
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)


def _hb(h, ts, **fields):
    data = {"ts": ts.isoformat(), "ok": True, "note": "0 event(s)"}
    data.update(fields)
    T._wj(h.paths["cs_heartbeat"], data)


def test_engine_stalled_verdict_fails_bar_age(tmp_path):
    h = T.Home(tmp_path, T.MON_1030)
    _hb(h, T.MON_1030, stalled=True, verdict="stalled", bars_due=12, bars_missing=4,
        newest_closed_bar_epoch=int(T.et(2026, 10, 5, 10, 5).timestamp()))
    out = h.run()
    assert "bar_age" in T.failing(out)
    detail = out["status"]["verdicts"]["bar_age"]["detail"]
    assert "4 of today's 12 bar(s) missing" in detail
    assert "engine_hb" not in T.failing(out), "ok keeps its meaning: the engine is running"


def test_engine_ok_verdict_keeps_bar_age_passing(tmp_path):
    h = T.Home(tmp_path, T.MON_1030)
    _hb(h, T.MON_1030, stalled=False, verdict="ok", bars_due=12, bars_missing=0)
    assert "bar_age" not in T.failing(h.run())


def test_a_stale_heartbeat_verdict_is_not_trusted(tmp_path):
    h = T.Home(tmp_path, T.MON_1030)
    _hb(h, T.MON_1030 - dt.timedelta(minutes=10), stalled=True, verdict="stalled")
    out = h.run()
    assert "bar_age" not in T.failing(out)


def test_heartbeat_bar_time_used_when_the_state_has_none(tmp_path):
    h = T.Home(tmp_path, T.MON_1030)
    T._wj(h.paths["cs_state"], {"bar_source": {}, "eod_settled": {}})
    T._w(h.paths["qqq_5m"], "time,open,high,low,close,volume\n")
    _hb(h, T.MON_1030, stalled=False, verdict="ok",
        newest_closed_bar_epoch=int(T.et(2026, 10, 5, 10, 20).timestamp()))
    assert "bar_age" not in T.failing(h.run())


# -- ONE PAGER: the engine pages bars stopped / bars on yfinance itself ------------------------
def test_engine_paged_stall_is_tracked_but_not_pushed_twice(tmp_path):
    """The engine (api/cloud_signal.py FEED HEALTH) pushes 'prices stopped' itself; with a fresh
    heartbeat carrying its verdict this monitor keeps the episode on its status but sends no
    second page -- not at the start, not at the end."""
    h = T.Home(tmp_path, T.MON_1030)
    stalled = dict(stalled=True, verdict="stalled", bars_due=12, bars_missing=4,
                   newest_closed_bar_epoch=int(T.et(2026, 10, 5, 10, 5).timestamp()))
    _hb(h, T.MON_1030, **stalled)
    out = h.run()
    assert "bar_age" in T.failing(out)
    assert [a["key"] for a in out["status"]["open_alerts"] if a.get("quiet")] == ["bar_age"]
    assert h.pushes == []
    h.advance(T.MON_1030 + dt.timedelta(minutes=2))
    _hb(h, T.MON_1030 + dt.timedelta(minutes=2), **stalled)
    h.run()
    assert h.pushes == []
    h.advance(T.MON_1030 + dt.timedelta(minutes=4))
    _hb(h, T.MON_1030 + dt.timedelta(minutes=4), stalled=False, verdict="ok", bars_due=12,
        bars_missing=0)
    out = h.run()
    assert "bar_age" not in T.failing(out) and h.pushes == [], "no second 'OK again' page either"


def test_engine_paged_yfinance_is_tracked_but_not_pushed_twice(tmp_path):
    h = T.Home(tmp_path, T.MON_1030)
    h.cs_state(source="yfinance")
    _hb(h, T.MON_1030, stalled=False, verdict="ok", bar_source="yfinance", yf_fallback_streak=2)
    h.run()
    h.advance(T.MON_1030 + dt.timedelta(minutes=2))
    _hb(h, T.MON_1030 + dt.timedelta(minutes=2), stalled=False, verdict="ok",
        bar_source="yfinance", yf_fallback_streak=5)
    out = h.run()
    assert "bar_source" in T.failing(out)
    assert h.pushes == []


def test_an_older_engine_without_the_fields_still_gets_paged_here(tmp_path):
    h = T.Home(tmp_path, T.MON_1030)
    h.cs_state(newest_bar_start=T.et(2026, 10, 5, 10, 0))     # closed 10:05, 25 min ago
    out = h.run()
    assert "bar_age" in T.failing(out)
    assert len(h.pushes) == 1 and "newest QQQ price bar" in h.pushes[0]["message"]


# -- EVERY LIVE TIMEFRAME (2026-10-09): ENGU-Q is live again, on 1m bars ----------------------
def _with_1m(h, source, checked_at):
    st = json.load(open(h.paths["cs_state"], encoding="utf-8"))
    st["bar_source"]["1m"] = {"source": source, "newest_epoch": int(checked_at.timestamp()) - 120,
                              "checked_at": checked_at.isoformat()}
    T._wj(h.paths["cs_state"], st)


def test_bar_source_fails_on_the_1m_cache_from_yfinance(tmp_path):
    h = T.Home(tmp_path, T.MON_1030)
    _with_1m(h, "yfinance", T.MON_1030)
    h.run()
    assert h.pushes == []
    h.advance(T.MON_1030 + dt.timedelta(minutes=2))
    out = h.run()
    assert "bar_source" in T.failing(out)
    assert "the 1m cache is being filled from yfinance" in \
        out["status"]["verdicts"]["bar_source"]["detail"]
    assert len(h.pushes) == 1 and "slower backup source" in h.pushes[0]["message"]


def test_bar_source_ignores_a_1m_entry_no_live_leg_refreshes(tmp_path):
    """A timeframe the engine stopped stamping (its leg left the book) keeps its last entry in
    state.json: it must not keep the check failing."""
    h = T.Home(tmp_path, T.MON_1030)
    _with_1m(h, "yfinance", T.et(2026, 9, 28, 15, 59))
    h.run()
    h.advance(T.MON_1030 + dt.timedelta(minutes=2))
    out = h.run()
    assert "bar_source" not in T.failing(out) and h.pushes == []
