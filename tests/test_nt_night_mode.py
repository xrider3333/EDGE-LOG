"""api/nt_night_mode.py - the NinjaTrader NIGHT MODE window every alerter reads (owner 2026-10-07).

Pins: when the window ends (next trading morning, weekends and holidays skipped), what "active" /
"quiet" / "covered" mean (no grace / MORNING_GRACE_MIN / BAR_GRACE_MIN), the state changes, the block
published for the cloud watchdog, the skip file, and that nt_recover.ps1 honours the same file.
The conftest fixture points every path at a temp dir, so nothing here reads the owner's real state.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys

import pytest

from api import nt_night_mode as nm

AZ = nm.LOCAL
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def az(y, m, d, hh, mm, ss=0):
    return dt.datetime(y, m, d, hh, mm, ss, tzinfo=AZ)


WED_1320 = az(2026, 10, 7, 13, 20)          # 16:20 New York, a normal Wednesday close


# -- when the window ends ----------------------------------------------------------------------------
@pytest.mark.parametrize("now,want", [
    (WED_1320, az(2026, 10, 8, 5, 45)),                       # next morning
    (az(2026, 10, 9, 13, 20), az(2026, 10, 12, 5, 45)),       # Friday -> Monday
    (az(2026, 10, 10, 9, 0), az(2026, 10, 12, 5, 45)),        # Saturday -> Monday
    (az(2026, 10, 8, 3, 0), az(2026, 10, 8, 5, 45)),          # OFF at 03:00 -> the same morning
    (az(2026, 10, 8, 5, 45), az(2026, 10, 9, 5, 45)),         # exactly at the start -> the next one
    (az(2026, 11, 25, 13, 20), az(2026, 11, 27, 5, 45)),      # the night before Thanksgiving -> Friday
    (az(2026, 12, 24, 11, 0), az(2026, 12, 28, 5, 45)),       # Christmas Eve -> past Christmas + weekend
])
def test_next_morning_start(now, want):
    assert nm.next_morning_start(now) == want


def test_morning_start_follows_the_setting(monkeypatch):
    monkeypatch.setattr(nm, "MORNING_START_LOCAL", (6, 30))
    assert nm.next_morning_start(WED_1320) == az(2026, 10, 8, 6, 30)


# -- active / quiet / covered -----------------------------------------------------------------------
def _night(since=WED_1320, until=az(2026, 10, 8, 5, 45), **kw):
    return nm.enter({}, since, until, "end of day", "eod", how="clean", flat=True, **kw)


def test_active_only_before_until_and_never_from_a_bad_file(tmp_path):
    st = _night()
    assert nm.active(st, az(2026, 10, 7, 20, 0))
    assert nm.active(st, az(2026, 10, 8, 5, 44, 59))
    assert nm.active(st, az(2026, 10, 8, 5, 45)) is None
    assert nm.active({}, WED_1320) is None
    assert nm.active({"active": {"since": "x", "until": "garbage"}}, WED_1320) is None
    # missing / unreadable file = NO night mode (the watchdog keeps working)
    assert nm.read_state() == {}
    with open(nm.STATE_PATH, "w") as fh:
        fh.write("{not json")
    assert nm.read_state() == {} and nm.active(now=WED_1320) is None


def test_quiet_adds_the_morning_grace_and_active_does_not():
    st = _night()
    t = az(2026, 10, 8, 6, 10)                                  # 25 min after the end
    assert nm.active(st, t) is None
    q = nm.quiet(st, t)
    assert q and q["active"] is False and q["end"] == az(2026, 10, 8, 5, 45)
    assert q["grace_until"] == az(2026, 10, 8, 5, 45) + dt.timedelta(minutes=nm.MORNING_GRACE_MIN)
    assert nm.quiet(st, az(2026, 10, 8, 6, 31)) is None         # grace (45 min) over
    assert nm.quiet(st, az(2026, 10, 8, 6, 31), grace_min=0) is None
    assert nm.quiet(st, az(2026, 10, 7, 13, 19)) is None        # before the window


def test_covered_marks_bars_inside_the_window_plus_bar_grace():
    st = _night()
    f = nm.covered_fn(st)
    end = az(2026, 10, 8, 5, 45).timestamp()
    assert f(WED_1320.timestamp() + 60)
    assert f(end + 9 * 60)                                       # inside BAR_GRACE_MIN (10)
    assert not f(end + 11 * 60)
    assert not f(WED_1320.timestamp() - 60)
    assert nm.covered_fn({})(WED_1320.timestamp()) is False


def test_judge_from_skips_the_closed_stretch():
    st = _night()
    start = az(2026, 10, 7, 15, 0).timestamp()                   # 18:00 New York yesterday
    end = az(2026, 10, 8, 5, 45).timestamp()
    assert nm.judge_from(start, az(2026, 10, 8, 2, 0).timestamp(), st) is None       # inside: nothing to judge
    assert nm.judge_from(start, az(2026, 10, 8, 6, 15).timestamp(), st) == int(end + 600)
    assert nm.judge_from(start, az(2026, 10, 8, 5, 50).timestamp(), st) == int(az(2026, 10, 8, 5, 50).timestamp())
    assert nm.judge_from(start, az(2026, 10, 8, 6, 15).timestamp(), {}) == int(start)


def test_enter_clear_and_history():
    st = _night()
    st = nm.clear(st, az(2026, 10, 7, 19, 0), "owner switch ON")
    assert st["active"] is None and len(st["history"]) == 1
    h = st["history"][0]
    assert h["ended"] == nm.iso(az(2026, 10, 7, 19, 0)) and "owner switch ON" in h["how"]
    # an ended-early window covers only until it really ended
    assert nm.windows(st) == [(WED_1320, az(2026, 10, 7, 19, 0))]
    assert not nm.covered_fn(st)(az(2026, 10, 7, 20, 0).timestamp())
    for i in range(nm.HISTORY_KEEP + 5):
        s = az(2026, 9, 1, 13, 0) + dt.timedelta(days=i)
        st = nm.enter(st, s, s + dt.timedelta(hours=16), "end of day", "eod")
    assert len(st["history"]) == nm.HISTORY_KEEP


def test_public_state_is_what_the_cloud_watchdog_reads():
    st = _night(position=["ENGU-Q's NQ trade"])
    pub = nm.public_state(st, az(2026, 10, 7, 17, 40))
    assert pub["active"] is True and pub["until_hhmm"] == "05:45" and pub["position_open"] is True
    assert nm.to_local(pub["grace_until"]) == az(2026, 10, 8, 6, 30)
    json.dumps(pub)                                              # Firestore-safe
    assert nm.public_state({}, WED_1320) == {"active": False}
    later = nm.public_state(st, az(2026, 10, 8, 7, 0))
    assert later["active"] is False and later["until"] == nm.iso(az(2026, 10, 8, 5, 45))


def test_skip_file_is_one_night_and_goes_stale():
    assert nm.skip_pending(WED_1320) == (False, "")
    with open(nm.SKIP_PATH, "w") as fh:
        fh.write("keep it on tonight")
    ok, note = nm.skip_pending()
    assert ok and note == "keep it on tonight"
    old = dt.datetime.now().timestamp() - (nm.SKIP_MAX_AGE_H + 1) * 3600
    os.utime(nm.SKIP_PATH, (old, old))
    ok, note = nm.skip_pending()
    assert not ok and "stale" in note


def test_every_owner_setting_is_at_the_top():
    src = open(nm.__file__, encoding="utf-8").read()
    head = src[src.index("OWNER SETTINGS"):src.index("LIVE_ACCOUNT =")]
    for name in ("ENABLED", "EOD_START_ET", "MORNING_START_LOCAL", "BACKFILL_GIVE_UP_MIN", "BACKFILL_RETRY_MIN",
                 "FILLS_WAIT_MIN", "MORNING_GRACE_MIN", "BAR_GRACE_MIN", "CLOUD_NIGHT_PUSH", "QUIET_SECONDS"):
        assert "\n%s = " % name in head, name
    assert nm.CLOUD_NIGHT_PUSH in ("silent", "low")


# -- nt_recover.ps1 reads the same file ---------------------------------------------------------------
PS1 = os.path.join(ROOT, "tools", "nt_recover.ps1")


def test_nt_recover_checks_night_mode_before_it_does_anything():
    s = open(PS1, encoding="utf-8").read()
    i_night = s.index("$nightUntil = NightModeUntil")
    assert s.index("$pausePath = 'C:\\EdgeLog\\nt_recover.PAUSE'") < i_night < s.index('Log "=== recover start')
    assert "$nightPath = 'C:\\EdgeLog\\nt_night_mode.json'" in s
    # re-checked right before a launch, in case night mode began during the pass
    login = s.index("& powershell -ExecutionPolicy Bypass -File $loginPs1")
    assert s.rindex("if (NightModeUntil)", 0, login) > s.index("# ── 2. log in / launch if needed")


def _ps_night_until(tmp_path, content):
    """Run nt_recover.ps1's own NightModeUntil function against a temp file."""
    s = open(PS1, encoding="utf-8").read()
    fn = s[s.index("function NightModeUntil {"):s.index("$nightUntil = NightModeUntil")]
    p = tmp_path / "nm.json"
    if content is not None:
        p.write_text(content, encoding="utf-8")
    script = tmp_path / "t.ps1"
    script.write_text("$nightPath = '%s'\n%s\n$u = NightModeUntil\nif ($u) { 'ACTIVE' } else { 'NONE' }\n"
                      % (str(p), fn), encoding="utf-8")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, text=True, timeout=90)
    return (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else r.stderr


@pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell"), reason="Windows PowerShell only")
def test_nt_recover_function_reads_the_window(tmp_path):
    now = dt.datetime.now(AZ)
    fut = nm.enter({}, now - dt.timedelta(hours=1), now + dt.timedelta(hours=3), "end of day", "eod")
    past = nm.enter({}, now - dt.timedelta(hours=9), now - dt.timedelta(minutes=1), "end of day", "eod")
    assert _ps_night_until(tmp_path, json.dumps(fut)) == "ACTIVE"
    assert _ps_night_until(tmp_path, json.dumps(past)) == "NONE"
    assert _ps_night_until(tmp_path, json.dumps({"active": None, "history": []})) == "NONE"
    assert _ps_night_until(tmp_path, "{garbage") == "NONE"
    assert _ps_night_until(tmp_path, None) == "NONE"


def test_eod_safe_repo_copy_points_at_the_shared_checkout():
    s = open(os.path.join(ROOT, "tools", "nt_eod_safe.ps1"), encoding="utf-8").read()
    assert "$cli     = 'C:\\Users\\xride\\OneDrive\\Desktop\\EDGE-LOG\\tools\\nt_bridge.py'" in s
    assert "EdgeLog-worktrees\\paper" not in s
    assert "exit 2" in s and "exit 1" in s and "Stop-Process" not in s   # it never kills, never flattens
    assert "flatten" not in s.split("param([switch]$WhatIf)")[1].lower()


def test_bridge_doc_carries_the_night_block(monkeypatch):
    from api import nt_bridge_pub, nt_watchdog
    written = {}

    class Ref:                                            # db.collection().document().collection().document().set()
        def __init__(self, name=""):
            self.name = name

        def collection(self, name):
            return Ref(name)

        def document(self, name):
            return Ref(name)

        def set(self, data):
            written[self.name] = data

    monkeypatch.setattr(nt_bridge_pub, "snapshot", lambda: {"checked_at": "2026-10-08 00:00:00", "up": False})
    monkeypatch.setattr(nt_watchdog, "state", lambda *a, **k: {"ok": True, "enabled": True})
    nm.write_state(_night())
    nt_bridge_pub.publish(Ref(), "uid")
    blk = written["nt_bridge"]["night_mode"]
    assert blk["until"] == nm.iso(az(2026, 10, 8, 5, 45)) and "grace_until" in blk
