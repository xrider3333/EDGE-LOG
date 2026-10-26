"""tools/webull_freshness.py -- QQQ_1d MISSING: ONE PAGER (MANAGER DECISION REC 2026-10-25).

When the box's ohlc/QQQ_1d.csv is MISSING or EMPTY this monitor's qqq_1d check is the ONE phone
note for it (api/cloud_signal records its DIP not-ready and NOISE vol-window notes instead --
tests/test_cloud_signal_qqq_1d_one_pager.py). Pinned here:

  1. the wording is the true impact, off the 5m cache's depth: DIP #424 takes no new trades and
     sends no exit for its held shares (under 430 sessions), NOISE's vol skip ranks on k5 - 1
     sessions instead of 252 (off under 60); lint-clean for every depth and both file states;
     the constants are the strategies' own;
  2. it pages ONCE for the cause: the pre-open gate's note, and no second one from the 09:40
     session check (its own episode, qqq_1d_missing, opens "prepushed"), across a monitor
     restart; the session check is the one note when the gate never NAMED it (missing from
     mid-morning, back at a slot or any run in between, or only a "+1 more" behind another
     miss); a fix sends the one low "OK"; a new loss after that pages again; a stale episode
     already open when the file goes still pages the new cause;
  3. the file test is the engine's (the monitor pages whenever the engine records);
  4. the stale ("a day short") cases keep their ids and words.
Reuses tests/test_webull_freshness.py's fixture home. No push, no systemctl, no live file.
"""
import datetime as dt
import importlib
import importlib.util
import json
import os

import pytest

from api import ntfy_push

_spec = importlib.util.spec_from_file_location(
    "webull_freshness_helpers_q1d",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_webull_freshness.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
wf = T.wf
et = T.et

MON = dt.date(2026, 10, 5)                     # a Monday session day
HEADER = "time,open,high,low,close,volume\n"
MISSING_LINE = "The QQQ daily price file is missing on the cloud box."
EMPTY_LINE = "The QQQ daily price file on the cloud box is empty."


@pytest.fixture(autouse=True)
def _no_ping(monkeypatch):
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)


def _sessions_before(day, n):
    out, d = [], day - dt.timedelta(days=1)
    while len(out) < n:
        if wf.market_calendar.is_session(d):
            out.append(d)
        d -= dt.timedelta(days=1)
    return out[::-1]


def _write_5m(path, days, bars=3, extra=()):
    """A QQQ_5m.csv with `bars` RTH bars (09:30, 09:35, ...) on each day, plus `extra` rows."""
    rows = [HEADER]
    for d in days:
        for i in range(bars):
            t = wf.at(d, (9, 30)) + dt.timedelta(minutes=5 * i)
            rows.append(f"{int(t.timestamp())},1,1,1,1,1\n")
    rows += [f"{int(e)},1,1,1,1,1\n" for e in extra]
    T._w(path, "".join(rows))


def _home(tmp_path, now, k5=93, state="missing"):
    """The fixture box with `k5` 5m sessions before today and QQQ_1d.csv `state`: "missing",
    "empty" (0 bytes), "header" (a header only) or None (left healthy)."""
    h = T.Home(tmp_path, now)
    _write_5m(h.paths["qqq_5m"], _sessions_before(now.date(), k5))
    _set_1d(h, state)
    return h


def _set_1d(h, state):
    p = h.paths["qqq_1d"]
    if state == "missing":
        if os.path.exists(p):
            os.remove(p)
    elif state == "empty":
        T._w(p, "")
    elif state == "header":
        T._w(p, HEADER)
    else:
        h.bars(h.now)                                           # a healthy daily file again
        _write_5m(h.paths["qqq_5m"], _sessions_before(h.now.date(), 93))


def _run_at(h, hh, mm, ss=30):
    h.advance(et(MON.year, MON.month, MON.day, hh, mm, ss))
    return h.run()


def _alerts(h):
    with open(h.paths["monitor_state"], encoding="utf-8") as f:
        return json.load(f)["alerts"]


def _check_now(h):
    return [p for p in h.pushes if p["title"] == "QQQ book: CHECK NOW"]


# -- 1. the wording ----------------------------------------------------------------------------
def test_the_numbers_are_the_strategies_own():
    from api import cloud_signal as cs          # imported here only (1.5 s+ on the box)
    from augur_strategies import NOISE_1_0
    assert wf.DIP_MIN_SESSIONS == cs.DIP_424_PARAMS["trend_len"] + 30 == 430
    assert wf.DIP_MIN_SESSIONS == cs.CROWN_LEGS["DIP_424"]["params"]["trend_len"] + 30
    assert wf.VOL_SKIP_SESSIONS == NOISE_1_0.VOL_SKIP_REF_SESSIONS
    noise = cs.CROWN_LEGS["NOISE_382"]["strategy"]
    assert wf.VOL_SKIP_SESSIONS == cs.required_lookback_sessions(noise)
    assert wf.VOL_SKIP_FLOOR == NOISE_1_0.VOL_SKIP_LOOKBACK_SESSIONS == cs.VOL_SKIP_MIN_OBS_DEFAULT
    assert wf.FAMILY_WORDS["DIP"] == "DIP #424"


DIP_WORDS = "DIP #424 takes no new trades and sends no exit for its held shares"


@pytest.mark.parametrize("k5, want", [
    (93, DIP_WORDS + ", and NOISE's vol skip ranks on 92 sessions, not 252, until the file is back"),
    (61, DIP_WORDS + ", and NOISE's vol skip ranks on 60 sessions, not 252, until the file is back"),
    (60, DIP_WORDS + ", and NOISE's vol skip is off, until the file is back"),
    (0, DIP_WORDS + ", and NOISE's vol skip is off, until the file is back"),
    (252, DIP_WORDS + ", and NOISE's vol skip ranks on 251 sessions, not 252, until the file is "
                      "back"),
    (253, DIP_WORDS + ", until the file is back"),
    (428, DIP_WORDS + ", until the file is back"),
    (429, None),                                # 429 + today = 430: DIP runs on the 5m cache alone
    (None, DIP_WORDS + ", and NOISE's vol skip ranks on the 5-minute prices alone, until the "
                       "file is back"),
])
def test_the_trading_line_follows_the_5m_depth(k5, want):
    assert wf.qqq_1d_missing_affects(k5) == want


@pytest.mark.parametrize("state", ["missing", "empty"])
@pytest.mark.parametrize("k5", [None, 0, 40, 93, 300, 500])
def test_every_wording_is_lint_clean(state, k5):
    snap = {"qqq_1d_state": state,
            "qqq_5m_days": None if k5 is None else _sessions_before(MON, k5)}
    gone = wf.qqq_1d_gone(snap, MON)
    assert gone["k5"] == k5
    note = wf.compose_note([wf._desc({"plain": wf._plain(gone["problem"], affects=gone["affects"]),
                                      "severity": wf.HIGH})])
    assert ntfy_push.lint(note) == [], note
    assert note["message"].split("\n")[1] == {"missing": MISSING_LINE, "empty": EMPTY_LINE}[state]
    assert note["priority"] == ("default" if k5 == 500 else "high")
    # the developer words follow the same depth (status.json, the log, the PC relay)
    dev = gone["dev"]
    assert ("not ready" in dev) is (k5 is None or k5 < 429), dev
    if k5 is not None and 60 <= k5 - 1 < 252:
        assert f"ranks on {k5 - 1} of 252 sessions" in dev, dev
    else:
        assert "of 252 sessions" not in dev, dev
    if k5 == 500:
        assert "499 of 252" not in dev and "window is full" in dev and "enough for DIP" in dev
        assert "neither leg is short of history without it" in dev
    if k5 == 40:
        assert "vol skip is off (39 sessions in the 5m window, under 60)" in dev
    if k5 == 300:
        assert "records its DIP not-ready note instead of pushing it" in dev


def test_a_present_file_is_not_gone():
    assert wf.qqq_1d_gone({"qqq_1d_state": None, "qqq_5m_days": None}, MON) is None
    assert wf.qqq_1d_gone({}, MON) is None


# -- 2. once for the cause --------------------------------------------------------------------
@pytest.mark.parametrize("state, line", [("missing", MISSING_LINE), ("empty", EMPTY_LINE),
                                         ("header", EMPTY_LINE)])
def test_missing_all_day_pages_once_from_the_gate(tmp_path, state, line):
    h = _home(tmp_path, et(2026, 10, 5, 8, 30, 20), state=state)
    h.run()
    assert h.pushes == [{"title": "QQQ book: CHECK NOW", "priority": "high", "message":
                         "Trading: AFFECTED - " + DIP_WORDS + ", and NOISE's vol skip ranks on "
                         "92 sessions, not 252, until the file is back.\n"
                         + line + "\n"
                         "Do: ask Claude (PAPER-WB chat)."}]
    st = h.status()
    assert st["preopen"]["pushed"] == [wf.QQQ_1D_MISSING_ID]
    assert "QQQ_1d.csv is " + ("missing" if state == "missing" else "empty") in \
        st["preopen"]["slots"]["08:30"]["misses"][0]
    _run_at(h, 9, 15)                                           # the 09:15 slot: no repeat
    for mm in range(30, 60, 2):                                 # from the open, every 2 minutes
        _run_at(h, 9, mm)
    importlib.reload(wf)                                        # the monitor restarts
    for hh in (10, 12, 15):
        _run_at(h, hh, 0)
        _run_at(h, hh, 2)
    assert len(h.pushes) == 1, h.pushes
    rec = _alerts(h)[wf.QQQ_1D_MISSING_ID]
    assert rec["open"] is True and rec["prepushed"] is True and not rec.get("quiet")
    assert rec["plain"]["problem"] == line
    assert "the engine records its DIP not-ready and NOISE vol-window notes" in rec["detail"]
    verdicts = h.status()["verdicts"]
    assert verdicts[wf.QQQ_1D_MISSING_ID]["title"] == "QQQ daily cache " + (
        "MISSING" if state == "missing" else "EMPTY")
    assert verdicts["qqq_1d"]["ok"] is None and "qqq_1d" not in _alerts(h)  # stale: no change
    _run_at(h, 16, 12)                                          # the close: expires, no push
    assert len(h.pushes) == 1


def test_fixed_after_the_open_sends_the_one_ok_and_a_new_loss_pages_again(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 8, 30, 20))
    h.run()
    _run_at(h, 9, 40)
    _run_at(h, 9, 42)
    assert len(h.pushes) == 1 and _alerts(h)[wf.QQQ_1D_MISSING_ID]["prepushed"] is True
    _set_1d(h, None)                                            # the daily file is back
    _run_at(h, 9, 44)
    assert len(h.pushes) == 2 and h.pushes[-1]["title"] == "QQQ book: OK"
    assert h.pushes[-1]["priority"] == "low"
    assert "was: the QQQ daily price file is missing on the cloud box" in h.pushes[-1]["message"]
    assert wf.QQQ_1D_MISSING_ID not in (h.status()["preopen"].get("pushed") or [])
    _set_1d(h, "missing")                                       # and gone again: a new episode
    _run_at(h, 11, 0)
    _run_at(h, 11, 2)
    assert len(_check_now(h)) == 2 and MISSING_LINE in h.pushes[-1]["message"]
    assert not _alerts(h)[wf.QQQ_1D_MISSING_ID].get("prepushed")


def test_missing_from_mid_morning_the_session_check_is_the_one_note(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 8, 30, 20), state=None)
    h.run()
    assert [p["title"] for p in h.pushes] == ["QQQ book: OK"]
    h.advance(et(2026, 10, 5, 9, 45, 30))
    _set_1d(h, None)                                            # the 09:35 refresh landed
    h.run()
    _set_1d(h, "missing")
    _run_at(h, 10, 0)
    assert len(h.pushes) == 1                                   # debounced: 2 runs in a row
    _run_at(h, 10, 2)
    (p,) = _check_now(h)
    assert p["message"].split("\n")[1] == MISSING_LINE and ntfy_push.lint(p) == []
    for mm in (4, 6, 30):
        _run_at(h, 10, mm)
    assert len(_check_now(h)) == 1


def test_back_at_the_0915_slot_then_gone_again_pages_from_the_session_check(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 8, 30, 20))
    h.run()
    _set_1d(h, None)
    _run_at(h, 9, 15)                                           # the gate passes: "OK", and
    assert [p["title"] for p in h.pushes] == ["QQQ book: CHECK NOW", "QQQ book: OK"]
    assert "pushed" not in h.status()["preopen"]                # what it pushed is forgotten
    _set_1d(h, "missing")
    _run_at(h, 9, 40)
    _run_at(h, 9, 42)
    assert len(_check_now(h)) == 2


def test_lost_between_the_slots_the_0915_slot_pages_and_the_session_check_does_not(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 8, 30, 20), state=None)
    h.run()
    _set_1d(h, "missing")
    _run_at(h, 9, 15)
    assert len(_check_now(h)) == 1
    for mm in (40, 42, 44):
        _run_at(h, 9, mm)
    assert len(_check_now(h)) == 1 and _alerts(h)[wf.QQQ_1D_MISSING_ID]["prepushed"] is True


def test_a_gate_note_led_by_another_miss_does_not_cover_it(tmp_path):
    """A "+1 more" names nothing: the owner approves the Webull login the gate led with, the
    09:15 slot sees the same file miss (no repeat), and the 09:42 session check is the note that
    names the file and its impact -- two pushes in all, then none."""
    h = _home(tmp_path, et(2026, 10, 5, 8, 30, 20))
    h.token(status="PENDING")
    h.run()
    (p,) = h.pushes
    assert p["message"].split("\n")[1] == "The Webull login needs approval. +1 more."
    assert h.status()["preopen"]["pushed"] == ["token_status:webull_token"]
    h.token()                                                   # approved
    _run_at(h, 9, 0)
    _run_at(h, 9, 15)
    assert len(h.pushes) == 1                                   # the same file miss: no repeat
    _run_at(h, 9, 40)
    assert len(h.pushes) == 1                                   # debounced: 2 runs in a row
    _run_at(h, 9, 42)
    assert len(h.pushes) == 2
    assert h.pushes[-1]["title"] == "QQQ book: CHECK NOW"
    assert h.pushes[-1]["message"].split("\n")[:2] == [
        "Trading: AFFECTED - " + DIP_WORDS + ", and NOISE's vol skip ranks on 92 sessions, not "
        "252, until the file is back.", MISSING_LINE]
    for mm in (44, 50):
        _run_at(h, 9, mm)
    _run_at(h, 12, 0)
    assert len(h.pushes) == 2


def test_a_gate_note_the_file_leads_covers_it_with_another_miss_behind(tmp_path):
    """The file leads ("+1 more" is the token that merely expires soon): that note is the one
    page, and the session check stays silent."""
    h = _home(tmp_path, et(2026, 10, 5, 8, 30, 20))
    h.token(days_left=3)
    h.run()
    (p,) = h.pushes
    assert p["message"].split("\n")[1] == MISSING_LINE + " +1 more."
    assert h.status()["preopen"]["pushed"] == [wf.QQQ_1D_MISSING_ID]
    for mm in (15, 40, 42, 44):
        _run_at(h, 9, mm)
    assert len(h.pushes) == 1 and _alerts(h)[wf.QQQ_1D_MISSING_ID]["prepushed"] is True


def test_back_at_any_run_before_the_open_then_gone_again_pages_again(tmp_path):
    """The file is back at a run between the slots (the 09:15 slot still fails on the token
    that expires soon, so no slot passes) and gone again before 09:40: a new loss, a new note."""
    h = _home(tmp_path, et(2026, 10, 5, 8, 30, 20))
    h.token(days_left=3)
    h.run()
    assert len(_check_now(h)) == 1
    _set_1d(h, None)
    for hh, mm in ((9, 0), (9, 15), (9, 20), (9, 30)):
        _run_at(h, hh, mm)
    assert h.status()["preopen"]["pushed"] == []                # the file back: forgotten
    _set_1d(h, "missing")
    _run_at(h, 9, 36)
    for mm in (40, 42, 44):
        _run_at(h, 9, mm)
    assert len(_check_now(h)) == 2 and MISSING_LINE in _check_now(h)[-1]["message"]
    assert not _alerts(h)[wf.QQQ_1D_MISSING_ID].get("prepushed")


def test_a_stale_episode_then_the_file_gone_pages_the_new_cause(tmp_path):
    """The 09:35 refresh failed ("a day short" paged at 09:47), then the file is deleted: its
    own episode pages the true impact once; the file back fresh ends both with ONE "OK"."""
    t = et(2026, 10, 5, 9, 45, 30)
    h = T.Home(tmp_path, t)
    _write_5m(h.paths["qqq_5m"], _sessions_before(MON, 93))
    h.bars(t, d1_day=dt.date(2026, 10, 1))                      # Friday's bar not added
    h.run()
    _run_at(h, 9, 47)
    (p,) = h.pushes
    assert p["message"].split("\n")[1] == ("The QQQ daily price history was not updated this "
                                           "morning.")
    _set_1d(h, "missing")
    _run_at(h, 10, 0)
    _run_at(h, 10, 2)
    assert len(h.pushes) == 2 and h.pushes[-1]["message"].split("\n")[1] == MISSING_LINE
    alerts = _alerts(h)
    assert alerts["qqq_1d"]["open"] and alerts[wf.QQQ_1D_MISSING_ID]["open"]
    for mm in (4, 30):
        _run_at(h, 10, mm)
    assert len(h.pushes) == 2
    _set_1d(h, None)                                            # back, with Friday's bar
    _run_at(h, 10, 32)
    assert len(h.pushes) == 3 and h.pushes[-1]["title"] == "QQQ book: OK"
    assert "was: the QQQ daily price file is missing on the cloud box" in h.pushes[-1]["message"]
    assert "qqq_1d" not in _alerts(h) and wf.QQQ_1D_MISSING_ID not in _alerts(h)


def test_a_deep_enough_5m_cache_is_not_trading_affected(tmp_path):
    """500 5m sessions: DIP's series and NOISE's skip are whole without the daily file -- the
    gate's miss is a default "needs a fix", not "CHECK NOW"."""
    h = _home(tmp_path, et(2026, 10, 5, 8, 30, 20), k5=500)
    h.run()
    (p,) = h.pushes
    assert p["title"] == "QQQ book: needs a fix" and p["priority"] == "default"
    assert p["message"] == ("Trading: not affected.\n" + MISSING_LINE + "\n"
                            "Do: ask Claude (PAPER-WB chat).")


def test_the_stale_cases_keep_their_id_and_words(tmp_path):
    t = et(2026, 10, 5, 8, 30, 20)
    h = T.Home(tmp_path, t)
    h.bars(t, d1_day=dt.date(2026, 9, 30))                     # two sessions behind: a miss
    h.run()
    (p,) = h.pushes
    assert p["message"].split("\n")[:2] == [
        "Trading: AFFECTED - NOISE trades on a price history that is a day short.",
        "The QQQ daily price history is out of date."]
    assert h.status()["preopen"]["pushed"] == ["qqq_1d"]
    assert wf.QQQ_1D_MISSING_ID != "qqq_1d"


# -- 3. the file test ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    None, "", "\n\n  \n", HEADER, HEADER + "x,1,1,1,1,1\nnan,1\ninf,1\n", "﻿time,open\n",
    HEADER + "1759377600,1,1,1,1,1\n", HEADER + "1759377600,1,1,1,1,1\n17593,torn",
    "1759377600,1,1,1,1,1\n", HEADER + "abc,1\n1759377600,1,1,1,1,1\n",
])
def test_the_file_test_is_the_engines(tmp_path, text):
    from api import cloud_signal as cs
    paths = cs._paths(home=str(tmp_path))
    p = cs._cache_path("1d", paths)
    if text is not None:
        T._w(p, text)
    assert wf.qqq_1d_file_state(p) == cs.qqq_1d_missing_or_empty(paths)
    if wf.qqq_1d_file_state(p):                                 # the engine records it ->
        assert wf.last_bar_epoch(p) is None                     # this check always fails then


def test_an_unreadable_file_is_present(tmp_path):
    p = str(tmp_path / "QQQ_1d.csv")
    os.makedirs(p)
    assert wf.qqq_1d_file_state(p) is None


def test_the_5m_depth_counts_rth_sessions_and_older_backfill(tmp_path):
    days = _sessions_before(MON, 10)
    sat = dt.date(2026, 10, 3)
    eth = wf.at(days[0] - dt.timedelta(days=1), (8, 0))        # a pre-market row only
    paths = wf.default_paths(str(tmp_path / "edgelog"))
    _write_5m(paths["qqq_5m"], days + [MON], extra=[
        wf.at(sat, (10, 0)).timestamp(), eth.timestamp()])
    got = wf.five_min_session_days(paths)
    assert got == sorted(days + [MON])
    back = _sessions_before(days[0], 5)
    _write_5m(paths["qqq_5m_backfill"], back + days[:2])        # overlap rows are never added
    assert wf.five_min_session_days(paths) == sorted(back + days + [MON])
    assert wf.qqq_1d_gone({"qqq_1d_state": "missing",
                           "qqq_5m_days": wf.five_min_session_days(paths)}, MON)["k5"] == 15
    T._w(paths["qqq_5m"], HEADER)
    assert wf.five_min_session_days(paths) is None


def test_the_monitors_depth_is_the_engines(tmp_path, monkeypatch):
    """The 92 in the note is the engine's own depth_5m, with a backfill spliced in front too."""
    import pandas as pd
    from api import cloud_signal as cs
    spec = importlib.util.spec_from_file_location("q1d_stream_helpers", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_cloud_signal_stream_parity.py"))
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    monkeypatch.setattr(cs, "_VOL_WINDOW_STASH", {})
    monkeypatch.setattr(cs, "_VOL_WINDOW_NOTED", {})
    monkeypatch.setattr(cs, "_QQQ_1D_RECORDED", {})
    day = "2026-09-08"
    sessions = P._sessions(110, last=day)
    df5 = P._5m_frame(sessions, bars_per_day=12)
    first_live = sorted(set(sessions))[40]            # 40 sessions in the backfill, 70 live
    t0 = int(pd.Timestamp(f"{first_live} 00:00", tz=cs.TZ).tz_convert("UTC").timestamp())
    paths = P._home(tmp_path, df5[df5["time"] >= t0], "eng")
    df5[df5["time"] < t0].to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m_backfill.csv"),
                                 index=False)
    legs = {"NOISE_382": P._cfg(P._stub(lookback=252, vpr=True), warmup_sessions=5)}
    w = {}
    cs.step(now=P._eff("09:40", day), legs=legs, paths=paths, fetch=False, warnings=w)
    depth = w[cs.VOL_WINDOW_KEY]["NOISE_382"]["depth_5m"]
    mpaths = {"qqq_5m": cs._cache_path("5m", paths),
              "qqq_5m_backfill": os.path.join(paths["ohlc_dir"], "QQQ_5m_backfill.csv")}
    k5 = sum(1 for d in wf.five_min_session_days(mpaths) if d < dt.date(2026, 9, 8))
    assert depth == k5 - 1 == 108
    assert f"ranks on {depth} sessions, not 252" in wf.qqq_1d_missing_affects(k5)


# -- the vol_window finding says why the engine did not push ----------------------------------------
def test_the_vol_window_finding_names_a_record_only_entry(tmp_path):
    now = et(2026, 10, 5, 10, 30)
    h = T.Home(tmp_path, now)
    entry = {"day": "2026-10-05", "at": "2026-10-05T10:30:05-04:00", "need": 252, "have": 92,
             "depth_5m": 92, "bridged": 0, "short": True, "reason_key": "missing_cache",
             "reason": "daily bars missing", "text": "QQQ_1d.csv is missing or empty",
             "pushed": None, "record_only": True, "shadow": False}
    T._wj(h.paths["cs_heartbeat"], {"ts": now.isoformat(), "ok": True, "note": "",
                                    wf.VOL_WINDOW_KEY: {"NOISE_382": entry}})
    v = wf.check_vol_window(wf.collect(h.paths, h.run_cmd), now, {})[0]
    assert "Engine push: none (recorded only: QQQ_1d.csv is missing or empty, the " \
           "qqq_1d_missing check pages it)" in v["detail"]
    assert v["quiet"] is True
