r"""The split detector on EXTENDED-HOURS frames, and TBIS's volume test (2026-10-05).

THE DEFECT THIS FIXES WAS FOUND BY TBIS's QA PASS over every real cache, and it is the reason the
guard never went to main. "Overnight" used to mean the last bar of one ET date over the first bar
of the next. On an RTH frame that IS the regular close and open, so GE's 1-for-8 fired at 8.06x.
On an EXTENDED-HOURS frame it means the AFTER-HOURS close (17:50) over the PREMARKET open (04:30),
which reads 7.80x - outside the 2% window around 8, so the split was MISSED. A guard that misses
on exactly the frames the lanes pull is worse than no guard.

The fix measures REGULAR SESSION CLOSE to the NEXT REGULAR SESSION OPEN. That is the basis a split
is actually quoted against, and the only boundary that means the same thing on both frames.

THE VOLUME TEST IS OPT-IN, and that is a safety decision rather than a default. A real split
changes the share count, so volume scales by about 1/price_ratio and price_ratio x volume_ratio
lands near 1; on siporb's daily cache that cuts 369 whole-ratio flags to 64. But the WRITE guard
must stay strict: a false refusal costs the caller a look, while a false accept once wrote a fake
+$139k trade. So a scan opts in; upsert_master does not.
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import import_alpaca_stocks as alp  # noqa: E402

DAY = 86400
BASE = 1627862400          # 2021-08-02 00:00 UTC; ET = UTC-4 in August


def _bar(day_off, hh, mm, o, c, v=1_000_000):
    return {"time": BASE + day_off * DAY + (hh + 4) * 3600 + mm * 60,
            "open": o, "high": max(o, c), "low": min(o, c), "close": c, "volume": v}


def _eth_split_frame(new_open=104.48, pre_old=13.30, post_pre=104.30, vol_scales=True):
    """A reverse split on an EXTENDED-HOURS frame, shaped like GE's real one.

    The regular-session numbers give the true ratio; the premarket and after-hours bars are what
    made the old last-bar-to-first-bar rule read 7.80x and miss.
    """
    # GE's real numbers: a 12.95 regular close, then a 104.48 regular open (8.068x). The 13.30
    # after-hours close and 104.30 premarket open are what made the old boundary read 7.80x.
    old_close = 12.95
    rows = []
    for i in range(-20, 0):
        vb = 8_000_000 if vol_scales else 1_000_000
        rows.append(_bar(i, 4, 30, 12.80, 12.85, vb // 9))
        rows.append(_bar(i, 9, 30, 12.90, 12.92, vb))
        rows.append(_bar(i, 15, 30, 12.93, old_close, vb))
        rows.append(_bar(i, 17, 50, pre_old, pre_old + 0.07, vb // 7))
    for i in range(0, 20):
        va = (8_000_000 // 8) if vol_scales else 1_000_000
        rows.append(_bar(i, 4, 30, post_pre, post_pre + 0.05, va // 9))
        rows.append(_bar(i, 9, 30, new_open, new_open + 0.12, va))
        rows.append(_bar(i, 15, 30, new_open - 1.0, new_open - 0.88, va))
        rows.append(_bar(i, 17, 50, new_open - 0.88, new_open - 0.78, va // 7))
    return pd.DataFrame(rows)


def _naive_ratio(df, when="2021-08-02"):
    """What the OLD rule saw: last bar of one ET date over the first bar of the next."""
    d = df.sort_values("time").reset_index(drop=True)
    et = pd.to_datetime(d["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    day = et.dt.strftime("%Y-%m-%d")
    for i in range(1, len(d)):
        if day.iloc[i] != day.iloc[i - 1] and day.iloc[i] == when:
            return float(d["open"].iloc[i]) / float(d["close"].iloc[i - 1])
    return None


# ═══════════════════════════════════════════════ the ETH boundary
def test_the_old_boundary_really_did_miss_it():
    """Pin the defect itself, so the fix cannot be mistaken for a test that always passed. These
    numbers reproduce TBIS's measurement: 7.80x on the extended-hours boundary."""
    df = _eth_split_frame()
    naive = _naive_ratio(df)
    assert 7.7 < naive < 7.9, naive
    assert abs(naive - 8.0) / 8.0 > 0.02, \
        "if the naive ratio were inside the 2% window there would be nothing to fix"


def test_a_split_on_an_extended_hours_frame_is_caught():
    hits = alp.split_like_gaps(_eth_split_frame())
    days = [h[0] for h in hits]
    assert "2021-08-02" in days, "the ETH frame still misses the split: %r" % (hits,)
    hit = [h for h in hits if h[0] == "2021-08-02"][0]
    assert 8.0 < hit[1] < 8.2, hit
    assert hit[3] == "8:1"


def test_the_regular_session_ratio_is_what_gets_reported():
    """Not the premarket number - a reader comparing the report against a split table needs the
    ratio the split was quoted at."""
    hit = [h for h in alp.split_like_gaps(_eth_split_frame()) if h[0] == "2021-08-02"][0]
    assert abs(hit[1] - 8.068) < 0.01, hit[1]


def test_premarket_noise_alone_never_raises_a_flag():
    """A wild premarket print with a normal regular session is not a split, and used to be
    exactly what the old boundary would read."""
    rows = []
    for i in range(-10, 10):
        rows.append(_bar(i, 4, 30, 1.00, 1.00, 500))        # a nonsense premarket tick
        rows.append(_bar(i, 9, 30, 100.00, 100.50))
        rows.append(_bar(i, 15, 30, 100.50, 100.80))
    assert alp.split_like_gaps(pd.DataFrame(rows)) == []


def test_an_after_hours_only_day_is_skipped_not_guessed():
    """A day with no regular-session bar cannot be a boundary, so it must not become one."""
    rows = []
    for i in range(-5, 0):
        rows.append(_bar(i, 9, 30, 100.0, 100.2))
        rows.append(_bar(i, 15, 30, 100.2, 100.4))
    rows.append(_bar(0, 17, 50, 12.5, 12.6))                # holiday-ish: after hours only
    for i in range(1, 5):
        rows.append(_bar(i, 9, 30, 100.4, 100.6))
        rows.append(_bar(i, 15, 30, 100.6, 100.8))
    assert alp.split_like_gaps(pd.DataFrame(rows)) == []


def test_an_early_close_day_uses_its_real_close():
    """On a 13:00 half-day the 15:30 prints are extended hours, so the regular close is the
    13:00 one. EARLY_CLOSE_DATES already lists these for rth_filter."""
    assert "2021-11-26" in alp.EARLY_CLOSE_DATES
    base = int(pd.Timestamp("2021-11-26 00:00", tz="US/Eastern").timestamp())
    rows = []
    for i in range(-6, 0):
        rows.append({"time": base + i * DAY + 10 * 3600, "open": 12.90, "high": 12.95,
                     "low": 12.85, "close": 12.95, "volume": 1_000_000})
    # the half-day: a regular bar at 12:30, then an extended-hours print at 15:30
    rows.append({"time": base + 12 * 3600 + 30 * 60, "open": 12.95, "high": 13.0,
                 "low": 12.9, "close": 12.98, "volume": 900_000})
    rows.append({"time": base + 15 * 3600 + 30 * 60, "open": 103.0, "high": 104.0,
                 "low": 102.0, "close": 103.6, "volume": 90_000})
    df = pd.DataFrame(rows)
    # the 15:30 print is NOT the close of a 13:00 day, so it must not become a boundary
    for day, _r, _n, _nm in alp.split_like_gaps(df):
        assert day != "2021-11-26", "an early-close day used an extended-hours bar as its close"


# ═══════════════════════════════════════════════ no regression on the RTH path
def test_an_rth_only_frame_still_fires():
    """The frames the guard already handled must behave exactly as before."""
    rows = []
    for i in range(-10, 0):
        rows.append(_bar(i, 9, 30, 12.90, 12.92))
        rows.append(_bar(i, 15, 30, 12.93, 12.95))
    for i in range(0, 10):
        rows.append(_bar(i, 9, 30, 104.48, 104.60))
        rows.append(_bar(i, 15, 30, 103.50, 103.60))
    hits = alp.split_like_gaps(pd.DataFrame(rows))
    assert [h[0] for h in hits] == ["2021-08-02"], hits


def test_a_frame_with_one_session_is_not_a_boundary():
    rows = [_bar(0, 9, 30, 100.0, 100.5), _bar(0, 15, 30, 100.5, 101.0)]
    assert alp.split_like_gaps(pd.DataFrame(rows)) == []


def test_an_empty_frame_is_still_empty():
    assert alp.split_like_gaps(pd.DataFrame()) == []
    assert alp.split_like_gaps(None) == []


# ═══════════════════════════════════════════════ TBIS's volume test
def test_the_volume_test_is_off_by_default_so_the_write_guard_stays_strict():
    """A false refusal costs the caller a look; a false accept wrote a fake +$139k trade. The
    direction of that trade-off is the whole point."""
    import inspect
    p = inspect.signature(alp.split_like_gaps).parameters
    assert p["require_volume"].default is False


def test_a_real_split_passes_the_volume_test():
    """Volume scales by about 1/price_ratio, so the product lands near 1."""
    hits = alp.split_like_gaps(_eth_split_frame(vol_scales=True), require_volume=True)
    assert "2021-08-02" in [h[0] for h in hits]


def test_a_price_move_with_unchanged_volume_is_filtered_out():
    """THE FALSE POSITIVE THE TEST EXISTS FOR. Price up 8x with the share count untouched is not
    a split, whatever the ratio looks like."""
    hits = alp.split_like_gaps(_eth_split_frame(vol_scales=False), require_volume=True)
    assert "2021-08-02" not in [h[0] for h in hits]
    # ...and the price test alone still sees it, so the filter is what changed, not the detector
    assert "2021-08-02" in [h[0] for h in
                            alp.split_like_gaps(_eth_split_frame(vol_scales=False))]


def test_the_volume_window_is_a_median_not_a_single_day():
    """One heavy day either side must not decide it."""
    assert alp.SPLIT_VOLUME_SESSIONS >= 20


def test_the_volume_tolerance_is_the_measured_one():
    """1.6x of 1 is TBIS's constant, chosen on 369 real flags - not a round number."""
    assert alp.SPLIT_VOLUME_TOL == 1.6


def test_a_frame_with_no_volume_column_falls_back_to_the_price_test():
    """Missing volume must not silently turn the guard off."""
    df = _eth_split_frame().drop(columns=["volume"])
    hits = alp.split_like_gaps(df, require_volume=True)
    assert "2021-08-02" in [h[0] for h in hits]


def test_zero_volume_does_not_divide_by_zero():
    df = _eth_split_frame()
    df["volume"] = 0
    alp.split_like_gaps(df, require_volume=True)      # must simply not raise


# ═══════════════════════════════════════════════ against the real cache
REAL_GE = r"C:\EdgeLog\alpaca_cache\ttm_r20c\GE_30m_split_rth.csv"


@pytest.mark.skipif(not os.path.exists(REAL_GE), reason="the unadjusted GE cache is not on this box")
def test_the_real_unadjusted_GE_cache_still_fires():
    """The actual defect, on the actual bars that booked the fake +$139k trade."""
    hits = alp.split_like_gaps(pd.read_csv(REAL_GE))
    assert [h[0] for h in hits] == ["2021-08-02"], hits
    assert 8.0 < hits[0][1] < 8.2


# ═══════════════════════════════════════════════ DAILY frames (TBIS #76, 2026-10-07)
def _daily_frame(clock="00:00", new_open=104.48, vol_scales=True, n=20):
    """A reverse split on a DAILY series, stamped at one clock time like a 1D master.

    Alpaca's 1D library masters stamp every bar 00:00 ET, which is outside the regular session -
    so the session-boundary rule found no bar on any date and skipped every day.
    """
    # GE's real numbers again: 12.95 regular close, 104.48 next open (8.068x)
    old_close = 12.95
    base = int(pd.Timestamp("2021-07-01 " + clock, tz="US/Eastern").timestamp())
    rows = []
    for i in range(-n, 0):
        vb = 8_000_000 if vol_scales else 1_000_000
        rows.append({"time": base + i * DAY, "open": 12.90, "high": 13.00, "low": 12.80,
                     "close": old_close, "volume": vb})
    for i in range(0, n):
        va = 1_000_000 if vol_scales else 1_000_000
        rows.append({"time": base + i * DAY, "open": new_open, "high": new_open + 1,
                     "low": new_open - 1.5, "close": new_open - 0.88, "volume": va})
    return pd.DataFrame(rows)


def test_a_midnight_stamped_daily_master_is_no_longer_invisible():
    """THE DEFECT TBIS FOUND, and it was mine: every 1D library master was skipped entirely, so
    one holding a missed split passed upsert_master without a word."""
    hits = alp.split_like_gaps(_daily_frame("00:00"))
    assert [h[0] for h in hits] == ["2021-07-01"], hits
    assert 8.0 < hits[0][1] < 8.2
    assert hits[0][3] == "8:1"


def test_the_daily_shape_is_detected_rather_than_assumed():
    """A frame is treated as daily because of its SHAPE - one clock time for every bar, outside
    the regular session - not because a caller said so."""
    assert alp._is_daily_frame([0, 0, 0, 0]) is True
    assert alp._is_daily_frame([17 * 60 + 50] * 6) is True       # an after-hours daily stamp
    assert alp._is_daily_frame([]) is False
    assert alp._is_daily_frame([9 * 60 + 30] * 5) is False       # inside the session: not daily
    assert alp._is_daily_frame([0, 0, 570, 0]) is False          # mixed: an intraday frame


def test_an_intraday_frame_with_one_stray_premarket_day_is_untouched():
    """WHY THE DETECTOR IS NARROW. Re-stamping every row to midday - fine for a scan that owns
    its data - would promote this stray premarket-only day into a session boundary and could
    invent a gap. The intraday path must be unchanged by the daily fix."""
    rows = []
    for i in range(-6, 0):
        rows.append(_bar(i, 9, 30, 100.0, 100.2))
        rows.append(_bar(i, 15, 30, 100.2, 100.4))
    rows.append(_bar(0, 4, 30, 12.5, 12.6))              # premarket only, a nonsense print
    for i in range(1, 6):
        rows.append(_bar(i, 9, 30, 100.4, 100.6))
        rows.append(_bar(i, 15, 30, 100.6, 100.8))
    assert alp.split_like_gaps(pd.DataFrame(rows)) == []


def test_a_daily_frame_stamped_inside_the_session_still_works():
    """TBIS's scan re-stamps to 12:00 ET before calling in. That lands inside the regular session,
    so it goes down the ordinary path - and must give the same answer."""
    hits = alp.split_like_gaps(_daily_frame("12:00"))
    assert [h[0] for h in hits] == ["2021-07-01"], hits


def test_the_volume_test_still_discriminates_on_a_daily_frame():
    """The daily fix must not weaken the filter: a real split passes, a price move with an
    unchanged share count does not."""
    assert "2021-07-01" in [h[0] for h in
                            alp.split_like_gaps(_daily_frame("00:00", vol_scales=True),
                                                require_volume=True)]
    assert "2021-07-01" not in [h[0] for h in
                                alp.split_like_gaps(_daily_frame("00:00", vol_scales=False),
                                                    require_volume=True)]


def test_a_clean_daily_frame_raises_nothing():
    """A daily series with no split must stay silent - the fix opens a path, it does not lower
    the bar."""
    base = int(pd.Timestamp("2021-07-01 00:00", tz="US/Eastern").timestamp())
    rows = [{"time": base + i * DAY, "open": 100.0 + i * 0.1, "high": 101.0 + i * 0.1,
             "low": 99.0 + i * 0.1, "close": 100.5 + i * 0.1, "volume": 1_000_000}
            for i in range(-20, 20)]
    assert alp.split_like_gaps(pd.DataFrame(rows)) == []
