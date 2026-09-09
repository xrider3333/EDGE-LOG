"""The 10-second NQ feed watchdog in api/nt_heartbeat.py.

THE BUG IT EXISTS FOR (2026-09-09). NinjaTrader was healthy all session -- bridge up, all
three strategies Realtime, fills.csv fresh, the nt_heartbeat dead-man's switch green --
while its 10-second chart export had been dead since 08:39:40 ET. Nothing noticed, because
every existing watcher asks a different question: nt_recover.ps1 asks about STRATEGY state,
the bridge asks whether NinjaTrader is running, and nt_heartbeat asked whether the bridge is
still publishing. A chart indicator that silently stops writing answers "yes" to all three.

The consequence is not cosmetic: with no live NQ price the QQQ shadow book cannot mark an
open lot, so an end-of-day flatten prices the exit at the ENTRY price and writes a
fabricated round trip into the forward record the go-live decision rests on.

`evaluate_tick_feed` is pure, so the real outage can simply be replayed here.
"""
import datetime
import zoneinfo

from api import nt_heartbeat as h

NY = zoneinfo.ZoneInfo("America/New_York")


def _et(h_, m, s=0, day=9):
    return datetime.datetime(2026, 9, 9 if day == 9 else day, h_, m, s, tzinfo=NY)


def test_live_feed_is_ok():
    now = _et(10, 25)
    fresh = (now - datetime.timedelta(seconds=10)).timestamp()
    r = h.evaluate_tick_feed(fresh, now, True)
    assert r["state"] == "ok"
    assert r["alerted"] is False


def test_the_real_2026_09_09_outage_is_caught():
    # last live bar 08:39:40, looked at 10:25 -- the exact shape of the real failure
    dead = _et(8, 39, 40).timestamp()
    r = h.evaluate_tick_feed(dead, _et(10, 25), True)
    assert r["state"] == "stale"
    assert r["age_minutes"] > 100
    assert "chart export has stopped" in r["message"]
    assert r["alerted"] is False, "first sight of an outage must be free to page"


def test_alert_latches_so_one_outage_pages_once():
    dead = _et(8, 39, 40).timestamp()
    first = h.evaluate_tick_feed(dead, _et(10, 25), True)
    # publish() sets alerted=True after paging; the next cycle must carry that forward
    second = h.evaluate_tick_feed(dead, _et(10, 30), True, dict(first, alerted=True))
    assert second["state"] == "stale"
    assert second["alerted"] is True


def test_resumed_feed_clears_the_latch():
    now = _et(11, 30)
    fresh = (now - datetime.timedelta(seconds=20)).timestamp()
    r = h.evaluate_tick_feed(fresh, now, True, {"alerted": True, "state": "stale"})
    assert r["state"] == "ok"
    assert r["alerted"] is False, "a self-healed feed must not stay latched"


def test_quiet_outside_regular_hours_and_on_non_session_days():
    dead = _et(8, 39, 40).timestamp()
    # 03:00 on a session day: NQ trades, but nothing here mirrors it -- do not page
    assert h.evaluate_tick_feed(dead, _et(3, 0), True)["state"] == "idle"
    # 16:00 exactly is already outside the watched window
    assert h.evaluate_tick_feed(dead, _et(16, 0), True)["state"] == "idle"
    # a holiday/weekend, in-hours: still idle
    assert h.evaluate_tick_feed(dead, _et(10, 25), False)["state"] == "idle"


def test_missing_file_is_reported_not_swallowed():
    r = h.evaluate_tick_feed(None, _et(10, 25), True)
    assert r["state"] == "missing"
    assert "no 10s NQ feed file" in r["message"]


def test_reader_never_raises_on_a_bad_path():
    assert h.newest_tick_bar_epoch((r"C:\nope\does_not_exist.csv",)) is None


def test_reader_skips_a_header_or_torn_final_line(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    p.write_text("time,open,high,low,close,volume\n1788957580,1,2,3,4,5\nnot-a-number,\n",
                 encoding="utf-8")
    assert h.newest_tick_bar_epoch((str(p),)) == 1788957580.0
