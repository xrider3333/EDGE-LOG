"""CLOSEFETCH (api/close_fetch.py): close-anchored 1 s fetch + two-identical-reads guard."""
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

from api import close_fetch as cf
from api import market_calendar

ET = ZoneInfo("US/Eastern")
RTH_OPEN = dt.time(9, 30)


def _et(y, mo, d, h, mi, s=0.0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=ET) + dt.timedelta(seconds=s)


def _sim(close, appear_at=None, fail_at=(), last_fetch_before=None, until=60.0, step=0.25,
         guard=True, change_first=False):
    """Drive the clock + guard around one 5m close. Returns (clock, merged_at_s, calls, log).
    appear_at = seconds after close the bar shows in the REST reply (None = never)."""
    logs = []
    clock = cf.CloseFetchClock(RTH_OPEN, market_calendar, log=logs.append)
    g = cf.ProvisionalBarGuard()
    slot = int((close - dt.timedelta(minutes=5)).timestamp())
    base = 1_000_000.0
    if last_fetch_before is not None:
        clock.last_fetch_wall = base - last_fetch_before
    newest = slot - 300
    merged_at, fetch_times, reads = None, [], 0
    t = 0.0
    while t <= until:
        now_et = close + dt.timedelta(seconds=t)
        wall = base + t
        if clock.decide(now_et, wall, newest):
            fetch_times.append(t)
            if any(abs(t - f) < 1e-9 for f in fail_at):
                clock.after_fetch(False, newest, wall)
            else:
                rows = [{"time": slot - 300, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
                if appear_at is not None and t >= appear_at:
                    reads += 1
                    c = 2.0 if (change_first and reads == 1) else 3.0
                    rows.append({"time": slot, "open": 1, "high": 4, "low": 1, "close": c, "volume": 9})
                fresh = pd.DataFrame(rows)
                if guard:
                    fresh = g.filter("5m", fresh, newest, log=logs.append)
                if fresh["time"].max() >= slot and merged_at is None:
                    merged_at = t
                    newest = slot
                clock.after_fetch(True, newest, wall)
        t = round(t + step, 6)
    return clock, merged_at, fetch_times, logs


CLOSE = _et(2026, 11, 20, 10, 5)       # a Friday session


def test_merges_two_seconds_after_close_with_guard():
    clock, merged, calls, logs = _sim(CLOSE, appear_at=0.77)
    assert merged == 2.0                         # read at +1 held, +2 identical -> merged
    assert clock.state == "merged"
    assert any("CLOSEFETCH" in x and "2 fast call(s)" in x for x in logs)


def test_clock_drift_last_fetch_close_minus_1():
    _, merged, calls, _ = _sim(CLOSE, appear_at=0.77, last_fetch_before=1.0)
    assert merged == 2.0


def test_clock_drift_last_fetch_close_minus_29():
    # the 30 s clock would fire at +1 anyway; fast path merges at +2, not +31
    _, merged, calls, _ = _sim(CLOSE, appear_at=0.77, last_fetch_before=29.0)
    assert merged == 2.0


def test_missed_bar_falls_back_and_slow_clock_picks_it_up():
    clock, merged, calls, logs = _sim(CLOSE, appear_at=25.0, until=90.0)
    fast = [c for c in calls if 1.0 <= c <= 20.0]
    assert len(fast) <= cf.FAST_MAX_CALLS_PER_BAR
    assert not [c for c in calls if 20.0 < c < 49.0]   # back on the 30 s clock after +20
    assert merged is not None and merged > 20.0
    assert any("window closed" in x for x in logs)


def test_provisional_change_waits_for_two_identical():
    _, merged, calls, logs = _sim(CLOSE, appear_at=0.77, change_first=True)
    assert merged == 3.0                          # +1 (c=2) held, +2 (c=3) changed, +3 same
    assert any("provisional bar changed" in x for x in logs)


def test_429_in_window_falls_back_and_still_picked_up():
    clock, merged, calls, logs = _sim(CLOSE, appear_at=0.77, fail_at=(1.0,), until=70.0)
    assert clock.state == "fallback:fetch error"
    assert not [c for c in calls if 1.0 < c < 31.0]
    assert merged is not None and merged >= 31.0   # two slow reads
    assert any("fetch error" in x for x in logs)


def test_half_day_last_bar_is_anchored():
    close = _et(2026, 11, 27, 13, 0)              # half day: closes 13:00
    clock = cf.CloseFetchClock(RTH_OPEN, market_calendar, log=lambda *_: None)
    assert clock.fast_slot(close + dt.timedelta(seconds=1)) is not None
    assert clock.fast_slot(_et(2026, 11, 27, 13, 5, 1)) is None   # after the half-day close
    _, merged, _, _ = _sim(close, appear_at=0.77)
    assert merged == 2.0


def test_no_fast_fetch_outside_session():
    clock = cf.CloseFetchClock(RTH_OPEN, market_calendar, log=lambda *_: None)
    for when in (_et(2026, 11, 20, 9, 30, 1),     # 09:25 slot is pre-open
                 _et(2026, 11, 20, 16, 5, 1),     # after the close
                 _et(2026, 11, 26, 10, 5, 1),     # Thanksgiving
                 _et(2026, 11, 21, 10, 5, 1)):    # Saturday
        assert clock.fast_slot(when) is None
    assert clock.fast_slot(_et(2026, 11, 20, 9, 35, 1)) is not None   # first bar
    assert clock.fast_slot(_et(2026, 11, 20, 16, 0, 1)) is not None   # last bar


def test_call_count_cap():
    old = cf.FAST_STOP_S
    try:
        cf.FAST_STOP_S = 60.0                     # window long enough that the cap binds
        clock, merged, calls, logs = _sim(CLOSE, appear_at=None, until=59.0)
    finally:
        cf.FAST_STOP_S = old
    assert clock.calls == cf.FAST_MAX_CALLS_PER_BAR
    assert clock.day_calls == cf.FAST_MAX_CALLS_PER_BAR
    assert any("call cap" in x for x in logs)


def test_sleep_cap_never_skips_window():
    clock = cf.CloseFetchClock(RTH_OPEN, market_calendar, log=lambda *_: None)
    assert abs(clock.sleep_cap(_et(2026, 11, 20, 10, 4, 50)) - 11.0) < 1e-6
    assert clock.sleep_cap(_et(2026, 11, 20, 10, 5, 3)) == cf.FAST_STEP_S


def test_guard_passes_bars_already_cached():
    g = cf.ProvisionalBarGuard()
    fresh = pd.DataFrame([{"time": 100, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
    assert len(g.filter("5m", fresh, 100)) == 1
    assert len(g.filter("5m", fresh, 99)) == 0
    assert len(g.filter("5m", fresh, 99)) == 1
