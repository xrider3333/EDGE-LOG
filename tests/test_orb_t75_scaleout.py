"""tools/orb_t75_scaleout.py simulate(): the prereg's scale-out on hand-made bars (no data, no Firestore)."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
s75 = pytest.importorskip("orb_t75_scaleout")


def _A(o, h, l):
    return {"open": np.asarray(o, float), "high": np.asarray(h, float), "low": np.asarray(l, float)}


def test_half_off_at_1r_rest_to_exit_with_extra_cost():
    A = _A([100, 100, 101, 104], [100, 102.5, 103, 104], [100, 100, 100.5, 104])
    tr = [(1, 0, 3, 1, 100.0, 4.0, 1.0, 2.0)]          # risk 2, leg exits +4 at bar 3 (its open)
    r, sc = s75.simulate(tr, A, "R", 1.0, 0.5, False, 0.5)
    assert sc[0] and r[0] == pytest.approx(0.5 * 2 + 0.5 * 4 - 0.25 * 0.5)


def test_be_on_remainder_stops_at_entry_and_no_scale_on_exit_bar():
    A = _A([100, 100, 101, 99], [100, 102.5, 101, 99], [100, 100, 99.5, 98])
    tr = [(1, 0, 3, 1, 100.0, -1.0, 1.0, 2.0)]
    r, _ = s75.simulate(tr, A, "R", 1.0, 0.5, True, 0.0)
    assert r[0] == pytest.approx(0.5 * 2 + 0.5 * 0.0)  # bar 2 touches entry -> remainder flat
    tr2 = [(1, 0, 1, 1, 100.0, 2.5, 1.0, 2.0)]         # trigger only on the exit bar -> HOLD
    r2, sc2 = s75.simulate(tr2, A, "R", 1.0, 0.5, True, 0.0)
    assert not sc2[0] and r2[0] == 2.5


def test_short_pct_trigger():
    A = _A([100, 100, 99], [100, 100, 99], [100, 99.2, 99])
    tr = [(1, 0, 2, -1, 100.0, 1.0, 1.0, 2.0)]
    r, sc = s75.simulate(tr, A, "pct", 0.0058, 1 / 3, False, 0.0)
    assert sc[0] and r[0] == pytest.approx(1 / 3 * 0.58 + 2 / 3 * 1.0)
