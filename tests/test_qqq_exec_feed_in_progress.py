"""feed_days: today before 16:10 ET is in progress (valid None), never judged on the full day."""
import datetime as dt
from zoneinfo import ZoneInfo

from api import qqq_exec as qe

ET = ZoneInfo("America/New_York")


def _st(ticks, first="09:25", last="11:16"):
    return {"feed_days": {"2026-11-20": {"ticks": ticks, "stale_ticks": 0,
                                         "first_tick_et": first, "last_tick_et": last}}}


def test_midday_healthy_day_is_in_progress_not_invalid():
    now = dt.datetime(2026, 11, 20, 11, 16, tzinfo=ET)
    so_far = int((now - now.replace(hour=9, minute=25)).total_seconds() / qe.TICK_SEC)
    d = qe._build_feed_days(_st(so_far), now_et=now)[-1]
    assert d["valid"] is None and d["in_progress"] is True
    assert "in progress" in d["note"] and "missing" not in d["note"]
    assert "absent" not in d["note"]


def test_midday_gap_so_far_is_named():
    now = dt.datetime(2026, 11, 20, 11, 16, tzinfo=ET)
    d = qe._build_feed_days(_st(100), now_et=now)[-1]
    assert d["valid"] is None and "missing so far" in d["note"]


def test_after_1610_the_day_is_judged():
    now = dt.datetime(2026, 11, 20, 16, 10, tzinfo=ET)
    good = qe._build_feed_days(_st(4668, last="16:05"), now_et=now)[-1]
    assert good["valid"] is True and good["in_progress"] is False
    bad = qe._build_feed_days(_st(1300, last="16:05"), now_et=now)[-1]
    assert bad["valid"] is False and "adapter absent" in bad["note"]


def test_past_day_judged_any_time():
    now = dt.datetime(2026, 11, 23, 10, 0, tzinfo=ET)
    d = qe._build_feed_days(_st(1300), now_et=now)[-1]
    assert d["valid"] is False and d["in_progress"] is False


def test_half_day_gap_stops_counting_at_1300():
    # 2026-11-27 = half day (13:00 close); full half-session of ticks, read at 15:00
    now = dt.datetime(2026, 11, 27, 15, 0, tzinfo=ET)
    full = int((now.replace(hour=13, minute=0) - now.replace(hour=9, minute=25)).total_seconds()
               / qe.TICK_SEC)
    st = {"feed_days": {"2026-11-27": {"ticks": full, "stale_ticks": 0,
                                       "first_tick_et": "09:25", "last_tick_et": "13:05"}}}
    d = qe._build_feed_days(st, now_et=now)[-1]
    assert d["in_progress"] is True and "missing" not in d["note"]


def test_readiness_mean_skips_in_progress_day():
    days = [{"valid": True, "uptime_pct": 1.0}] * 9 + [
        {"valid": None, "uptime_pct": 0.27, "in_progress": True}]
    out = qe._build_readiness(days, {"checked": 0, "failed": 0}, {"total": 0}, {"events": []})
    assert out["uptime_mean_10"] == 1.0
