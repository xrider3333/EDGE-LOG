"""Regression tests for the order-flow window and the AG agreement tilt (MANAGER build review 2026-09-30).

1. A trade's fill is the entry bar's OPEN when the engine's entry price is that open (NOISE) and the bar's CLOSE
   when it is the close (ORB close-confirm) - the review found the ORB window ended 5 minutes before the fill.
2. 10-second rows are stamped at bar END: the window takes rows ending in (start, fill], so the row ending exactly
   at the fill is IN and the row ending at the window start is OUT.
3. The AG tilt compares FILL times: on a same-label tie the NOISE trade (filled at the open) is never tilted by the
   ORB trade (filled at the close, 5 minutes later); the ORB trade is.
"""
import importlib.util
import os

import numpy as np
import pandas as pd
import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OF = _load("orderflow_r1")
AG = _load("ag_paired_stop")


def test_fill_time_open_vs_close():
    idx = pd.DatetimeIndex(["2026-09-30 09:30", "2026-09-30 09:35", "2026-09-30 09:40"])
    opens, closes = [100.0, 101.0, 102.0], [100.5, 101.5, 102.5]
    trades = [(1, 2, 0.0, 1, 101.5),      # entry price = bar 1's CLOSE -> fills 09:40 (ORB)
              (1, 2, 0.0, 1, 101.0)]      # entry price = bar 1's OPEN  -> fills 09:35 (NOISE)
    f = OF.fill_times(idx, opens, closes, trades)
    assert list(f) == [pd.Timestamp("2026-09-30 09:40"), pd.Timestamp("2026-09-30 09:35")]


def test_window_is_end_stamped_start_exclusive_fill_inclusive():
    fill = pd.Timestamp("2026-09-30 10:05")
    start = fill - pd.Timedelta(minutes=30)
    t = pd.date_range(start, fill, freq="10s")                       # end stamps 09:35:00 .. 10:05:00
    delta = np.ones(len(t))
    flow = np.full(len(t), 10.0)
    delta[0], flow[0] = -1000.0, 1000.0                               # ends AT the start: must be OUT
    delta[-1], flow[-1] = 1000.0, 1000.0                              # ends AT the fill: must be IN
    of = pd.DataFrame({"delta": delta, "flow": flow, "close": 0.0}, index=t)
    imb, mins = OF.window(of, fill)
    assert mins == pytest.approx(30.0)
    assert imb == pytest.approx((179 + 1000) / (1790 + 1000))


def test_ag_tilt_uses_fill_times():
    day = "2026-09-30 "
    orb = pd.DataFrame({"e": [pd.Timestamp(day + "10:05")], "x": [pd.Timestamp(day + "11:05")], "side": [1]})
    noi = pd.DataFrame({"e": [pd.Timestamp(day + "10:00")], "x": [pd.Timestamp(day + "12:00")], "side": [1]})
    # same 10:00 label: NOISE filled at 10:00, ORB at 10:05 -> only the ORB trade may take the tilt
    assert list(AG.tilt(noi, orb)) == [1.0]
    assert list(AG.tilt(orb, noi)) == [1.5]
    # the other way round: an opposite-direction trade never tilts
    assert list(AG.tilt(orb, noi.assign(side=[-1]))) == [1.0]
