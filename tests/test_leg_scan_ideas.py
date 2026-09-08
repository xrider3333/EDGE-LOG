"""Fast synthetic tests for tools/leg_scan_ideas.py — no masters, no network.

Three things are checked, matching the scan's pre-registration:
  1. the opening-gap measure (gap in units of the prior 20-day average daily range),
  2. the 14:00-14:30 range-breakout rule (direction, stop = the range's other side),
  3. the discovery/holdout split never reaches the 2025-07-01 lockbox.
"""
import datetime as _dt
import importlib.util
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "leg_scan_ideas", os.path.join(ROOT, "tools", "leg_scan_ideas.py"))
LS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LS)


# ---------------------------------------------------------------- 1. gap measure
def test_gap_units_measure():
    # opened 30 points above yesterday's close, on a 100-point average daily range
    assert LS.gap_units_from(10030.0, 10000.0, 100.0) == 0.3
    # gap down is negative, and the size is symmetric
    assert LS.gap_units_from(9950.0, 10000.0, 100.0) == -0.5
    # no gap at all
    assert LS.gap_units_from(10000.0, 10000.0, 100.0) == 0.0
    # unknown inputs (first 20 days, or a zero range) must be nan, never 0.0
    assert np.isnan(LS.gap_units_from(10030.0, float("nan"), 100.0))
    assert np.isnan(LS.gap_units_from(10030.0, 10000.0, float("nan")))
    assert np.isnan(LS.gap_units_from(10030.0, 10000.0, 0.0))
    # and the DayBook wrapper reads the same formula off a day's context
    book = _synthetic_book()
    d = book.dates[-1]
    e = book.day[d]
    expect = (e["open0930"] - e["prior_close"]) / e["adr20"] if e["adr20"] == e["adr20"] \
        else float("nan")
    got = book.gap_units(d)
    assert (np.isnan(got) and np.isnan(expect)) or got == expect


# ------------------------------------------------- 2. 14:00-14:30 range breakout
def test_fomc_range_breakout():
    # the bare direction rule: a CLOSE beyond the range, not a wick
    assert LS.range_breakout_dir(101.0, 100.0, 102.0) == 1
    assert LS.range_breakout_dir(101.0, 100.0, 99.0) == -1
    assert LS.range_breakout_dir(101.0, 100.0, 100.5) == 0
    assert LS.range_breakout_dir(101.0, 100.0, 101.0) == 0   # exactly at the edge

    # end to end on a synthetic day: 14:00-14:25 caged in [100, 101], the 14:30 bar
    # closes at 102 -> long at the 14:35 open, stop at the range low, held to 15:55.
    book = _synthetic_book(fomc_break=True)
    d = book.dates[-1]
    e = book.day[d]
    ia, ib = book.i(d, "14:00"), book.i(d, "14:30")
    rh, rl = float(e["h"][ia:ib].max()), float(e["l"][ia:ib].min())
    assert LS.range_breakout_dir(rh, rl, float(e["c"][ib])) == 1
    tr = LS.simulate(book, d, "14:35", 1, "16:00", stop_px=rl)
    entry = float(e["o"][book.i(d, "14:35")])
    close = float(e["c"][-1])
    assert tr is not None
    assert abs(tr["pnl"] - ((close - entry) * LS.POINT_VALUE - LS.COST_DOLLARS)) < 1e-6
    # the stop really is the range's other side: raising it above entry stops us out
    tr2 = LS.simulate(book, d, "14:35", 1, "16:00", stop_px=entry + 1.0)
    assert tr2["pnl"] < tr["pnl"]


# ------------------------------------------------------ 3. lockbox is never touched
def test_split_never_touches_lockbox():
    d0, d1, h0, h1 = LS.split_bounds()
    lock = pd.Timestamp(LS.LOCKBOX_FROM).date()
    assert d0 == pd.Timestamp(LS.WINDOW_FROM).date()
    assert h1 == pd.Timestamp(LS.WINDOW_TO).date()
    assert h1 < lock, "holdout must end before the lockbox starts"
    assert d0 < d1 < h0 <= h1
    assert h0 == d1 + _dt.timedelta(days=1), "no gap and no overlap between segments"
    # roughly 60/40 by calendar days
    frac = (d1 - d0).days / (h1 - d0).days
    assert 0.58 < frac < 0.62
    # a lockbox-dated trade lands in NEITHER segment (this is the filter main() uses)
    trades = [{"date": _dt.date(2015, 3, 2), "pnl": 100.0},
              {"date": _dt.date(2022, 3, 2), "pnl": 100.0},
              {"date": _dt.date(2025, 8, 1), "pnl": 999999.0}]
    disc = [t for t in trades if d0 <= t["date"] <= d1]
    hold = [t for t in trades if h0 <= t["date"] <= h1]
    assert len(disc) == 1 and len(hold) == 1
    assert 999999.0 not in [t["pnl"] for t in disc + hold]
    # and the scan's own window constant stops before the lockbox
    assert pd.Timestamp(LS.WINDOW_TO).date() < lock


# ---------------------------------------------------------------- synthetic bars
def _synthetic_book(fomc_break=False):
    """Three flat 5-minute RTH days; optionally the last one breaks a 14:00-14:30 cage."""
    rows = []
    days = [_dt.date(2015, 6, 1), _dt.date(2015, 6, 2), _dt.date(2015, 6, 3)]
    for di, d in enumerate(days):
        t = _dt.datetime(d.year, d.month, d.day, 9, 30)
        for b in range(78):                       # 09:30 .. 15:55
            hm = t.strftime("%H:%M")
            px = 100.0
            if fomc_break and di == 2:
                if "14:00" <= hm < "14:30":
                    px = 100.5                    # caged inside [100.25, 100.75]
                elif hm == "14:30":
                    px = 102.0                    # closes above the cage
                elif hm == "14:35":
                    px = 102.0                    # the entry bar
                elif hm > "14:35":
                    px = 110.0                    # then runs well above the cage
            rows.append({"time": int(t.replace(tzinfo=_dt.timezone.utc).timestamp()),
                         "open": px, "high": px + 0.25, "low": px - 0.25,
                         "close": px, "volume": 1000, "_dt": t})
            t += _dt.timedelta(minutes=5)
    df = pd.DataFrame(rows)
    df["_dt"] = pd.to_datetime(df["_dt"]).dt.tz_localize("US/Eastern")
    df["_end"] = df["_dt"] + pd.Timedelta(minutes=5)
    df["day_id"] = pd.factorize(df["_dt"].dt.date)[0]
    return LS.DayBook(df)
