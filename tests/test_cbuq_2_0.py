"""CBU-Q 2.0 (augur_strategies/CBUQ_2_0.py, SETUPS_PREREG_R3_CBU_V1.md): causality (section 5), the trade walk,
one position at a time with at most 2 a session, the holiday list."""
import importlib.util as ilu
import os
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from augur_engine import setup_kit as SK  # noqa: E402

_sp = ilu.spec_from_file_location("cbuq_2_0_t", os.path.join(REPO, "augur_strategies", "CBUQ_2_0.py"))
M = ilu.module_from_spec(_sp)
_sp.loader.exec_module(M)

VARIANTS = [(b, w) for b in M._BASES for w in M._WINDOWS]


def _tape(seed=0, days=20):
    """24-hour one-minute tape from Tuesday 2026-01-20 (after MLK day, before Presidents Day and the March DST
    switch, which a naive ET index cannot hold): an up-drift with a big green volume-spike bar
    every 97 minutes, so every variant fires."""
    rng = np.random.default_rng(seed)
    n = days * 1440
    idx = pd.date_range("2026-01-20 00:00", periods=n, freq="1min")
    step = 0.02 + rng.normal(0, 0.5, n)
    big = (np.arange(n) % 97) == 0
    step[big] = 4.0
    c = 1000 + np.cumsum(step)
    o = c - step
    h = np.maximum(o, c) + rng.uniform(0, 0.3, n)
    l = np.minimum(o, c) - rng.uniform(0, 0.3, n)
    v = rng.uniform(80, 120, n)
    v[big] = 600
    return o, h, l, c, v, idx


def _sig(o, h, l, c, v, idx, base, window):
    M._clear_caches()
    return M._signals(o, h, l, c, v, idx, base=base, window=window)[1]


def test_every_variant_fires_on_the_synthetic_tape():
    t = _tape()
    for base, window in VARIANTS:
        assert len(_sig(*t, base, window)) > 0, (base, window)


@pytest.mark.parametrize("seed", [0, 1])
def test_signals_at_i_ignore_every_later_bar(seed):
    o, h, l, c, v, idx = _tape(seed)
    full = {bw: _sig(o, h, l, c, v, idx, *bw) for bw in VARIANTS}
    allsig = np.sort(np.concatenate(list(full.values())))
    rng = np.random.default_rng(7)
    for cut in (int(allsig[len(allsig) // 3]), int(allsig[-2]), int(allsig[2 * len(allsig) // 3])):
        k = cut + 1
        o2, h2, l2, c2, v2 = (x.copy() for x in (o, h, l, c, v))
        m = len(c) - k
        c2[k:] = c[k:] + rng.normal(0, 25, m)
        o2[k:] = c2[k:] - rng.normal(0, 5, m)
        h2[k:] = np.maximum(o2[k:], c2[k:]) + 3
        l2[k:] = np.minimum(o2[k:], c2[k:]) - 3
        v2[k:] = rng.uniform(1, 5000, m)
        for bw in VARIANTS:
            a = full[bw][full[bw] <= cut]
            b = _sig(o2, h2, l2, c2, v2, idx, *bw)
            # the session's-last-bar guard reads the calendar (bar timestamps are not mutated), never prices
            assert np.array_equal(a, b[b <= cut]), (bw, cut)


def test_trades_closed_before_a_cut_ignore_later_bars():
    o, h, l, c, v, idx = _tape(3)
    M._clear_caches()
    t_full = M._core(o, h, l, c, v, idx, base="any", window="day", exit_mode="ride")
    cut = t_full[len(t_full) // 2][1]
    o2, h2, l2, c2 = (x.copy() for x in (o, h, l, c))
    c2[cut + 1:] -= 50
    o2[cut + 1:] -= 50
    h2[cut + 1:] -= 50
    l2[cut + 1:] -= 50
    M._clear_caches()
    t_mut = M._core(o2, h2, l2, c2, v, idx, base="any", window="day", exit_mode="ride")
    a = [t for t in t_full if t[1] <= cut]
    assert a == [t for t in t_mut if t[1] <= cut]


def test_ride_walk_matches_the_house_walker():
    rng = np.random.default_rng(11)
    for _ in range(400):
        n = 60
        c = 100 + np.cumsum(rng.normal(0, 1, n))
        o = np.r_[100.0, c[:-1]] + rng.normal(0, 0.2, n)
        h = np.maximum(o, c) + rng.uniform(0, 1, n)
        l = np.minimum(o, c) - rng.uniform(0, 1, n)
        entry = o[1]
        stop = entry - rng.uniform(0.5, 3)
        risk = entry - stop
        mine = M._walk(o, h, l, c, 1, n - 1, entry, stop, risk, "ride")
        house = SK.walk_trade(o, h, l, c, 1, entry, stop, risk, "ride", 1.0, 15, 1.0, n - 1)
        assert mine[0] == house[0] and mine[1] == pytest.approx(house[1])


def test_be2r_stop_first_target_and_breakeven():
    # bar 1 entry 100, stop 99 (R = 1): bar 1 closes 101 (arms), bar 2 dips to 100 -> breakeven scratch
    o = np.array([100, 100, 101.0, 101]); h = np.array([100, 101.2, 101.5, 101]); l = np.array([100, 99.5, 100, 100])
    c = np.array([100, 101, 101, 101.0])
    assert M._walk(o, h, l, c, 1, 3, 100.0, 99.0, 1.0, "be2r") == (2, 0.0)
    # a bar that touches both the stop and the 2 R target exits at the stop
    h2 = np.array([100, 102.5, 101, 101.0]); l2 = np.array([100, 98.9, 100, 100])
    assert M._walk(o, h2, l2, c, 1, 3, 100.0, 99.0, 1.0, "be2r") == (1, -1.0)
    # target at 2 R
    h3 = np.array([100, 101.2, 102.1, 101.0])
    assert M._walk(o, h3, l, c, 1, 3, 100.0, 99.0, 1.0, "be2r")[0] in (1, 2)
    assert M._walk(o, h3, np.array([100, 99.5, 100.5, 100]), c, 1, 3, 100.0, 99.0, 1.0, "be2r") == (2, 2.0)
    # ride holds past 2 R to the last bar's close
    assert M._walk(o, h3, np.array([100, 99.5, 100.5, 100.5]), c, 1, 3, 100.0, 99.0, 1.0, "ride") == (3, 1.0)


def test_one_position_at_a_time_and_two_a_session():
    o, h, l, c, v, idx = _tape(5)
    M._clear_caches()
    tr = M._core(o, h, l, c, v, idx, base="any", window="day", exit_mode="ride")
    assert tr
    P = SK.prep(o, h, l, c, v, idx, side=1)
    per = pd.Series([int(P["sess"][t[0]]) for t in tr]).value_counts()
    assert per.max() <= 2
    for a, b in zip(tr, tr[1:]):
        if P["sess"][a[0]] == P["sess"][b[0]]:
            assert b[0] - 1 >= a[1]                     # the next signal bar closes at or after the exit bar
    for fb, xb, pnl, entry in tr:
        assert entry == o[fb] and xb >= fb


def test_holidays_match_the_point_score_list_2025_27():
    sp = ilu.spec_from_file_location("ps_t", os.path.join(REPO, "tools", "point_score.py"))
    ps = ilu.module_from_spec(sp)
    sp.loader.exec_module(ps)
    mine = set(str(np.datetime64(int(x), "D")) for x in M._holidays())
    assert set(x for x in mine if x >= "2025") == set(ps.CME_HOLIDAYS["full"])
    assert {"2012-10-29", "2018-12-05", "2016-03-25", "2021-12-24"} <= mine and "2021-12-31" not in mine


def test_no_decision_on_a_listed_holiday(monkeypatch):
    o, h, l, c, v, idx = _tape(0, days=30)                       # 2026-01-20 .. 02-18; 02-16 is Presidents Day
    on = lambda s: sum(str(idx[i].date()) == "2026-02-16" for i in s)
    assert on(_sig(o, h, l, c, v, idx, "any", "day")) == 0
    monkeypatch.setattr(M, "_HOLIDAY_ORD", np.zeros(0, dtype="int64"))
    assert on(_sig(o, h, l, c, v, idx, "any", "day")) > 0         # the tape does fire that day without the list
