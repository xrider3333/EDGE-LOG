"""api/capture_health.py - daily 10-second capture health, on synthetic CSVs (nothing real is read)."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from api import capture_health as CH

ET = ZoneInfo("America/New_York")
HEADER = "time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt\n"


def _ts(day, hh, mm, ss=0):
    return int(dt.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=ET).timestamp())


def _row(t, classified=True, rt=0):
    if classified:
        return f"{t},100,101,99,100.5,10,2,6,4,8,{rt}\n"
    return f"{t},100,101,99,100.5,10,0,0,0,0,{rt}\n"


def _write(path, day, *, prev_days=2, classified=lambda t: True, skip=lambda t: False, rt=lambda t: 0):
    """Bars for `prev_days` earlier days (full 18:00-17:00 sessions) and for `day`, end-stamped."""
    rows = [HEADER]
    d0 = day - dt.timedelta(days=prev_days)
    t = _ts(d0, 18, 0) + 10
    end = _ts(day, 17, 0)
    while t <= end:
        et = dt.datetime.fromtimestamp(t, ET)
        # the export pauses 17:00-18:00 ET
        if not (17 <= et.hour < 18) or (et.hour == 17 and et.minute == 0 and et.second == 0):
            if not skip(t):
                rows.append(_row(t, classified(t), rt(t)))
        t += 10
    path.write_text("".join(rows))


DAY = dt.date(2026, 9, 29)   # a Tuesday, normal 16:00 close


def test_clean_day(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, DAY)
    r = CH.one_instrument(str(p), DAY)
    rth = r["rth"]
    assert rth["bars"] == 2340 and rth["expected"] == 2340
    assert rth["bars_pct"] == 100.0 and rth["delta_pct"] == 100.0
    assert rth["longest_gap_min"] == 0.0 and rth["gap_start_et"] is None
    assert r["eth"]["expected"] == 8280
    assert r["eth"]["bars"] > 8000 and r["eth"]["delta_pct"] == 100.0


def test_zero_delta_day_warns(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, DAY, classified=lambda t: False)
    out = CH.capture_health(DAY, instruments=("NQ",), path_for=lambda inst: str(p))
    assert out["NQ"]["rth"]["delta_pct"] == 0.0
    assert out["NQ"]["rth"]["bars"] == 2340
    assert "delta" in out["warning"] and "0%" in out["warning"]


def test_gap_found_and_located(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    g0, g1 = _ts(DAY, 11, 0, 10), _ts(DAY, 11, 30)       # 180 bars missing: 11:00:00 to 11:30:00
    _write(p, DAY, skip=lambda t: g0 <= t <= g1, rt=lambda t: 1 if t > _ts(DAY, 15, 0) else 0)
    rth = CH.one_instrument(str(p), DAY)["rth"]
    assert rth["bars"] == 2340 - 180
    assert rth["longest_gap_min"] == 30.0
    assert rth["gap_start_et"] == "11:00"
    assert rth["rt_bars"] == 360                          # 15:00 to 16:00 flagged realtime
    # 2,160 of 2,340 is 92 percent: above the 90 percent bar, so no bars warning on its own
    assert CH.capture_health(DAY, ("NQ",), lambda i: str(p))["warning"] is None


def test_too_few_bars_warns(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    half = _ts(DAY, 12, 0)
    _write(p, DAY, skip=lambda t: t > half and t <= _ts(DAY, 16, 0))
    w = CH.capture_health(DAY, ("NQ",), lambda i: str(p))["warning"]
    assert "session bars were captured" in w and "NQ" in w


def test_partly_classified_and_other_days_excluded(tmp_path):
    p = tmp_path / "ES_10s.csv"
    # earlier days are perfect, the target day is classified only in its first half hour
    cut = _ts(DAY, 10, 0)
    _write(p, DAY, classified=lambda t: t < _ts(DAY, 0, 0) or t <= cut)
    rth = CH.one_instrument(str(p), DAY)["rth"]
    assert rth["bars"] == 2340
    assert rth["delta_pct"] == round(100.0 * 180 / 2340, 1)
    # the ETH window is 18:00 the evening before to 17:00: it must not include the day before that
    eth = CH.one_instrument(str(p), DAY)["eth"]
    assert eth["bars"] <= 8280


def test_half_day_expected_bars(tmp_path):
    day = dt.date(2026, 11, 27)                           # day after Thanksgiving, 13:00 close
    p = tmp_path / "NQ_10s.csv"
    _write(p, day)
    rth = CH.one_instrument(str(p), day)["rth"]
    assert rth["expected"] == 1260 and rth["bars"] == 1260


def test_missing_file_is_fail_soft(tmp_path):
    out = CH.capture_health(DAY, ("NQ", "ES"), lambda i: str(tmp_path / "nope.csv"))
    assert "error" in out["NQ"] and "error" in out["ES"]
    assert "unreadable" in out["warning"]


def test_empty_window_reports_zero_bars(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    p.write_text(HEADER + _row(_ts(dt.date(2026, 1, 5), 10, 0)))
    out = CH.capture_health(DAY, ("NQ",), lambda i: str(p))
    rth = out["NQ"]["rth"]
    assert rth["bars"] == 0 and rth["longest_gap_min"] == 390.0
    assert out["warning"]


def test_line_format():
    rec = {"rth": {"bars": 2331, "expected": 2340, "delta_pct": 98.3, "longest_gap_min": 1.5,
                   "gap_start_et": "10:12"}}
    assert CH.line("NQ", rec) == "10s capture NQ: 2,331/2,340 bars, delta on 98%, longest gap 1.5 min from 10:12 ET"
    assert "unavailable" in CH.line("ES", {"error": "x"})


def test_overnight_traded_but_unclassified_is_visible_without_a_warning(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    live = _ts(DAY, 8, 20)                                # the capture goes live at 08:20 ET
    _write(p, DAY, classified=lambda t: t > live)
    out = CH.capture_health(DAY, ("NQ",), lambda i: str(p))
    eth, rth = out["NQ"]["eth"], out["NQ"]["rth"]
    assert rth["delta_pct"] == 100.0 and out["warning"] is None   # the session is fine
    assert eth["delta_pct"] < 50
    assert eth["delta_from_et"] == "08:20"
    assert eth["unclassified_bars"] > 4000
    assert eth["unclassified_run_start_et"] == "18:00" and eth["unclassified_run_min"] > 600
    line = CH.line("NQ", out["NQ"])
    assert "full day delta on" in line and "split starts 08:20 ET" in line
