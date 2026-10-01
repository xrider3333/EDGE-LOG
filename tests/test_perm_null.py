import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import perm_null  # noqa: E402


def test_within_session_keeps_each_sessions_tag_count():
    lab = np.array([1, 0, 0, 1, 1, 0, 1], bool)
    ses = np.array(["a", "a", "a", "b", "b", "c", "d"])
    rng = np.random.default_rng(1)
    for _ in range(200):
        out = perm_null.within_session_permutation(lab, ses, rng)
        for s in np.unique(ses):
            assert out[ses == s].sum() == lab[ses == s].sum()
        assert out[5] == lab[5] and out[6] == lab[6]          # single-trade sessions never move


def test_single_trade_sessions_give_a_degenerate_null():
    pnl = np.array([5.0, -3.0, 2.0])
    lab = np.array([1, 0, 1], bool)
    ses = np.array(["x", "y", "z"])
    assert perm_null.within_session_share(pnl, lab, ses, n=50) == 1.0   # every shuffle equals the real tag


def test_within_session_null_is_not_the_global_null():
    # the tag keeps the best trade of every day, but the good days are the ones with most trades skipped
    pnl = np.array([10.0, -1.0, -1.0, 1.0, -50.0, 2.0, -40.0])
    lab = np.array([1, 0, 0, 1, 0, 1, 0], bool)
    ses = np.array(["a", "a", "a", "b", "b", "c", "c"])
    w = perm_null.within_session_share(pnl, lab, ses, n=2000)
    g = perm_null.global_share(pnl, lab, n=2000)
    assert w < 0.5 and g < w
