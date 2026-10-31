"""tools/orb_t239b_exits.py simulate(): level set on a bar's close acts from the next bar; never on the entry bar."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
x = pytest.importorskip("orb_t239b_exits")


def _A(o, h, l, c):
    return {k: np.asarray(v, float) for k, v in zip(("open", "high", "low", "close"), (o, h, l, c))}


IDX = pd.date_range("2024-01-02 09:30", periods=8, freq="5min")


def test_e3_six_bar_trail_fills_at_level_from_next_bar():
    # long entry 100 bar 0: its close sets the E3 stop at its low 99.5, acting from bar 1 (never on bar 0); bar 1 low 99 -> fill 99.5
    A = _A([100, 101, 102, 103, 103, 103, 103, 103], [100, 103, 104, 104, 104, 104, 104, 104],
           [99.5, 99, 98.5, 102, 102, 102, 102, 102], [100, 102, 103, 103, 103, 103, 103, 103])
    tr = [(2024, 0, 7, 1, 100.0, 3.0, 1.0, 2.0)]
    assert x.simulate(tr, A, IDX, "E3")[0] == pytest.approx(-0.5)


def test_gap_through_fills_at_open_and_untouched_keeps_hold():
    A = _A([100, 100, 95, 95, 95, 95, 95, 95], [100, 100.5, 95, 95, 95, 95, 95, 95],
           [99.9, 100, 94, 94, 94, 94, 94, 94], [100, 100.2, 95, 95, 95, 95, 95, 95])
    tr = [(2024, 0, 7, 1, 100.0, -5.0, 1.0, 2.0)]
    assert x.simulate(tr, A, IDX, "E3")[0] == pytest.approx(-5.0)   # bar 2 opens 95 below stop 99.9 -> open fill = -5
    assert x.simulate(tr, A, IDX, "E5")[0] == pytest.approx(-5.0)   # never reached 1R -> hold
