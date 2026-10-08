"""tests/test_keel_live_state_nq_stale.py -- tools/keel_live_state.py's NQ FRESHNESS ALERT
(2026-10-05). The PC's nightly push failed 09-30, 10-01 and 10-03 (and did not run 10-02),
the box's master stayed at 09-29, and KEEL v12 rebuilt on it every night without a word.
check_nq_freshness now logs every stale run and writes a marker (nq_stale_alert.json) with the
facts. WEBULL PUSH PLAN 10-07 (MANAGER #86): it no longer pushes -- the box monitor's nq_master
check is the one pusher of "NQ data did not reach the box" and reads the marker.

No clock, no network, no live files: `now_et` is passed in, the marker lives in tmp_path, and
the master is a hand-built load_master()-shaped dict.
"""
import datetime
import os
import sys
import zoneinfo

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.keel_live_state as kls  # noqa: E402

ET = zoneinfo.ZoneInfo("America/New_York")


def _et(y, mo, d, h, mi):
    return datetime.datetime(y, mo, d, h, mi, tzinfo=ET)


def _master(*days, dropped=None):
    """A load_master()-shaped dict whose bars end on the last of `days` (post-drop)."""
    idx = pd.DatetimeIndex([pd.Timestamp(f"{d} 15:55", tz=ET) for d in days])
    return {"arr": {"index": idx.values, "close": [1.0] * len(days)},
            "dropped_session": dropped}


def _no_push(monkeypatch):
    """WEBULL PUSH PLAN 10-07: this script never pushes -- any push fails the test."""
    from api import ntfy_push

    def boom(*a, **k):
        raise AssertionError("tools/keel_live_state.py must not push (the box monitor owns it)")
    monkeypatch.setattr(ntfy_push, "push", boom)
    monkeypatch.setattr(ntfy_push, "push_result", boom)


def _marker(tmp_path):
    import json
    with open(tmp_path / kls.STALE_MARKER, encoding="utf-8") as f:
        return json.load(f)


# -- last completed trading day ---------------------------------------------------------
def test_last_completed_session_waits_for_the_close_plus_the_push():
    # Friday 2026-10-02: before 18:00 ET Thursday is the last completed day; after, Friday
    assert kls.last_completed_session(_et(2026, 10, 2, 17, 0)) == datetime.date(2026, 10, 1)
    assert kls.last_completed_session(_et(2026, 10, 2, 18, 30)) == datetime.date(2026, 10, 2)
    # the weekend and Monday morning look back to Friday
    assert kls.last_completed_session(_et(2026, 10, 3, 11, 0)) == datetime.date(2026, 10, 2)
    assert kls.last_completed_session(_et(2026, 10, 5, 3, 0)) == datetime.date(2026, 10, 2)


def test_last_completed_session_skips_holidays_and_knows_half_days():
    # Labor Day 2026-09-07 is no session: Tuesday morning looks back to Friday 09-04
    assert kls.last_completed_session(_et(2026, 9, 8, 6, 0)) == datetime.date(2026, 9, 4)
    # day after Thanksgiving closes 13:00 -- completed from 15:00 ET
    assert kls.last_completed_session(_et(2026, 11, 27, 15, 30)) == datetime.date(2026, 11, 27)
    assert kls.last_completed_session(_et(2026, 11, 27, 14, 0)) == datetime.date(2026, 11, 25)


# -- the check (no push: WEBULL PUSH PLAN 10-07 -- tools/webull_freshness.py owns the phone) --
def test_the_october_incident_logs_every_run_and_notes_the_marker(tmp_path, monkeypatch):
    """The box's master stuck at 09-29; the 18:30 ET timer runs Thursday 10-01, Friday
    10-02: a log line every run, the marker written once per fact, NEVER a push."""
    _no_push(monkeypatch)
    logs = []
    m = _master("2026-09-28", "2026-09-29")
    r = kls.check_nq_freshness(m, str(tmp_path), nq_file="/box/nq/NOADJ_NQ_5m_RTH.csv",
                               now_et=_et(2026, 10, 1, 18, 30), log=logs.append)
    assert r["stale"] and r["noted"] and r["incomplete_day"] is None
    assert r["newest"] == "2026-09-29" and r["expected"] == "2026-10-01"
    assert "pushed" not in r
    # the developer text (dates, the push script, the file path) is in the log line
    assert any("2026-09-29" in ln and "2026-10-01" in ln and "push" in ln
               and "NOADJ_NQ_5m_RTH.csv" in ln for ln in logs)
    mk = _marker(tmp_path)
    assert (mk["newest"], mk["expected"], mk["incomplete_day"]) == ("2026-09-29", "2026-10-01",
                                                                   None)
    # the same stale file later the same night: logged again, marker unchanged
    logs.clear()
    r = kls.check_nq_freshness(m, str(tmp_path), now_et=_et(2026, 10, 1, 22, 0),
                               log=logs.append)
    assert r["stale"] and not r["noted"]
    assert any("STALE" in line for line in logs)
    # a NEW last completed day with the file still stuck: the marker moves on
    r = kls.check_nq_freshness(m, str(tmp_path), now_et=_et(2026, 10, 2, 18, 30),
                               log=logs.append)
    assert r["noted"] and _marker(tmp_path)["expected"] == "2026-10-02"


def test_current_data_is_quiet_and_clears_the_marker(tmp_path, monkeypatch):
    _no_push(monkeypatch)
    logs = []
    stale = _master("2026-09-29")
    kls.check_nq_freshness(stale, str(tmp_path), now_et=_et(2026, 10, 1, 18, 30),
                           log=logs.append)
    assert os.path.exists(tmp_path / kls.STALE_MARKER)
    fresh = _master("2026-09-30", "2026-10-01")
    r = kls.check_nq_freshness(fresh, str(tmp_path), now_et=_et(2026, 10, 1, 18, 30),
                               log=logs.append)
    assert not r["stale"]
    assert not os.path.exists(tmp_path / kls.STALE_MARKER)
    assert any("current again" in line for line in logs)
    # a later stale episode is noted again
    r = kls.check_nq_freshness(stale, str(tmp_path), now_et=_et(2026, 10, 1, 18, 30),
                               log=logs.append)
    assert r["noted"] and os.path.exists(tmp_path / kls.STALE_MARKER)


def test_an_incomplete_last_session_is_stale_and_the_marker_names_it(tmp_path, monkeypatch):
    """An upload that carried only part of the day: the build drops it, KEEL trains a day
    behind. This script's one unique view -- the marker carries it to the box monitor."""
    _no_push(monkeypatch)
    m = _master("2026-09-30", dropped="2026-10-01")
    r = kls.check_nq_freshness(m, str(tmp_path), now_et=_et(2026, 10, 1, 18, 30),
                               log=lambda *_: None)
    assert r["stale"] and r["incomplete_day"] == "2026-10-01"
    assert _marker(tmp_path)["incomplete_day"] == "2026-10-01"


def test_a_half_day_the_build_drops_is_not_a_missing_upload(tmp_path, monkeypatch):
    _no_push(monkeypatch)
    m = _master("2026-11-25", dropped="2026-11-27")
    r = kls.check_nq_freshness(m, str(tmp_path), now_et=_et(2026, 11, 27, 18, 30),
                               log=lambda *_: None)
    assert not r["stale"] and not os.path.exists(tmp_path / kls.STALE_MARKER)


def test_the_module_has_no_push_left(monkeypatch):
    """ONE ALERTER PER PROBLEM: the old sender and its phone note are gone."""
    assert not hasattr(kls, "_default_stale_push") and not hasattr(kls, "stale_note")
    import inspect
    assert "push" not in inspect.signature(kls.check_nq_freshness).parameters


def test_the_check_never_raises(tmp_path, monkeypatch):
    logs = []

    def boom(*a, **k):
        raise OSError("disk gone")
    monkeypatch.setattr(kls.os, "replace", boom)
    r = kls.check_nq_freshness(_master("2026-09-29"), str(tmp_path),
                               now_et=_et(2026, 10, 2, 18, 30), log=logs.append)
    assert r["stale"]
    assert any("non-fatal" in line for line in logs)
    r = kls.check_nq_freshness({"arr": {}}, str(tmp_path), now_et=_et(2026, 10, 2, 18, 30),
                               log=logs.append)
    assert r["stale"] is False


def test_main_runs_the_check_once_per_master_load(tmp_path, monkeypatch):
    """main() checks right after it loads the master, before building -- once per run, not
    once per leg."""
    nq = tmp_path / "NOADJ_NQ_5m_RTH.csv"
    nq.write_text("x", encoding="utf-8")
    seen = []
    legs = [{"leg_key": "A", "live": True, "version": "v12"},
            {"leg_key": "B", "live": False, "version": "v12"}]
    monkeypatch.setattr(kls, "resolve_legs", lambda: legs)
    monkeypatch.setattr(kls, "load_master", lambda f, log=print: {"m": 1})
    monkeypatch.setattr(kls, "check_nq_freshness",
                        lambda master, out_dir, nq_file=None, **k: seen.append((master, nq_file)))
    monkeypatch.setattr(kls, "build", lambda *a, **k: (None, None))
    monkeypatch.setattr(sys, "argv", ["keel_live_state.py", "--nq-file", str(nq),
                                      "--out-dir", str(tmp_path / "out")])
    kls.main()
    assert seen == [({"m": 1}, str(nq))]
