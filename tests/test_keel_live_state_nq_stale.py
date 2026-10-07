"""tests/test_keel_live_state_nq_stale.py -- tools/keel_live_state.py's NQ FRESHNESS ALERT
(2026-10-05). The PC's nightly push failed 09-30, 10-01 and 10-03 (and did not run 10-02),
the box's master stayed at 09-29, and KEEL v12 rebuilt on it every night without a word.
check_nq_freshness now logs every stale run and pushes ONCE per stale trading day -- since
2026-10-07 as one plain api/ntfy_push note ("QQQ book: needs a fix", default priority).

No clock, no network, no live files: `now_et` and `push` are passed in, the marker lives in
tmp_path, and the master is a hand-built load_master()-shaped dict.
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


class _Pushes(list):
    def __call__(self, msg, title, log=print):
        self.append((title, msg))
        return True


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


# -- the alert ----------------------------------------------------------------------------
def test_the_october_incident_logs_every_run_and_pushes_once_a_day(tmp_path):
    """The box's master stuck at 09-29; the 18:30 ET timer runs Thursday 10-01, Friday
    10-02 and Monday 10-05: one push for the file, a log line every run."""
    pushes, logs = _Pushes(), []
    m = _master("2026-09-28", "2026-09-29")
    r = kls.check_nq_freshness(m, str(tmp_path), nq_file="/box/nq/NOADJ_NQ_5m_RTH.csv",
                               now_et=_et(2026, 10, 1, 18, 30), push=pushes, log=logs.append)
    assert r["stale"] and r["pushed"]
    assert r["newest"] == "2026-09-29" and r["expected"] == "2026-10-01"
    assert len(pushes) == 1
    title, msg = pushes[0]
    # the plain phone format (2026-10-07): the developer text (dates, the push script, the
    # file path) stays in the log line
    assert title == "QQQ book: needs a fix"
    assert msg == ("Trading: not affected.\n"
                   "The NQ price history on the cloud box stops at 09-29, so the KEEL sizing "
                   "model is rebuilt on old data.\n"
                   "Do: make sure the PC is on at 14:20, or ask Claude (PAPER-WB chat).")
    from api import ntfy_push
    assert ntfy_push.lint({"title": title, "message": msg,
                           "priority": kls.STALE_PUSH_PRIORITY}) == []
    assert kls.STALE_PUSH_PRIORITY == "default"
    assert any("2026-09-29" in ln and "2026-10-01" in ln and "push" in ln for ln in logs)
    assert os.path.exists(tmp_path / kls.STALE_MARKER)
    # the same stale file next night: logged again, NOT pushed again
    logs.clear()
    r = kls.check_nq_freshness(m, str(tmp_path), now_et=_et(2026, 10, 1, 22, 0),
                               push=pushes, log=logs.append)
    assert r["stale"] and not r["pushed"] and len(pushes) == 1
    assert any("STALE" in line for line in logs)
    # a NEW last completed day with the file still stuck is a new fact: one more push
    r = kls.check_nq_freshness(m, str(tmp_path), now_et=_et(2026, 10, 2, 18, 30),
                               push=pushes, log=logs.append)
    assert r["pushed"] and len(pushes) == 2


def test_current_data_is_quiet_and_clears_the_marker(tmp_path):
    pushes, logs = _Pushes(), []
    stale = _master("2026-09-29")
    kls.check_nq_freshness(stale, str(tmp_path), now_et=_et(2026, 10, 1, 18, 30), push=pushes,
                           log=logs.append)
    assert len(pushes) == 1
    fresh = _master("2026-09-30", "2026-10-01")
    r = kls.check_nq_freshness(fresh, str(tmp_path), now_et=_et(2026, 10, 1, 18, 30),
                               push=pushes, log=logs.append)
    assert not r["stale"] and len(pushes) == 1
    assert not os.path.exists(tmp_path / kls.STALE_MARKER)
    assert any("current again" in line for line in logs)
    # a later stale episode pushes again
    kls.check_nq_freshness(stale, str(tmp_path), now_et=_et(2026, 10, 1, 18, 30), push=pushes,
                           log=logs.append)
    assert len(pushes) == 2


def test_an_incomplete_last_session_is_stale_too(tmp_path):
    """A push that carried only part of the day: the build drops it, KEEL trains a day behind."""
    pushes = _Pushes()
    m = _master("2026-09-30", dropped="2026-10-01")
    r = kls.check_nq_freshness(m, str(tmp_path), now_et=_et(2026, 10, 1, 18, 30), push=pushes,
                               log=lambda *_: None)
    assert r["stale"] and len(pushes) == 1
    assert "incomplete" in pushes[0][1]


def test_a_half_day_the_build_drops_is_not_a_missing_push(tmp_path):
    pushes = _Pushes()
    m = _master("2026-11-25", dropped="2026-11-27")
    r = kls.check_nq_freshness(m, str(tmp_path), now_et=_et(2026, 11, 27, 18, 30), push=pushes,
                               log=lambda *_: None)
    assert not r["stale"] and pushes == []


def test_a_push_that_did_not_go_out_is_tried_again_next_run(tmp_path):
    """api/ntfy_push.push returns False on a failed send (it does not raise): no marker
    then, so ntfy being down at 18:30 does not silence the whole stale day."""
    sent, logs = _Pushes(), []

    def failed(msg, title, log=print):
        return False
    m = _master("2026-09-29")
    r = kls.check_nq_freshness(m, str(tmp_path), now_et=_et(2026, 10, 1, 18, 30), push=failed,
                               log=logs.append)
    assert r["stale"] and not r["pushed"]
    assert not os.path.exists(tmp_path / kls.STALE_MARKER)
    assert any("did not go out" in line for line in logs)
    r = kls.check_nq_freshness(m, str(tmp_path), now_et=_et(2026, 10, 1, 22, 0), push=sent,
                               log=logs.append)
    assert r["pushed"] and len(sent) == 1
    assert os.path.exists(tmp_path / kls.STALE_MARKER)


def test_the_check_never_raises(tmp_path):
    logs = []

    def boom(msg, title, log=print):
        raise RuntimeError("ntfy down")
    r = kls.check_nq_freshness(_master("2026-09-29"), str(tmp_path),
                               now_et=_et(2026, 10, 2, 18, 30), push=boom, log=logs.append)
    assert r["stale"]
    assert any("non-fatal" in line for line in logs)
    r = kls.check_nq_freshness({"arr": {}}, str(tmp_path), now_et=_et(2026, 10, 2, 18, 30),
                               push=_Pushes(), log=logs.append)
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
