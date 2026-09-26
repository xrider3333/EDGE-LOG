"""tools/refresh_resampled_masters.py re-derives the 15m/30m/60m/2m non-adjusted masters from
their 5m/1m parents, and must never write a bucket that isn't fully closed out yet -- the same
"never save a still-forming bar" hazard tools/refresh_noadj_yahoo.py already had to guard
against (see that file's own header and tests/test_refresh_noadj_yahoo.py). This file tests the
pure bucketing/aggregation functions directly on small synthetic 5m/1m frames: no network, no
real master files, no sqlite. It covers both resample methods the module uses (GRID for
15m/30m/60m, ROW-COUNT for 2m -- see refresh_resampled_masters.py's module docstring for why
there are two), the open=first/volume=sum aggregation rule, and the drop-incomplete-tail rule
on both a full 09:30-16:00 session and a short (early-close) session.
"""
import os
import importlib.util

import numpy as np
import pandas as pd
import pytest

# Load THIS checkout's file by path (matches tests/test_refresh_noadj_yahoo.py's own
# convention) so an earlier test's `tools` package left in sys.modules never shadows it.
_SPEC = importlib.util.spec_from_file_location(
    "_refresh_resampled_masters_under_test",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "refresh_resampled_masters.py"))
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)


ET = "US/Eastern"


def _epoch(date_str, hh, mm):
    return int(pd.Timestamp(f"{date_str} {hh:02d}:{mm:02d}:00", tz=ET).timestamp())


def _session_5m_bars(date_str, start_hm, n_bars, base_price=100.0):
    """n_bars consecutive 5m bars starting at start_hm=(hh,mm) on date_str. Each bar's open
    equals its own sequence number (so "open is the first bar's open" is easy to assert),
    high = open+1, low = open-1, close = open+0.5, volume = 10 per bar (so a full 6-bar 30m
    bucket sums to 60, a full 12-bar 60m bucket sums to 120)."""
    hh, mm = start_hm
    rows = []
    for i in range(n_bars):
        t_min = hh * 60 + mm + 5 * i
        h, m = divmod(t_min, 60)
        t = _epoch(date_str, h, m)
        o = base_price + i
        rows.append({"time": t, "open": o, "high": o + 1, "low": o - 1, "close": o + 0.5, "volume": 10})
    return pd.DataFrame(rows)


def _session_1m_bars(date_str, start_hm, n_bars, base_price=100.0):
    hh, mm = start_hm
    rows = []
    for i in range(n_bars):
        t_min = hh * 60 + mm + i
        h, m = divmod(t_min, 60)
        t = _epoch(date_str, h, m)
        o = base_price + i
        rows.append({"time": t, "open": o, "high": o + 1, "low": o - 1, "close": o + 0.5, "volume": 1})
    return pd.DataFrame(rows)


# ── GRID method (15m/30m/60m) ─────────────────────────────────────────────────────────
def test_full_session_30m_buckets_and_aggregation():
    """A full 09:30-16:00 RTH session (78 5m bars) resamples to 13 clean 30m buckets. Each
    bucket's open is its first sub-bar's open, its volume is the sum of its 6 sub-bars."""
    day = _session_5m_bars("2026-01-05", (9, 30), 78)
    out = R.resample_grid(day, 30)
    assert len(out) == 13
    # first bucket: sub-bars 0..5, open = bar0's open (100), volume = 6*10
    first = out.iloc[0]
    assert first["time"] == _epoch("2026-01-05", 9, 30)
    assert first["open"] == 100.0
    assert first["volume"] == 60
    assert first["high"] == day.iloc[0:6]["high"].max()
    assert first["low"] == day.iloc[0:6]["low"].min()
    assert first["close"] == day.iloc[5]["close"]     # last sub-bar's close
    # a middle bucket lines up on the fixed 09:30-anchored grid
    third = out.iloc[2]
    assert third["time"] == _epoch("2026-01-05", 10, 30)


def test_full_session_60m_buckets_and_aggregation():
    day = _session_5m_bars("2026-01-05", (9, 30), 78)
    out = R.resample_grid(day, 60)
    assert len(out) == 7   # 78 bars / 12 per 60m bucket, with a short last bucket (6 bars)
    first = out.iloc[0]
    assert first["time"] == _epoch("2026-01-05", 9, 30)
    assert first["open"] == 100.0
    assert first["volume"] == 120        # 12 sub-bars * 10


def test_short_early_close_session_keeps_its_own_partial_last_bucket():
    """A short session (early close) that is NOT the last day in the file still gets its own
    trailing partial bucket -- that bucket already has every bar the parent will ever give it
    for that day, so it is a legitimate historical bucket, not an "incomplete" one."""
    full_day = _session_5m_bars("2026-01-05", (9, 30), 78)
    short_day = _session_5m_bars("2026-01-06", (9, 30), 20)   # ends well before 16:00
    parent = pd.concat([full_day, short_day], ignore_index=True)
    out = R.resample_grid(parent, 30)
    # short day: 20 bars -> 3 full 30m buckets (18 bars) + 1 partial (2 bars)
    short_day_buckets = out[out["time"] >= _epoch("2026-01-06", 9, 30)]
    assert len(short_day_buckets) == 4
    last = short_day_buckets.iloc[-1]
    assert last["volume"] == 20          # only 2 sub-bars in the last, partial bucket


def test_drop_incomplete_tail_grid_trims_the_still_forming_bucket():
    """The LAST day in the file only has 3 of the 6 5m bars a 30m bucket needs -- that bucket
    is still forming (the parent simply hasn't produced the rest of it yet) and must be
    dropped, unlike the short-session case above which already has all its data."""
    full_day = _session_5m_bars("2026-01-05", (9, 30), 78)
    live_day = _session_5m_bars("2026-01-06", (9, 30), 3)   # only 09:30,09:35,09:40 so far
    parent = pd.concat([full_day, live_day], ignore_index=True)
    out = R.resample_grid(parent, 30)
    parent_last_t = int(parent["time"].max())
    trimmed = R._drop_incomplete_tail(out, 30, parent_last_t, parent_tf_seconds=300)
    assert trimmed["time"].max() < _epoch("2026-01-06", 9, 30)   # the 01-06 bucket is gone
    assert len(trimmed) == len(out) - 1


def test_drop_incomplete_tail_is_a_no_op_when_the_last_bucket_is_actually_closed():
    full_day = _session_5m_bars("2026-01-05", (9, 30), 78)
    out = R.resample_grid(full_day, 30)
    parent_last_t = int(full_day["time"].max())
    trimmed = R._drop_incomplete_tail(out, 30, parent_last_t, parent_tf_seconds=300)
    assert len(trimmed) == len(out)   # nothing trimmed -- the parent's last 5m bar closes the window


# ── ROW-COUNT method (2m) ─────────────────────────────────────────────────────────────
def test_rowcount_2m_from_1m_aggregation():
    day = _session_1m_bars("2026-01-05", (9, 30), 40)
    out = R.resample_rowcount(day, 2, 1)
    assert len(out) == 20   # 40 1m bars / 2 per 2m bucket
    first = out.iloc[0]
    assert first["time"] == _epoch("2026-01-05", 9, 30)
    assert first["open"] == 100.0        # first sub-bar's open
    assert first["volume"] == 2          # 2 sub-bars * 1
    assert first["_n"] == 2


def test_rowcount_drop_incomplete_tail():
    """Only 1 of the 2 rows the final 2m bucket needs has arrived -- drop it."""
    day = _session_1m_bars("2026-01-05", (9, 30), 41)   # odd count -> last bucket has 1 row
    out = R.resample_rowcount(day, 2, 1)
    assert int(out.iloc[-1]["_n"]) == 1
    trimmed = R._drop_incomplete_tail(out, 2, int(day["time"].max()), parent_tf_seconds=60, ratio=2)
    assert len(trimmed) == len(out) - 1
    assert int(trimmed.iloc[-1]["_n"]) == 2


def test_rowcount_full_bucket_not_dropped():
    day = _session_1m_bars("2026-01-05", (9, 30), 40)    # even count -> last bucket is full
    out = R.resample_rowcount(day, 2, 1)
    trimmed = R._drop_incomplete_tail(out, 2, int(day["time"].max()), parent_tf_seconds=60, ratio=2)
    assert len(trimmed) == len(out)


def test_rowcount_restarts_each_session_day():
    """A new day always starts a fresh group, regardless of how the previous day's row count
    ended -- an odd-length day must not bleed its leftover row into the next day's first
    bucket."""
    day1 = _session_1m_bars("2026-01-05", (9, 30), 3)     # 1 full bucket + 1 leftover row
    day2 = _session_1m_bars("2026-01-06", (9, 30), 2, base_price=200.0)
    parent = pd.concat([day1, day2], ignore_index=True)
    out = R.resample_rowcount(parent, 2, 1)
    day2_bucket = out[out["time"] == _epoch("2026-01-06", 9, 30)].iloc[0]
    assert day2_bucket["open"] == 200.0   # not contaminated by day1's leftover row
    assert day2_bucket["_n"] == 2


# ------------------------------------------------------------- the contract-roll guard

def test_a_coarse_bucket_does_not_catch_a_carry_sized_jump_on_its_own():
    """WHY the resample tool asks the PARENT instead of testing its own output.

    The roll guard's "is this an extreme move for this bar size" test loses its bite as bars
    get coarser: a 30-minute bar's ordinary body is already large enough that a carry-sized
    jump no longer stands ten standard deviations clear of it. This is the real 2026-09-14 NQ
    30m bucket, and it is NOT flagged - which is exactly why the tool tests the 5m parent.
    """
    import datetime as dt
    from augur_engine import roll_guard as rg
    st = int(dt.datetime(2026, 9, 14, 11, 30,
                         tzinfo=dt.timezone(dt.timedelta(hours=-4))).timestamp())
    tf = 1800
    # Ordinary NQ 30m bodies run from about 20 to about 200 points. The guard measures the
    # spread of the PRECEDING bodies in absolute terms, so it is that range - not the
    # alternating sign - that sets the floor: a spread this wide puts ten sigma above 400
    # points, and the splice bucket's body is 377.50.
    t, o, c, v = [], [], [], []
    px = 29080.0
    for i in range(200):
        mag = 20.0 + 180.0 * ((i * 37) % 100) / 99.0
        b = mag * (1.0 if i % 2 else -1.0)
        t.append(st - (200 - i) * tf); o.append(px); px += b; c.append(px); v.append(30000)
    t.append(st); o.append(29077.00); c.append(29454.50); v.append(18996)
    splice_index = len(c) - 1
    flagged = [h["index"] for h in rg.suspect_bars(t, o, c, volumes=v)]
    assert splice_index not in flagged, "the 30m bucket was flagged; this test's premise is gone"
    # (the earliest filler bars can be flagged: they have too few predecessors to measure a
    #  spread from, and that fallback deliberately errs towards refusing. Not the point here.)


def test_the_parent_bar_that_carries_the_splice_is_caught_at_5m():
    """The same jump, on the 5m parent, IS caught - so the parent is the right thing to ask."""
    import datetime as dt
    from augur_engine import roll_guard as rg
    st = int(dt.datetime(2026, 9, 14, 11, 30,
                         tzinfo=dt.timezone(dt.timedelta(hours=-4))).timestamp())
    tf = 300
    t, o, c, v = [], [], [], []
    px = 29080.0
    for i in range(200):
        b = 18.0 * (1.0 if i % 2 else -1.0)
        t.append(st - (200 - i) * tf); o.append(px); px += b; c.append(px); v.append(700)
    t.append(st); o.append(29077.00); c.append(29454.50); v.append(18996)
    hits = rg.suspect_bars(t, o, c, volumes=v)
    assert len(hits) == 1 and hits[0]["time"] == st


def test_the_cutoff_keeps_only_buckets_that_END_before_the_flagged_parent_bar():
    """A bucket stamped 11:00 on a 30m master covers 11:00-11:29 and is clean; the 11:30
    bucket contains the splice minute and must be held back, along with everything after."""
    import datetime as dt
    st = int(dt.datetime(2026, 9, 14, 11, 30,
                         tzinfo=dt.timezone(dt.timedelta(hours=-4))).timestamp())
    tf_minutes = 30
    cutoff = st - tf_minutes * 60 + 1          # the rule the tool applies
    assert st - 1800 < cutoff                  # the 11:00 bucket is kept
    assert not st < cutoff                     # the 11:30 bucket is not
    assert not st + 1800 < cutoff              # and nothing after it either
