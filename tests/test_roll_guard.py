"""The refresh must refuse to glue two contracts into one bar (December 2026 roll).

The two bars this guard exists for are real and are reproduced here from the masters,
via ROLL_AUDIT.md section 2.7:

    2026-06-15 03:30 ET  NQ 1m 24h   open 30,252.00 close 30,545.75  volume 13,914
    2026-06-15 05:30 ET  ES 1m 24h   open  7,521.50 close  7,586.50  volume  3,323
    2026-09-14 11:30 ET  NQ 1m       open 29,077.00 close 29,381.50  volume  8,361
    2026-09-14 11:30 ET  NQ 5m RTH   open 29,077.00 close 29,454.50  volume 18,996
    2026-09-14 11:30 ET  ES 5m RTH   open  7,612.00 close  7,691.50  volume 64,789

The tests that matter are the two directions: every one of those bars is caught, and
the events that merely LOOK like rolls are not - the weekend gaps of 2026-06-14 18:10
and 2026-09-13 18:10, and ordinary bars outside expiry week.
"""
import datetime as dt
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import roll_guard as rg  # noqa: E402

ET = dt.timezone(dt.timedelta(hours=-4))       # June and September are UTC-4
EST = dt.timezone(dt.timedelta(hours=-5))      # December is UTC-5


def _stamp(y, m, d, hh, mm, tz=ET):
    return int(dt.datetime(y, m, d, hh, mm, tzinfo=tz).timestamp())


def _calm_series(n, price, body, tf_s, first_time):
    """n ordinary bars: a small alternating body, so the spread is realistic and > 0."""
    times, opens, closes, vols = [], [], [], []
    px = float(price)
    for i in range(n):
        b = body * (1.0 if i % 2 else -1.0) * (0.6 + 0.4 * ((i * 7) % 5) / 4.0)
        times.append(first_time + i * tf_s)
        opens.append(px)
        px = px + b
        closes.append(px)
        vols.append(500 + (i % 11) * 30)
    return times, opens, closes, vols


def _with_splice(price, body_calm, tf_s, splice_time, splice_open, splice_close,
                 splice_vol, n_prior=120):
    """A calm run of bars ending exactly at the splice bar, which is appended last."""
    first = splice_time - n_prior * tf_s
    t, o, c, v = _calm_series(n_prior, price, body_calm, tf_s, first)
    # make the last calm bar hand over to the splice bar's open
    o.append(splice_open)
    c.append(splice_close)
    v.append(splice_vol)
    t.append(splice_time)
    return t, o, c, v


# --------------------------------------------------------------- the calendar prior

def test_third_friday_matches_the_2026_quarterly_expiries():
    assert rg.third_friday(2026, 3) == dt.date(2026, 3, 20)
    assert rg.third_friday(2026, 6) == dt.date(2026, 6, 19)
    assert rg.third_friday(2026, 9) == dt.date(2026, 9, 18)
    assert rg.third_friday(2026, 12) == dt.date(2026, 12, 18)


def test_a_month_that_starts_on_a_friday_still_gets_the_third_friday():
    # 2027-01-01 is a Friday, so the third Friday is the 15th, not the 22nd.
    assert rg.third_friday(2027, 1) == dt.date(2027, 1, 15)


def test_both_2026_splice_dates_and_the_december_roll_sit_inside_a_window():
    assert rg.in_roll_window(dt.date(2026, 6, 15))    # NQ/ES June splice
    assert rg.in_roll_window(dt.date(2026, 9, 14))    # the September splice
    assert rg.in_roll_window(dt.date(2026, 12, 14))   # the Monday of December expiry week


def test_expiry_day_itself_and_ordinary_weeks_are_outside_the_window():
    assert not rg.in_roll_window(dt.date(2026, 9, 18))   # expiry day: already rolled
    assert not rg.in_roll_window(dt.date(2026, 9, 19))
    assert not rg.in_roll_window(dt.date(2026, 7, 28))   # the bad Yahoo bar, not a roll
    assert not rg.in_roll_window(dt.date(2026, 10, 15))


def test_the_window_spans_the_ten_days_before_expiry_and_no_more():
    start, exp = rg.roll_window_for(dt.date(2026, 12, 14))
    assert exp == dt.date(2026, 12, 18)
    assert start == dt.date(2026, 12, 8)
    assert rg.in_roll_window(start)
    assert not rg.in_roll_window(start - dt.timedelta(days=1))


# ------------------------------------------------------- the bars this exists to stop

REAL_SPLICES = [
    # name,            price,  calm body, tf_s, when,                       open,      close,     volume
    ("NQ 1m 24h June", 30250,  4.0,       60,   (2026, 6, 15, 3, 30),       30252.00,  30545.75,  13914),
    ("ES 1m 24h June",  7520,  1.0,       60,   (2026, 6, 15, 5, 30),        7521.50,   7586.50,   3323),
    ("NQ 1m Sep",      29080,  8.0,       60,   (2026, 9, 14, 11, 30),      29077.00,  29381.50,   8361),
    ("NQ 5m RTH Sep",  29080, 18.0,      300,   (2026, 9, 14, 11, 30),      29077.00,  29454.50,  18996),
    ("ES 5m RTH Sep",   7610,  4.5,      300,   (2026, 9, 14, 11, 30),       7612.00,   7691.50,  64789),
]


@pytest.mark.parametrize("name,price,calm,tf_s,when,op,cl,vol", REAL_SPLICES,
                         ids=[r[0] for r in REAL_SPLICES])
def test_every_real_in_bar_splice_is_caught(name, price, calm, tf_s, when, op, cl, vol):
    st = _stamp(*when)
    t, o, c, v = _with_splice(price, calm, tf_s, st, op, cl, vol)
    hits = rg.suspect_bars(t, o, c, volumes=v)
    assert len(hits) == 1, "%s: expected exactly the splice bar, got %d" % (name, len(hits))
    hit = hits[0]
    assert hit["index"] == len(c) - 1
    assert hit["body"] == pytest.approx(abs(cl - op))
    assert hit["body"] >= hit["body_floor"]
    assert hit["body"] >= hit["sd_floor"]
    assert hit["volume"] == vol
    assert "contract switch inside a bar" in rg.describe(hit)


def test_the_same_splice_bar_outside_expiry_week_is_left_alone():
    """The guard is silent outside the ten days before expiry, by design.

    Same arithmetic, same bar shape, moved to a week with no expiry near it: nothing is
    flagged, so an ordinary violent news bar in July is never refused.
    """
    st = _stamp(2026, 7, 28, 11, 30)
    t, o, c, v = _with_splice(29080, 18.0, 300, st, 29077.00, 29454.50, 18996)
    assert rg.suspect_bars(t, o, c, volumes=v) == []


def test_a_weekend_gap_between_bars_is_not_a_splice():
    """2026-06-14 18:10 and 2026-09-13 18:10 are real weekend gaps, not rolls.

    A roll that lands between two bars is an ordinary non-adjusted gap and is correct
    for this series. The whole move sits BETWEEN the bars, so no bar has a large body.
    """
    for when, price, jump in ((( 2026, 6, 14, 18, 10), 30250, 412.00),
                              (( 2026, 9, 13, 18, 10), 29400, -384.50)):
        st = _stamp(*when)
        t, o, c, v = _calm_series(120, price, 4.0, 60, st - 120 * 60)
        # the reopen bar starts a whole jump away from the previous close, then trades calmly
        t.append(st)
        o.append(c[-1] + jump)
        c.append(o[-1] + 3.0)
        v.append(0)
        assert rg.suspect_bars(t, o, c, volumes=v) == [], "gap at %s was flagged" % (when,)


def test_a_body_smaller_than_half_the_carry_is_not_flagged():
    """Inside expiry week a merely large bar must still pass; only a carry-sized one stops."""
    st = _stamp(2026, 12, 14, 10, 30, tz=EST)
    carry = rg.carry_prior_pts(29000)                 # about 261 points on NQ
    t, o, c, v = _with_splice(29000, 18.0, 300, st, 29000.0,
                              29000.0 + carry * 0.45, 9000)
    assert rg.suspect_bars(t, o, c, volumes=v) == []
    # ... and just over the line it is caught
    t, o, c, v = _with_splice(29000, 18.0, 300, st, 29000.0,
                              29000.0 + carry * 0.55, 9000)
    assert len(rg.suspect_bars(t, o, c, volumes=v)) == 1


def test_a_carry_sized_move_that_is_normal_for_the_bar_size_is_not_flagged():
    """On a daily bar a 0.5% move is unremarkable, so the ten-sigma test must save it."""
    st = _stamp(2026, 12, 14, 9, 30, tz=EST)
    # daily-ish bars whose ordinary body is already 200 points. The run has to be long
    # enough that the earliest bars are not themselves inside an expiry window with too
    # few predecessors to measure a spread from - that fallback is tested separately.
    t, o, c, v = _with_splice(29000, 200.0, 86400, st, 29000.0, 29000.0 + 150.0, 9000,
                              n_prior=400)
    assert rg.suspect_bars(t, o, c, volumes=v) == []


def test_the_carry_prior_scales_with_price_not_a_fixed_point_count():
    """ES rolls for about a tenth of NQ's points because it trades a quarter of the level."""
    assert rg.carry_prior_pts(29000) == pytest.approx(261.0, abs=1.0)
    assert rg.carry_prior_pts(7600) == pytest.approx(68.4, abs=0.5)


# ------------------------------------------------------------- what a refresh asks it

def test_first_suspect_after_ignores_bars_already_stored():
    """A refresh only decides about the bars it is appending.

    If the guard re-flagged a splice already in the master, every refresh would stall
    forever. ROLL_AUDIT.md tracks the two we already have.
    """
    st = _stamp(2026, 9, 14, 11, 30)
    t, o, c, v = _with_splice(29080, 18.0, 300, st, 29077.00, 29454.50, 18996)
    assert rg.first_suspect_after(t, o, c, after_time=st, volumes=v) is None
    assert rg.first_suspect_after(t, o, c, after_time=st - 1, volumes=v)["time"] == st


def test_first_suspect_after_returns_the_earliest_of_several():
    """Two splices in one pull: the refresh has to stop at the first, not the last."""
    tf = 300
    a = _stamp(2026, 9, 14, 11, 30)
    t, o, c, v = _with_splice(29080, 18.0, tf, a, 29077.00, 29454.50, 18996)
    b = a + 20 * tf
    for k in range(1, 20):                              # calm filler between them
        t.append(a + k * tf); o.append(29454.5); c.append(29460.0); v.append(700)
    t.append(b); o.append(29460.0); c.append(29760.0); v.append(12000)
    hit = rg.first_suspect_after(t, o, c, after_time=a - 1, volumes=v)
    assert hit["time"] == a


def test_the_other_root_is_recorded_as_evidence_and_never_gates_the_call():
    """In June 2026 NQ and ES rolled two hours apart, so 'the other root was flat' is
    not a usable test. It is reported so a human can weigh it, nothing more."""
    st = _stamp(2026, 9, 14, 11, 30)
    t, o, c, v = _with_splice(29080, 18.0, 300, st, 29077.00, 29454.50, 18996)
    other_o = list(o); other_c = list(o)                # the other root dead flat
    hits = rg.suspect_bars(t, o, c, volumes=v, other_opens=other_o, other_closes=other_c)
    assert len(hits) == 1 and hits[0]["other_body"] == 0.0
    # the other root moving just as hard does not clear the bar
    other_c = [x + 400.0 for x in o]
    hits = rg.suspect_bars(t, o, c, volumes=v, other_opens=other_o, other_closes=other_c)
    assert len(hits) == 1 and hits[0]["other_body"] == pytest.approx(400.0)


# -------------------------------------------------------------------- degenerate input

def test_too_few_prior_bars_falls_back_to_the_carry_test_and_still_refuses():
    """A short pull has no usable spread. Refusing is the safe side of that."""
    st = _stamp(2026, 9, 14, 11, 30)
    t = [st - 300, st]
    o = [29070.0, 29077.0]
    c = [29075.0, 29454.5]
    hits = rg.suspect_bars(t, o, c)
    assert len(hits) == 1 and hits[0]["sd_floor"] is None and hits[0]["sd_bars"] == 1


def test_a_dead_flat_stretch_cannot_make_the_spread_zero():
    """An overnight run of unchanged bars would otherwise give SD 0 and flag everything."""
    st = _stamp(2026, 9, 14, 11, 30)
    tf = 60
    t = [st - (120 - i) * tf for i in range(120)]
    o = [29077.0] * 120
    c = [29077.0] * 120                                 # every prior body exactly 0
    t.append(st); o.append(29077.0); c.append(29077.0 + 5.0)   # a 5-point bar
    assert rg.suspect_bars(t, o, c) == []               # nowhere near the carry either way


def test_empty_and_mismatched_input_returns_nothing_rather_than_raising():
    assert rg.suspect_bars([], [], []) == []
    assert rg.suspect_bars([1, 2], [1.0], [1.0, 2.0]) == []
    assert rg.describe(None) == ""


def test_the_flagged_bar_is_reported_with_everything_needed_to_settle_it():
    st = _stamp(2026, 9, 14, 11, 30)
    t, o, c, v = _with_splice(29080, 18.0, 300, st, 29077.00, 29454.50, 18996)
    hit = rg.suspect_bars(t, o, c, volumes=v)[0]
    assert hit["et_date"] == "2026-09-14"
    assert hit["expiry"] == "2026-09-18"
    assert hit["volume_median"] is not None and hit["volume"] > hit["volume_median"]
    line = rg.describe(hit)
    for piece in ("2026-09-14", "29,077.00", "29,454.50", "2026-09-18", "append stopped"):
        assert piece in line, "missing %r in: %s" % (piece, line)


# ------------------------------------------------- the two shapes the refresh holds

def _splice_frames(tf=300):
    """A calm run plus the real 2026-09-14 NQ 5m RTH splice bar, in TV format."""
    import pandas as pd
    st = _stamp(2026, 9, 14, 11, 30)
    t, o, c, v = _with_splice(29080, 18.0, tf, st, 29077.00, 29454.50, 18996)
    df = pd.DataFrame(dict(time=t, open=o, close=c, volume=v))
    df["high"] = df[["open", "close"]].max(axis=1)
    df["low"] = df[["open", "close"]].min(axis=1)
    return st, df


def test_split_tv_frame_keeps_the_clean_bars_and_hands_back_the_suspect_one():
    """This is the shape tools/refresh_noadj_yahoo.py builds from a Yahoo pull."""
    st, df = _splice_frames()
    safe, hit = rg.split_tv_frame(df, after_time=st - 3000)
    assert hit is not None and hit["time"] == st
    assert len(safe) == len(df) - 1
    assert safe["time"].max() < st                     # the splice bar is not stored
    # nothing is refused when the suspect bar is already in the master
    safe2, hit2 = rg.split_tv_frame(df, after_time=st)
    assert hit2 is None and len(safe2) == len(df)


def test_split_indexed_frame_handles_the_capitalised_in_memory_columns():
    """This is the shape optimizer.auto_refresh_masters holds after combine_ohlcv_frames:
    a UTC DatetimeIndex and Open/High/Low/Close/Volume."""
    import pandas as pd
    st, df = _splice_frames()
    idx = pd.to_datetime(df["time"], unit="s", utc=True)
    m = df.drop(columns=["time"]).rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume"})
    m.index = idx
    safe, hit = rg.split_indexed_frame(m, after_ts=st - 3000)
    assert hit is not None and hit["et_date"] == "2026-09-14"
    assert len(safe) == len(m) - 1
    assert safe.index.max() < idx.max()


def test_split_returns_the_frame_untouched_when_there_is_nothing_to_refuse():
    import pandas as pd
    t, o, c, v = _calm_series(80, 29000, 18.0, 300, _stamp(2026, 12, 14, 9, 30, tz=EST))
    df = pd.DataFrame(dict(time=t, open=o, close=c, volume=v))
    safe, hit = rg.split_tv_frame(df, after_time=t[0] - 1)
    assert hit is None and len(safe) == len(df)


def test_write_alert_records_the_event_where_a_human_will_find_it(tmp_path):
    import json
    st, df = _splice_frames()
    _safe, hit = rg.split_tv_frame(df, after_time=st - 3000)
    path = rg.write_alert("NOADJ_NQ_5m_RTH.csv", "5m", hit, alert_dir=str(tmp_path))
    assert path and os.path.exists(path)
    saved = json.load(open(path, encoding="utf-8"))
    assert saved["master"] == "NOADJ_NQ_5m_RTH.csv"
    assert saved["et_date"] == "2026-09-14"
    assert saved["expiry"] == "2026-09-18"
    assert "contract switch inside a bar" in saved["message"]


def test_write_alert_never_raises_even_on_an_unwritable_path():
    """A failed alert must not take a refresh down with it."""
    assert rg.write_alert("x.csv", "5m", None) is None
    st, df = _splice_frames()
    _safe, hit = rg.split_tv_frame(df, after_time=st - 3000)
    assert rg.write_alert("x.csv", "5m", hit, alert_dir="\\?\nonexistent::path") is None


def test_the_yahoo_refresh_tool_actually_calls_the_guard():
    """A guard nothing calls is not a guard. This pins the wiring, not the arithmetic."""
    src = open(os.path.join(ROOT, "tools", "refresh_noadj_yahoo.py"), encoding="utf-8").read()
    assert "from augur_engine import roll_guard" in src
    assert "roll_guard.split_tv_frame" in src
    # and it must run BEFORE the merge-and-write, not after
    assert src.index("roll_guard.split_tv_frame") < src.index("merged.to_csv")


def test_the_app_and_runner_refresh_path_actually_calls_the_guard():
    """optimizer.auto_refresh_masters is the path api/augur_refresh.py runs for the
    headless runner every half hour, so the guard has to sit in it too."""
    src = open(os.path.join(ROOT, "optimizer.py"), encoding="utf-8").read()
    assert "from augur_engine import roll_guard" in src
    assert "roll_guard.split_indexed_frame" in src
    assert src.index("roll_guard.split_indexed_frame") < src.index("ok, _r = save_master_csv")


def test_a_bar_that_moves_AGAINST_the_carry_is_not_a_roll_step():
    """The next contract trades above the expiring one, so a roll steps the price UP.

    All four in-bar splices we have seen stepped up. A same-sized bar stepping DOWN inside
    expiry week is an FOMC or CPI print, and those are what otherwise trip this test - the
    direction filter halves the false alarms on sixteen years of real master data.
    """
    st = _stamp(2026, 9, 14, 11, 30)
    up = _with_splice(29080, 18.0, 300, st, 29077.00, 29454.50, 18996)
    down = _with_splice(29080, 18.0, 300, st, 29454.50, 29077.00, 18996)
    assert len(rg.suspect_bars(up[0], up[1], up[2], volumes=up[3])) == 1
    assert rg.suspect_bars(down[0], down[1], down[2], volumes=down[3]) == []


def test_the_direction_is_a_named_constant_so_a_backwardated_market_can_flip_it():
    """In the near-zero-rate years the deferred contract traded BELOW the front one.
    The rule has to be changeable in one place if that returns."""
    assert rg.CARRY_SIGN == 1
