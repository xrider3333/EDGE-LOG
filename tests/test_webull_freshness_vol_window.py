"""tools/webull_freshness.py -- the vol_window:<leg> finding (VOL WINDOW GUARD, MANAGER GO
2026-10-25).

api/cloud_signal.py publishes each NOISE bridge leg's vol-skip window on its heartbeat
("vol_window": {leg: {day, need, have, short, reason_key, reason, ...}}; the shadow legs' on the
shadow heartbeat). This monitor raises a QUIET MEDIUM finding -- the engine sends the one phone
note itself -- while a fresh entry for today says the window is short, and clears it the run a
fresh entry says it is full again. A stale heartbeat, an entry from another day and a leg the
heartbeat no longer names are no change (never a false "cleared"); outside the session the check
does not run and an open episode expires with no push. Reuses the fixture home from
tests/test_webull_freshness.py. No push, no systemctl, no live file.
"""
import datetime as dt
import importlib.util
import json
import os

import pytest

from api import ntfy_push

_spec = importlib.util.spec_from_file_location(
    "webull_freshness_helpers",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_webull_freshness.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
wf = T.wf

LIVE, SHADOW = "NOISE_382", "NOISE_422_PLAIN"
KEY = f"vol_window:{LIVE}"
MON = T.MON_1030                               # Mon 2026-10-05 10:30 ET, a session day


@pytest.fixture(autouse=True)
def _no_ping(monkeypatch):
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)


def _entry(day="2026-10-05", short=True, have=92, need=252, reason_key="missing_cache",
           reason="daily bars missing", shadow=False, pushed="2026-10-05", **over):
    e = {"day": day, "at": f"{day}T09:40:05-04:00", "need": need, "have": have, "depth_5m": 92,
         "bridged": have - 92, "short": short, "reason_key": reason_key,
         "reason": reason if short else "ok", "text": "QQQ_1d.csv is missing or empty",
         "pushed": pushed if short else None, "shadow": shadow}
    e.update(over)
    return e


def _hb(h, ts, block, shadow=False):
    """The engine (or shadow) heartbeat at `ts` carrying `block` as its vol_window."""
    data = {"ts": ts.isoformat(), "ok": True, "note": "0 event(s)"}
    if block is not None:
        data[wf.VOL_WINDOW_KEY] = block
    T._wj(h.paths["shadow_heartbeat" if shadow else "cs_heartbeat"], data)


def _open(out):
    return {a["key"]: a for a in out["status"]["open_alerts"]}


def _step(h, minutes, block=None, shadow_block=None):
    """Advance the fixture box by `minutes` (every process alive), then stamp the heartbeats."""
    now = MON + dt.timedelta(minutes=minutes)
    h.advance(now)
    if block is not None:
        _hb(h, now, block)
    if shadow_block is not None:
        _hb(h, now, shadow_block, shadow=True)
    return h.run()


def test_the_key_is_the_engines():
    from api import cloud_signal as cs           # imported here only (1.5 s+ on the box)
    assert wf.VOL_WINDOW_KEY == cs.VOL_WINDOW_KEY


@pytest.mark.parametrize("off", [False, True])
def test_the_trading_line_is_the_engines(off):
    """One cause, one answer: the monitor's wording says what the engine's note says."""
    from api import cloud_signal as cs
    assert wf.vol_window_affects("NOISE", off=off) == cs.vol_window_affects("NOISE", off=off)


def test_a_live_finding_says_trading_is_affected(tmp_path):
    h = T.Home(tmp_path, MON)
    _hb(h, MON, {LIVE: _entry()})
    h.run()
    with open(h.paths["monitor_state"], encoding="utf-8") as f:
        rec = json.load(f)["alerts"][KEY]
    note = wf.compose_note([wf._desc(rec)])
    assert note["message"].split("\n")[:2] == [
        "Trading: AFFECTED - NOISE may trade, or skip, today unlike the backtest "
        "(signals still run).",
        "NOISE's vol-skip check is short today: daily bars missing - the skip ranks on 92 "
        "sessions, not 252."]
    assert note["priority"] == "default" and rec["quiet"] is True


def test_under_the_floor_the_finding_says_the_check_is_off(tmp_path):
    h = T.Home(tmp_path, MON)
    _hb(h, MON, {LIVE: _entry(have=18, reason_key="thin_overlap", min_obs=60, off=True,
                              reason="the daily bars overlap the 5-minute bars too little",
                              depth_5m=18, bridged=0)})
    out = h.run()
    rec = _open(out)[KEY]
    assert "vol skip is OFF: it has 18 sessions, under its 60-session floor" in rec["detail"]
    assert "1 session in 28" not in rec["detail"] and "skip off" in rec["title"]
    with open(h.paths["monitor_state"], encoding="utf-8") as f:
        st = json.load(f)["alerts"][KEY]
    note = wf.compose_note([wf._desc(st)])
    assert note["message"].split("\n")[:2] == [
        "Trading: AFFECTED - NOISE may trade a day the backtest skips (signals still run).",
        "NOISE's vol-skip check is off today: the daily bars overlap the 5-minute bars too "
        "little - it has 18 sessions and needs 60 to work."]
    assert ntfy_push.lint(note) == [] and h.pushes == []
    # an older engine's entry (no min_obs / off) is read as on, as before
    v = wf.check_vol_window({"cs_hb": {"ts": MON.isoformat(), wf.VOL_WINDOW_KEY: {
        LIVE: _entry(have=18)}}}, MON, {})[0]
    assert "ranks on 18 sessions, not 252" in v["detail"]


def test_no_entry_is_not_checked(tmp_path):
    h = T.Home(tmp_path, MON)
    out = h.run()
    assert "vol_window" not in out["status"]["groups_checked"]
    assert T.failing(out) == set() and h.pushes == []


def test_a_short_live_window_opens_a_quiet_finding_and_clears_without_a_push(tmp_path):
    h = T.Home(tmp_path, MON)
    _hb(h, MON, {LIVE: _entry()})
    out = h.run()
    assert KEY in T.failing(out)
    rec = _open(out)[KEY]
    assert rec["quiet"] is True and rec["severity"] == wf.MEDIUM
    assert "ranks on 92 sessions, not 252" in rec["detail"]
    assert "missing_cache" in rec["detail"] and "Engine push: 2026-10-05" in rec["detail"]
    assert h.pushes == [], "the engine sends the one note itself"

    out = _step(h, 2, {LIVE: _entry()})                        # still short: nothing new
    assert KEY in _open(out) and h.pushes == []

    out = _step(h, 4, {LIVE: _entry(short=False, have=252, reason_key="ok")})
    assert KEY not in T.failing(out) and KEY not in _open(out)
    assert [r["key"] for r in out["recovered"]] == [KEY]
    assert h.pushes == [], "no OK push: the episode was quiet"


def test_the_finding_is_held_not_cleared_while_the_engine_cannot_say(tmp_path):
    h = T.Home(tmp_path, MON)
    _hb(h, MON, {LIVE: _entry()})
    h.run()
    # yesterday's entry (today's first bar not computed yet) -- no change
    out = _step(h, 2, {LIVE: _entry(day="2026-10-02", short=False, have=252, reason_key="ok")})
    assert KEY in _open(out) and out["recovered"] == []
    # a restart: the heartbeat names no leg until the next new bar -- no change
    out = _step(h, 4, {})
    assert KEY in _open(out) and out["recovered"] == []
    out = _step(h, 6)                                          # no vol_window key at all
    assert KEY in _open(out) and out["recovered"] == []
    # a stale heartbeat (engine_hb pages that) is not trusted, even saying "full"
    h.advance(MON + dt.timedelta(minutes=8))
    _hb(h, MON + dt.timedelta(minutes=2), {LIVE: _entry(short=False, have=252, reason_key="ok")})
    out = h.run()
    assert KEY in _open(out) and out["recovered"] == []
    assert not [p for p in h.pushes if "vol-skip" in p["message"]]


def test_an_entry_for_another_day_never_opens_one(tmp_path):
    h = T.Home(tmp_path, MON)
    _hb(h, MON, {LIVE: _entry(day="2026-10-02")})
    out = h.run()
    assert KEY not in T.failing(out) and KEY not in _open(out)
    assert out["status"]["verdicts"][KEY]["ok"] is None


@pytest.mark.parametrize("now", [
    T.SAT_1200,                                    # weekend
    T.THANKSGIVING,                                # holiday
    T.et(2026, 10, 5, 9, 20),                      # before the open
    T.et(2026, 11, 27, 13, 10),                    # a half day, after its 13:00 close
])
def test_not_checked_outside_the_session(tmp_path, now):
    h = T.Home(tmp_path, now)
    _hb(h, now, {LIVE: _entry(day=now.date().isoformat())})
    out = h.run()
    assert "vol_window" not in out["status"]["groups_checked"]
    assert KEY not in T.failing(out)


def test_an_open_finding_expires_at_the_close_with_no_push(tmp_path):
    t = T.et(2026, 10, 5, 15, 58)
    h = T.Home(tmp_path, t)
    _hb(h, t, {LIVE: _entry()})
    h.run()
    h.advance(T.et(2026, 10, 5, 16, 0))
    _hb(h, h.now, {LIVE: _entry()})
    lines = []
    out = wf.run_once(h.paths, now=h.now, push_fn=h.push_fn, run_cmd=h.run_cmd, log=lines.append)
    assert [r["key"] for r in out["expired"]] == [KEY]
    assert h.pushes == []
    assert any("EXPIRED" in ln and KEY in ln for ln in lines)


def test_a_shadow_leg_is_medium_quiet_and_never_pushed(tmp_path):
    h = T.Home(tmp_path, MON)
    _hb(h, MON, {SHADOW: _entry(shadow=True, pushed=None)}, shadow=True)
    out = h.run()
    rec = _open(out)[f"vol_window:{SHADOW}"]
    assert rec["quiet"] is True and rec["severity"] == wf.MEDIUM
    assert "shadow leg, no orders" in rec["title"]
    assert h.pushes == []


def test_a_shadow_key_on_the_live_heartbeat_with_no_flag_is_still_a_shadow(tmp_path):
    h = T.Home(tmp_path, MON)
    e = _entry(pushed=None)
    del e["shadow"]
    _hb(h, MON, {SHADOW: e})
    out = h.run()
    assert "shadow leg, no orders" in _open(out)[f"vol_window:{SHADOW}"]["title"]
    assert h.pushes == []


@pytest.mark.parametrize("block", [
    "garbled", ["a", "list"], {LIVE: "not a dict"}, {LIVE: {"day": 7, "short": "maybe"}},
    {LIVE: {"day": "2026-10-05", "need": "x", "have": None}},
])
def test_a_garbled_block_never_crashes_the_check(tmp_path, block):
    h = T.Home(tmp_path, MON)
    _hb(h, MON, block)
    out = h.run()
    assert not [k for k in T.failing(out) if k.startswith("check_error")]
    assert KEY not in T.failing(out) and h.pushes == []


def test_every_wording_passes_the_phone_lint(tmp_path):
    from api import cloud_signal as cs
    h = T.Home(tmp_path, MON)
    _hb(h, MON, {LIVE: _entry()})
    _hb(h, MON, {SHADOW: _entry(shadow=True, pushed=None)}, shadow=True)
    h.run()
    with open(h.paths["monitor_state"], encoding="utf-8") as f:
        st = json.load(f)
    for key in (KEY, f"vol_window:{SHADOW}"):
        rec = st["alerts"][key]
        note = wf.compose_note([wf._desc(rec)])
        assert ntfy_push.lint(note) == [], (key, note)
    for k, w in cs._VOL_WINDOW_WORDS.items():                 # every reason the engine can name
        v = wf.check_vol_window({"cs_hb": {"ts": MON.isoformat(), wf.VOL_WINDOW_KEY: {
            LIVE: _entry(reason=w, reason_key=k)}}}, MON, {})[0]
        assert ntfy_push.lint(wf.compose_note([wf._desc(dict(v, severity=wf.MEDIUM))])) == [], k


def test_the_engines_own_entry_drives_the_finding(tmp_path):
    """The contract end to end: an entry built by api/cloud_signal's own _vol_window_entry (a
    stash record of a missing QQQ_1d.csv) opens the finding; a full one clears it."""
    from api import cloud_signal as cs
    rec = {"day": "2026-10-05", "depth_5m": 92, "bridged": 0, "need": 252,
           "reason_key": "missing_cache", "text": "QQQ_1d.csv is missing or empty",
           "at": MON.isoformat()}
    cfg = cs.CROWN_LEGS[LIVE]
    h = T.Home(tmp_path, MON)
    _hb(h, MON, {LIVE: cs._vol_window_entry(LIVE, rec, cfg)})
    out = h.run()
    assert "ranks on 92 sessions, not 252" in _open(out)[KEY]["detail"]
    full = dict(rec, bridged=170, reason_key="ok", text="170 daily session(s) at ratio 1.0000")
    out = _step(h, 2, {LIVE: cs._vol_window_entry(LIVE, full, cfg)})
    assert KEY not in _open(out) and h.pushes == []
