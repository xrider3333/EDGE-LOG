"""tools/orb_t74_giveback.py simulate(): the prereg's giveback stop on hand-made bars (no data, no Firestore)."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
g = pytest.importorskip("orb_t74_giveback")


def _A(o, h, l):
    return {"open": np.asarray(o, float), "high": np.asarray(h, float), "low": np.asarray(l, float)}


def test_long_stop_arms_after_mfe_and_fills_on_touch():
    # entry 100 at bar 0, risk 2; bar 1 high 104 (MFE 4 = 2R); bar 2 dips to 101 -> stop at 100 + 0.5*4 = 102
    A = _A([100, 100, 103, 103], [100, 104, 103, 106], [100, 100, 101, 102])
    tr = [(1, 0, 3, 1, 100.0, 5.0, 1.0, 2.0)]          # leg's own exit: +5 at bar 3
    assert g.simulate(tr, A, 1.0, 0.5)[0] == pytest.approx(2.0)


def test_gap_through_stop_fills_at_open_and_short_mirrors():
    A = _A([100, 100, 99], [100, 100, 99], [100, 96, 99])  # short: MFE 4 at bar 1; bar 2 opens 99 > stop 98
    tr = [(1, 0, 2, -1, 100.0, 0.5, 1.0, 2.0)]
    assert g.simulate(tr, A, 1.0, 0.5)[0] == pytest.approx(1.0)


def test_not_armed_below_y_keeps_the_leg_exit():
    A = _A([100, 100, 100], [100, 101, 100], [100, 99.5, 99])
    tr = [(1, 0, 2, 1, 100.0, -1.0, 1.0, 2.0)]          # MFE 1 = 0.5R < 1R
    assert g.simulate(tr, A, 1.0, 0.5)[0] == pytest.approx(-1.0)
