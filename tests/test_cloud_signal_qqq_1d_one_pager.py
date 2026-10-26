"""api/cloud_signal.py -- QQQ_1d MISSING: ONE PAGER (MANAGER DECISION REC 2026-10-25).

A missing or empty <home>/ohlc/QQQ_1d.csv used to buzz the phone three times for one cause: the
box monitor's qqq_1d check (tools/webull_freshness.py), DIP_424's NOT READY note and NOISE's
vol-window note. The monitor's is the one kept; the engine's two are RECORD-ONLY while -- and
only while -- that file provably is their cause. Pinned here:

  1. the file test (qqq_1d_missing_or_empty): missing, 0 bytes, blank lines, a header only, rows
     whose time never parses -> missing / empty; any row whose time parses -> present; a file
     that cannot be read -> present (the engine pages as before);
  2. the cause test (_qqq_1d_is_the_cause): DIP "short" and the bridge's "missing_cache" with
     the file missing or empty, and either one's "error" when pandas found nothing to parse in an
     existing empty file (EmptyDataError) -- nothing else; and only while the box monitor's
     heartbeat is fresh (_box_monitor_alive, 600 s -- the PC's own "box monitor silent" bar):
     a dead monitor and the engine pages its own notes, from its next tick;
  3. NOISE (c): a missing, 0-byte, blank or header-only file -> no push all day, an engine
     restart included, no phone_dedupe.json write, the vol_window entry still published (short,
     record_only) and one log line; a present file the bridge refuses (thin, ratio, an error, no
     prior day, too short, no finished day) still pages; the file coming back broken the same
     day pages then;
  4. DIP (b): missing, 0-byte, header-only -> no push (warnings still name it); with the file
     missing a hole / a missing previous session / today's first bar late still page, and so does
     a runner error with the file present;
  5. ONE CAUSE, ONE PUSH, end to end: the engine (NOISE + the live DIP leg) and the box monitor on
     one home with QQQ_1d.csv missing all day -> exactly one phone push (the monitor's pre-open
     note, worded with the engine's own numbers), across an engine restart and a monitor
     restart; missing only from mid-morning, or only a "+1 more" behind another pre-open miss
     -> the monitor's session check is that one push; the monitor never running, or going
     quiet -> the engine's DIP and NOISE notes page;
  6. signals.csv, state.json and the engine's input are the same with the routing as without it.

Every test but the monitor-liveness ones (and the end-to-end walks, where the real monitor writes
its heartbeat) holds the monitor alive (_alive_monitor).

No network: every fetch is a stub, every push a recorder, every store under tmp_path.
"""
import importlib
import importlib.util
import json
import os

import pandas as pd
import pytest

from api import cloud_signal as cs
from api import dip_live as DL
from api import ntfy_push

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = _load("one_pager_stream_helpers", "test_cloud_signal_stream_parity.py")
G = _load("one_pager_vol_window_helpers", "test_cloud_signal_vol_window_guard.py")
S = _load("one_pager_dip_helpers", "test_dip424_shadow.py")

DAY, DAY2, NEED = G.DAY, G.DAY2, G.NEED
LIVE = G.LIVE                                  # "NOISE_382"
DIP = "DIP_424"
RECORD_LINE = "the box monitor's qqq_1d check pages that, recorded here (no push)"


def _quiet(*_a, **_k):
    return None


_REAL_ALIVE = cs._box_monitor_alive


@pytest.fixture(autouse=True)
def _alive_monitor(monkeypatch):
    """The box monitor's heartbeat is fresh (see the docstring); _real_monitor() undoes it."""
    monkeypatch.setattr(cs, "_box_monitor_alive", lambda now_epoch, paths=None: True)


def _real_monitor(monkeypatch):
    monkeypatch.setattr(cs, "_box_monitor_alive", _REAL_ALIVE)


@pytest.fixture(autouse=True)
def _fresh_memos(monkeypatch):
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)    # the monitor's ping
    for name in ("_VOL_WINDOW_STASH", "_VOL_WINDOW_NOTED", "_LIVE_NOT_READY_NOTED",
                 "_QQQ_1D_RECORDED"):
        monkeypatch.setattr(cs, name, {})
    cs._DAILY_CALIBRATION_LOG.clear()
    DL._PROBE_MEMO.clear()
    yield
    cs._DAILY_CALIBRATION_LOG.clear()
    DL._PROBE_MEMO.clear()


@pytest.fixture
def box(monkeypatch):
    """The cloud box, offline (tests/test_cloud_signal_vol_window_guard.py's): a fetch reads the
    cache back, the daily refresh never runs (the file stays as the test left it), every network
    path raises, and the engine's background push is recorded."""
    def boom(*a, **k):
        raise AssertionError("network touched")

    monkeypatch.setattr(cs, "fetch_and_merge",
                        lambda tf, paths=None, log=print: (cs.historical_bars(tf, paths), "webull", True))
    monkeypatch.setattr(cs, "_maybe_refresh_daily_cache", lambda *a, **k: None)
    monkeypatch.setattr(cs, "_fetch_webull", boom)
    monkeypatch.setattr(cs.qp, "_fetch_yf", boom)
    monkeypatch.setattr(cs, "_fetch_yf_daily", boom)
    monkeypatch.setattr(cs, "NOISE_FORWARD_LOG", False)
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    sent = []

    def fake_push(msg, title, priority="high", paths=None, log=print):
        sent.append({"title": title, "message": msg, "priority": priority})
        return "background"

    monkeypatch.setattr(cs, "_engine_push_background", fake_push)
    return sent


def _restart_engine():
    """What a process restart loses: every in-process memo (phone_dedupe.json stays)."""
    for d in (cs._VOL_WINDOW_STASH, cs._VOL_WINDOW_NOTED, cs._LIVE_NOT_READY_NOTED,
              cs._QQQ_1D_RECORDED):
        d.clear()
    cs._DAILY_CALIBRATION_LOG.clear()


HEADER = "time,open,high,low,close,volume\n"
GONE = {                                    # QQQ_1d.csv as the file test sees it
    "missing": None,
    "zero_bytes": "",
    "blank_lines": "\n\n  \n",
    "header_only": HEADER,
}


def _write_1d(paths, text):
    p = cs._cache_path("1d", paths)
    if text is None:
        if os.path.exists(p):
            os.remove(p)
        return
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _dedupe_store(paths):
    return os.path.join(paths["state_dir"], cs.PHONE_DEDUPE_FILE)


# -- 1. the file test -------------------------------------------------------------------------
@pytest.mark.parametrize("text, want", [
    (None, "missing"), ("", "empty"), ("\n\n  \n", "empty"), (HEADER, "empty"),
    (HEADER + "x,1,1,1,1,1\nnan,1,1,1,1,1\ninf,1,1,1,1,1\n", "empty"),
    ("﻿time,open\n", "empty"),
    (HEADER + "1759377600,1,1,1,1,1\n", None),
    (HEADER + "1759377600.0,1,1,1,1,1\n", None),
    (HEADER + "1759377600,1,1,1,1,1\n17593,torn", None),       # a torn last line: rows remain
    ("1759377600,1,1,1,1,1\n", None),                          # no header
])
def test_the_file_test(tmp_path, text, want):
    paths = cs._paths(home=str(tmp_path))
    _write_1d(paths, text)
    assert cs.qqq_1d_missing_or_empty(paths) == want


def test_a_file_that_cannot_be_read_is_present(tmp_path):
    """Unreadable is not "missing": the engine keeps paging its own notes."""
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(cs._cache_path("1d", paths))                   # a directory where the file goes
    assert cs.qqq_1d_missing_or_empty(paths) is None


# -- 2. the cause test --------------------------------------------------------------------------
EMPTY_ERR_DIP = "the DIP runner failed (EmptyDataError: No columns to parse from file)"
EMPTY_ERR_VPR = "EmptyDataError: No columns to parse from file"


@pytest.mark.parametrize("note, reason, text, file_text, want", [
    ("not_ready", "short", "x", None, "missing"),
    ("not_ready", "short", "x", HEADER, "empty"),
    ("not_ready", "short", "x", HEADER + "1759377600,1,1,1,1,1\n", None),  # present: pages
    ("not_ready", "error", EMPTY_ERR_DIP, "", "empty"),
    ("not_ready", "error", EMPTY_ERR_DIP, None, None),        # cannot come from a missing file
    ("not_ready", "error", EMPTY_ERR_DIP, HEADER + "1759377600,1,1,1,1,1\n", None),
    ("not_ready", "error", "the DIP runner failed (RuntimeError: probe broke)", "", None),
    ("not_ready", "hole", "x", None, None),
    ("not_ready", "prev_missing", "x", None, None),
    ("not_ready", "today_open", "x", None, None),
    ("not_ready", "cal_thin", "x", None, None),
    ("not_ready", "cal_fail", "x", None, None),
    ("not_ready", "cal_split", "x", None, None),
    ("not_ready", "half_day_rule", "x", None, None),
    ("not_ready", "missing_cache", "x", None, None),          # not a DIP reason
    ("vol_window", "missing_cache", "x", None, "missing"),
    ("vol_window", "missing_cache", "x", HEADER, "empty"),
    ("vol_window", "missing_cache", "x", HEADER + "1759377600,1,1,1,1,1\n", None),
    ("vol_window", "error", EMPTY_ERR_VPR, "", "empty"),
    ("vol_window", "error", EMPTY_ERR_VPR, None, None),
    ("vol_window", "error", "ValueError: garbled daily file", "", None),
    ("vol_window", "short", "x", None, None),                 # not a bridge reason
    ("vol_window", "no_finished", "x", None, None),
    ("vol_window", "thin_overlap", "x", None, None),
    ("vol_window", "ratio_out_of_band", "x", None, None),
    ("vol_window", "no_valid_overlap", "x", None, None),
    ("vol_window", "no_prior_daily", "x", None, None),
    ("vol_window", "ok", "x", None, None),                    # bridged, too short: short_depth
])
def test_the_cause_test(tmp_path, note, reason, text, file_text, want):
    paths = cs._paths(home=str(tmp_path))
    _write_1d(paths, file_text)
    assert cs._qqq_1d_is_the_cause(note, reason, text, paths) == want


def test_a_broken_cause_test_pages(monkeypatch, tmp_path):
    """Never raises: a failure reads as "not the file" -- the note pages as before."""
    def boom(_paths):
        raise RuntimeError("stat broke")
    monkeypatch.setattr(cs, "qqq_1d_missing_or_empty", boom)
    assert cs._qqq_1d_is_the_cause("not_ready", "short", "x", cs._paths(home=str(tmp_path))) is None


def _monitor_heartbeat(paths, epoch):
    """The box monitor's freshness_heartbeat.json under the engine's home, as run_once writes it."""
    p = os.path.join(paths["home"], "freshness", "freshness_heartbeat.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"ts": "x", "epoch": epoch, "ok": True}, f)
    return p


NOW_EPOCH = 1_790_000_000.0


def test_the_monitor_is_alive_only_while_its_heartbeat_is_fresh(tmp_path):
    from tools import webull_freshness_pc as pc
    assert cs.QQQ_1D_MONITOR_ALIVE_SEC == pc.BOX_SILENT_SEC == 600   # the PC's "monitor silent"
    paths = cs._paths(home=str(tmp_path))
    assert wf.default_paths(paths["home"])["heartbeat"] == os.path.join(
        paths["home"], "freshness", "freshness_heartbeat.json")    # the file the monitor writes
    assert _REAL_ALIVE(NOW_EPOCH, paths) is False                  # never ran
    p = _monitor_heartbeat(paths, NOW_EPOCH - 600)
    assert _REAL_ALIVE(NOW_EPOCH, paths) is True
    _monitor_heartbeat(paths, NOW_EPOCH - 601)
    assert _REAL_ALIVE(NOW_EPOCH, paths) is False                  # quiet over 10 minutes
    _monitor_heartbeat(paths, NOW_EPOCH + 5000)
    assert _REAL_ALIVE(NOW_EPOCH, paths) is False                  # a garbled epoch far ahead
    for bad in ('{"epoch": null}', '{"ts": "x"}', "not json", "[]", '{"epoch": "nan"}'):
        with open(p, "w", encoding="utf-8") as f:
            f.write(bad)
        assert _REAL_ALIVE(NOW_EPOCH, paths) is False, bad


@pytest.mark.parametrize("note, reason, file_text, want", [
    ("not_ready", "short", None, "missing"), ("vol_window", "missing_cache", HEADER, "empty"),
    ("not_ready", "error", "", "empty")])
def test_with_the_monitor_quiet_the_cause_test_pages(tmp_path, monkeypatch, note, reason,
                                                     file_text, want):
    _real_monitor(monkeypatch)
    paths = cs._paths(home=str(tmp_path))
    _write_1d(paths, file_text)
    text = EMPTY_ERR_DIP if reason == "error" else "x"
    assert cs._qqq_1d_is_the_cause(note, reason, text, paths, NOW_EPOCH) is None    # never ran
    _monitor_heartbeat(paths, NOW_EPOCH - 120)
    assert cs._qqq_1d_is_the_cause(note, reason, text, paths, NOW_EPOCH) == want
    assert cs._qqq_1d_is_the_cause(note, reason, text, paths, NOW_EPOCH + 601) is None


# -- 3. NOISE: the vol-window note ----------------------------------------------------------------
def _noise_home(tmp_path, name, file_text):
    paths = G._home(tmp_path, name, daily="ok")
    _write_1d(paths, file_text)
    return paths


@pytest.mark.parametrize("case", sorted(GONE))
def test_a_missing_or_empty_daily_file_is_recorded_not_paged(tmp_path, box, capsys, case):
    paths = _noise_home(tmp_path, case, GONE[case])
    legs = G._legs(shadow=True)
    want_key = "error" if case in ("zero_bytes", "blank_lines") else "missing_cache"
    for hhmm in ("09:30", "09:35", "09:40", "09:45", "10:15"):
        _events, w = G._step(paths, legs, hhmm)
    e = w[cs.VOL_WINDOW_KEY][LIVE]
    assert e["short"] is True and e["have"] == 92 and e["reason_key"] == want_key, e
    if want_key == "error":
        assert "EmptyDataError:" in e["text"]
    assert e["record_only"] is True and e["pushed"] is None
    assert w[cs.VOL_WINDOW_KEY][G.SHADOW]["record_only"] is False   # a shadow leg never pages
    assert box == [] and not os.path.exists(_dedupe_store(paths))
    out = capsys.readouterr().out
    assert out.count(RECORD_LINE) == 1, out                    # one line a day, not a tick
    _restart_engine()                                          # a restart the same day
    for hhmm in ("10:20", "10:25", "15:50"):
        _events, w = G._step(paths, legs, hhmm)
    assert box == [] and w[cs.VOL_WINDOW_KEY][LIVE]["record_only"] is True
    assert capsys.readouterr().out.count(RECORD_LINE) == 1     # once more: a new process
    G._step(paths, legs, "09:40", day=DAY2)                    # the next day: still recorded
    assert box == []


@pytest.mark.parametrize("case, reason_key", [
    ("thin", "thin_overlap"), ("ratio", "ratio_out_of_band"), ("no_prior", "no_prior_daily"),
    ("short_depth", "short_depth"), ("no_finished", "no_finished"), ("error", "error"),
    ("empty_error_text", "error"),
])
def test_a_present_file_the_bridge_refuses_still_pages(tmp_path, box, monkeypatch, case,
                                                       reason_key):
    df5 = G._df5()
    full = P._daily_frame(df5, n_prior=170, exclude=DAY2)
    daily = {"thin": G._thin(full, df5), "ratio": G._scaled(full),
             "no_prior": G._drop_prior(full, df5),
             "short_depth": P._daily_frame(df5, n_prior=100, exclude=DAY2),
             "no_finished": G._from_today(full), "error": full, "empty_error_text": full}[case]
    if case in ("error", "empty_error_text"):
        exc = (pd.errors.EmptyDataError("No columns to parse from file")
               if case == "empty_error_text" else ValueError("garbled daily file"))

        def broken(_df):
            raise exc
        monkeypatch.setattr(cs, "_daily_ranges_by_date", broken)
    paths = G._home(tmp_path, case, daily=daily, df5=df5)
    assert cs.qqq_1d_missing_or_empty(paths) is None
    for hhmm in ("09:30", "09:35", "09:40"):
        _events, w = G._step(paths, G._legs(), hhmm)
    e = w[cs.VOL_WINDOW_KEY][LIVE]
    assert e["short"] is True and e["reason_key"] == reason_key, e
    (p,) = box
    assert p["title"].startswith("NOISE: vol-skip check") and e["pushed"] == DAY
    assert e["record_only"] is False


def test_the_file_coming_back_broken_the_same_day_pages_then(tmp_path, box, capsys):
    df5 = G._df5()
    paths = G._home(tmp_path, daily=None, df5=df5)
    legs = G._legs()
    for hhmm in ("09:35", "09:40", "09:45"):
        G._step(paths, legs, hhmm)
    assert box == [] and RECORD_LINE in capsys.readouterr().out
    G._scaled(P._daily_frame(df5, n_prior=170, exclude=DAY2)).to_csv(
        cs._cache_path("1d", paths), index=False)              # back, but 3x too wide
    _events, w = G._step(paths, legs, "09:50")
    (p,) = box
    assert "disagree on size" in p["message"]
    e = w[cs.VOL_WINDOW_KEY][LIVE]
    assert e["reason_key"] == "ratio_out_of_band" and e["pushed"] == DAY
    assert e["record_only"] is False
    G._step(paths, legs, "10:00")
    assert len(box) == 1                                       # and once only


# -- 4. DIP: the NOT READY note --------------------------------------------------------------------
def _dip_live():
    """The SHIPPED live DIP leg, its live_since moved to the fixtures' first session."""
    return {DIP: dict(cs.CROWN_LEGS[DIP], live_since=S.CRASH_DAYS[0].isoformat())}


def _dip_walk(paths, live, day, mins=(35, 40, 45, 50)):
    out = []
    for mm in mins:
        w = {}
        assert cs.step(now=S.at(day, 9, mm, 5), legs=live, paths=paths, fetch=True,
                       warnings=w) == []
        out.append(w)
    return out


@pytest.mark.parametrize("case", ["missing", "zero_bytes", "header_only"])
def test_a_dip_leg_not_ready_for_a_missing_or_empty_file_is_recorded_not_paged(
        tmp_path, box, capsys, case):
    paths = S.write_home(tmp_path, S.CRASH, 30, no_1d=True)
    _write_1d(paths, GONE[case])
    live = _dip_live()
    ws = _dip_walk(paths, live, S.D_ENTRY)
    want = "error" if case == "zero_bytes" else "short"
    for w in ws:                                               # still named every time
        assert w["legs_not_ready"][DIP]["reason"] == want, w
    if want == "error":
        assert "EmptyDataError:" in ws[-1]["legs_not_ready"][DIP]["text"]
    assert box == [] and not os.path.exists(_dedupe_store(paths))
    assert capsys.readouterr().out.count(RECORD_LINE) == 1
    _restart_engine()
    _dip_walk(paths, live, S.D_ENTRY, mins=(55,))
    assert box == []
    # the file back: the live leg seeds as before, and nothing was ever pushed
    S.write_1d(paths, S.CRASH)
    lv = cs.step(now=S.at(S.D_ENTRY, 10, 5, 5), legs=live, paths=paths, fetch=True)
    assert [e["event"] for e in lv] == ["SEED"] and box == []


@pytest.mark.parametrize("case, reason", [("hole", "hole"), ("prev", "prev_missing"),
                                          ("late_open", "today_open")])
def test_every_other_dip_reason_still_pages_with_the_file_missing(tmp_path, box, case, reason):
    day = S.D_ENTRY
    drop = {"hole": (S.CRASH_DAYS[-20],), "prev": (S.D_CRASH,), "late_open": ()}[case]
    paths = S.write_home(tmp_path, S.CRASH, 30, drop_5m=drop, no_1d=True)
    if case == "late_open":                                    # today's 09:30 bar not cached yet
        f5 = cs._cache_path("5m", paths)
        df = pd.read_csv(f5)
        df[df["time"] != S._epoch(day)].to_csv(f5, index=False)
    assert cs.qqq_1d_missing_or_empty(paths) == "missing"
    ws = _dip_walk(paths, _dip_live(), day)
    assert ws[-1]["legs_not_ready"][DIP]["reason"] == reason, ws[-1]
    (p,) = box
    assert p["title"] == "DIP #424: not trading" and ntfy_push.lint(p) == []


def test_a_dip_runner_error_with_the_file_present_still_pages(tmp_path, box, monkeypatch):
    paths = S.write_home(tmp_path, S.CRASH, 30)

    def boom(*a, **k):
        raise RuntimeError("probe broke")
    monkeypatch.setattr(DL, "dip_positions", boom)
    ws = _dip_walk(paths, _dip_live(), S.D_ENTRY)
    assert ws[-1]["legs_not_ready"][DIP]["reason"] == "error"
    (p,) = box
    assert p["message"].split("\n")[1] == "Its strategy run failed."


# -- 5. one cause, one push: the engine and the monitor together ------------------------------------
T = _load("one_pager_freshness_helpers", "test_webull_freshness.py")
wf = T.wf


def _together(tmp_path, monkeypatch):
    """The box monitor's fixture home and an engine store sharing ONE ohlc dir and home (the
    engine reads the monitor's real heartbeat): the vol-window fixture's 95 5m sessions through
    DAY2, no QQQ_1d.csv; the engine runs NOISE_382 (the stub that names vol_prior_ranges) and the
    live DIP_424 leg."""
    _real_monitor(monkeypatch)
    day = pd.Timestamp(DAY).date()
    h = T.Home(tmp_path / "box", T.et(day.year, day.month, day.day, 8, 30, 30))
    ohlc = os.path.dirname(h.paths["qqq_1d"])
    G._df5().to_csv(h.paths["qqq_5m"], index=False)
    os.remove(h.paths["qqq_1d"])
    paths = cs._paths(home=str(tmp_path / "engine"))
    paths["ohlc_dir"] = ohlc
    paths["home"] = h.root
    legs = dict(G._legs())
    legs[DIP] = dict(cs.CROWN_LEGS[DIP], live_since="2026-01-02")
    return h, paths, legs


def _bar_now(hhmm):
    return G._at(hhmm).astimezone(wf.ET)


def test_one_cause_one_push_all_day_across_restarts(tmp_path, box, monkeypatch):
    h, paths, legs = _together(tmp_path, monkeypatch)
    h.run()                                                    # 08:30 pre-open slot
    h.advance(h.now.replace(hour=9, minute=15))
    h.run()                                                    # 09:15 slot: no repeat
    widths = []
    for hhmm in P._hhmms("09:30", "10:25"):
        now = _bar_now(hhmm)
        w = {}
        cs.step(now=now, legs=legs, paths=paths, fetch=True, warnings=w)
        if cs.VOL_WINDOW_KEY in w:
            widths.append(w[cs.VOL_WINDOW_KEY][LIVE]["depth_5m"])
        h.advance(now)
        h.run()
        if hhmm == "09:55":
            _restart_engine()                                  # the engine restarts
        if hhmm == "10:05":
            importlib.reload(wf)                               # so does the monitor
    for mm in range(30, 60, 2):                                # the monitor's own 2-minute runs
        h.advance(h.now.replace(hour=10, minute=mm))
        h.run()
    h.advance(h.now.replace(hour=15, minute=58))
    h.run()
    assert box == [], "the engine pushed for a missing QQQ_1d.csv"
    (p,) = h.pushes
    assert p["title"] == "QQQ book: CHECK NOW" and p["priority"] == "high"
    assert p["message"] == (
        "Trading: AFFECTED - DIP #424 takes no new trades and sends no exit for its held "
        "shares, and NOISE's vol skip ranks on 92 sessions, not 252, until the file is back.\n"
        "The QQQ daily price file is missing on the cloud box.\n"
        "Do: ask Claude (PAPER-WB chat).")
    assert ntfy_push.lint(p) == []
    assert set(widths) == {92}, "the monitor's 92 is the engine's own depth"
    with open(h.paths["monitor_state"], encoding="utf-8") as f:
        rec = json.load(f)["alerts"][wf.QQQ_1D_MISSING_ID]
    assert rec["open"] is True and rec["prepushed"] is True and not rec.get("quiet")


def test_missing_from_mid_morning_the_session_check_is_the_one_push(tmp_path, box, monkeypatch):
    h, paths, legs = _together(tmp_path, monkeypatch)
    legs = {LIVE: legs[LIVE]}          # NOISE only: this fixture's daily file is too short for DIP
    full = P._daily_frame(G._df5(), n_prior=170, exclude=DAY2)
    full.to_csv(h.paths["qqq_1d"], index=False)
    h.run()
    assert [x["title"] for x in h.pushes] == ["QQQ book: OK"]   # the pre-open gate passed
    for hhmm in P._hhmms("09:30", "10:25"):
        if hhmm == "09:50":
            os.remove(h.paths["qqq_1d"])
        now = _bar_now(hhmm)
        cs.step(now=now, legs=legs, paths=paths, fetch=True, warnings={})
        h.advance(now)
        h.run()
    assert box == []
    titles = [x["title"] for x in h.pushes]
    assert titles == ["QQQ book: OK", "QQQ book: CHECK NOW"], titles
    assert "The QQQ daily price file is missing on the cloud box." in h.pushes[-1]["message"]


def test_behind_another_gate_miss_the_session_check_names_it(tmp_path, box, monkeypatch):
    """The 08:30 note leads with the Webull login (the file is only "+1 more"), approved by
    09:00: the monitor's session check is then the one note that names the file and what it
    does to DIP and NOISE -- and the engine still only records."""
    h, paths, legs = _together(tmp_path, monkeypatch)
    h.token(status="PENDING")
    h.run()
    h.token()
    for hh, mm in ((9, 0), (9, 15)):
        h.advance(h.now.replace(hour=hh, minute=mm))
        h.run()
    for hhmm in P._hhmms("09:30", "10:25"):
        now = _bar_now(hhmm)
        cs.step(now=now, legs=legs, paths=paths, fetch=True, warnings={})
        h.advance(now)
        h.run()
    assert box == []
    assert [p["message"].split("\n")[1] for p in h.pushes] == [
        "The Webull login needs approval. +1 more.",
        "The QQQ daily price file is missing on the cloud box."]
    assert h.pushes[-1]["message"].split("\n")[0] == (
        "Trading: AFFECTED - DIP #424 takes no new trades and sends no exit for its held "
        "shares, and NOISE's vol skip ranks on 92 sessions, not 252, until the file is back.")


@pytest.mark.parametrize("quiet_from", [None, "09:50"])
def test_with_the_monitor_quiet_the_engine_pages_its_own_notes(tmp_path, box, monkeypatch,
                                                               quiet_from):
    """The monitor never runs today (its timer or unit dead), or stops after 09:45: the engine's
    DIP and NOISE notes page, as before the one-pager -- from the first tick the monitor's
    heartbeat is over 600 s old, once each."""
    h, paths, legs = _together(tmp_path, monkeypatch)
    first = None
    for hhmm in P._hhmms("09:30", "10:25"):
        now = _bar_now(hhmm)
        cs.step(now=now, legs=legs, paths=paths, fetch=True, warnings={})
        if box and first is None:
            first = hhmm
        if quiet_from is not None and hhmm < quiet_from:
            h.advance(now)
            h.run()
    assert sorted(p["title"] for p in box) == ["DIP #424: not trading",
                                                "NOISE: vol-skip check short"], box
    # never ran: the first step from 09:40 ET (the 09:35 bar's close); quiet: 09:45's run + 600 s
    assert first == ("09:35" if quiet_from is None else "10:00")
    assert all(ntfy_push.lint(p) == [] for p in box)


# -- 6. never a signal -----------------------------------------------------------------------------
def test_signals_state_and_engine_input_are_the_same_with_and_without_the_routing(
        tmp_path, box, monkeypatch):
    """The routing only decides push vs record: with the file missing, the same walk with the
    routing switched off (every note pages, as before) writes the same rows and state.json."""
    decisions = {f"{DAY} 09:45": "long", f"{DAY} 10:05": "exit"}

    def walk(name):
        paths = G._home(tmp_path, name, daily=None)
        stub, legs = G._stub_legs(decisions)
        legs[DIP] = dict(cs.CROWN_LEGS[DIP], live_since="2026-01-02")
        events = G._walk(paths, legs)
        return paths, stub, events

    on, stub_on, events_on = walk("on")
    assert box == []
    monkeypatch.setattr(cs, "qqq_1d_missing_or_empty", lambda paths=None: None)
    _restart_engine()
    off, stub_off, events_off = walk("off")
    assert len(box) == 2                                       # DIP + NOISE paged, as before
    assert events_on == events_off
    assert any(e["event"] == "ENTRY" for evs in events_on for e in evs)
    assert [c["vpr"] for c in stub_on.calls] == [c["vpr"] for c in stub_off.calls]
    assert G._ledger_without_emitted_at(on) == G._ledger_without_emitted_at(off)
    with open(on["state_path"], "rb") as f_on, open(off["state_path"], "rb") as f_off:
        assert f_on.read() == f_off.read(), "state.json byte-identical"
