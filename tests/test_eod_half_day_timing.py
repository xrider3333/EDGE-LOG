"""EOD audit G7 (2026-10-14, MANAGER #155): the executor's EOD summary and the box monitor's EOD
checks follow the session close -- 16:05 / 16:10 on a normal day, 13:05 / 13:10 on a recognised
half day (the first is 2026-11-27) -- instead of a fixed 16:05 / 16:10 that came ~3 h late.
"""
import datetime as _dt
import os
import sys
from zoneinfo import ZoneInfo

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import market_calendar as mc  # noqa: E402
from api import qqq_exec as qe  # noqa: E402
from tools import webull_freshness as wf  # noqa: E402

NY = ZoneInfo("America/New_York")
HALF = _dt.date(2026, 11, 27)
FULL = _dt.date(2026, 11, 25)


def _at(d, hh, mm):
    return _dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY)


def test_the_dates_are_what_the_tests_assume():
    assert mc.is_session(HALF) and mc.session_close_et(HALF) == "13:00"
    assert mc.is_session(FULL) and mc.session_close_et(FULL) == "16:00"


def test_the_eod_summary_goes_five_minutes_after_the_close():
    assert qe._eod_summary_from(_at(FULL, 12, 0)) == (16, 5)
    assert qe._eod_summary_from(_at(HALF, 12, 0)) == (13, 5)


def test_the_eod_summary_time_falls_back_to_1605_on_any_doubt(monkeypatch):
    def boom(d):
        raise RuntimeError("no calendar")
    monkeypatch.setattr(qe.market_calendar, "session_close_et", boom)
    assert qe._eod_summary_from(_at(HALF, 12, 0)) == (16, 5)


def test_the_monitor_eod_checks_start_ten_minutes_after_the_close():
    assert wf.eod_check_from(FULL) == (16, 10) == wf.EOD_CHECK_FROM
    assert wf.eod_check_from(HALF) == (13, 10)


def test_check_eod_is_quiet_before_and_active_after_on_a_half_day():
    snap = {"exec_state": {}}
    assert wf.check_eod(snap, _at(HALF, 13, 9)) is None
    out = wf.check_eod(snap, _at(HALF, 13, 11))
    assert out, "13:11 on a half day: the EOD checks run"
    assert any("eod_summary" in str(v) for v in out)


def test_check_eod_keeps_1610_on_a_normal_day():
    snap = {"exec_state": {}}
    assert wf.check_eod(snap, _at(FULL, 16, 9)) is None
    assert wf.check_eod(snap, _at(FULL, 13, 11)) is None
    assert wf.check_eod(snap, _at(FULL, 16, 11))
