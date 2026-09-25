"""SETUPS round 1 (SETUPS_PREREG.md) -- contract, causality (A0), mirror parity (A2), the
exit walk and each rule's signal-bar precision, on SYNTHETIC data only. Must run fast
(<20s total): a small hand-built ETH tape, no real masters, no network, no filesystem
writes.
"""
import importlib.util
import os

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT_DIR = os.path.join(ROOT, "augur_strategies")

FILES = ["CBUQ_1M_1_0", "CBDQ_1M_1_0", "EBUQ_1M_1_0", "ENGU_2_0", "ENGU_2_0_D"]


def _load(name):
    path = os.path.join(STRAT_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location("_test_" + name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def mods():
    return {n: _load(n) for n in FILES}


# ─────────────────────────────────────────────────────────────────────────────
# synthetic ETH tape: ~15 sessions of 1-minute bars, 18:00 ET -> next day 17:59 ET
# (skipping the 17:00-17:59 daily break), a random walk with a per-session trend bias
# so CBU/CBD/EBU/ENGU/ENGD all get a chance to fire.
# ─────────────────────────────────────────────────────────────────────────────
def build_tape(n_sessions=16, seed=11, overrides=None):
    """overrides: optional {session_idx: {local_rth_idx: (o,h,l,c)}} -- exact bars, applied
    after the random walk, for hand-built signal-precision tests. Returns (o,h,l,c,v,index)."""
    overrides = overrides or {}
    rng = np.random.default_rng(seed)
    all_ts, all_o, all_h, all_l, all_c, all_v = [], [], [], [], [], []
    cur = pd.Timestamp('2024-02-05 18:00', tz='US/Eastern')   # a Monday
    price = 15000.0
    for s in range(n_sessions):
        bias = rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0]) * 0.25
        t = cur
        sess_ts = []
        while len(sess_ts) < 24 * 60:
            if t.hour == 17:                      # daily break, no bars
                t = t + pd.Timedelta(minutes=1)
                continue
            sess_ts.append(t)
            t = t + pd.Timedelta(minutes=1)
        sess_ov = overrides.get(s, {})
        rth_local = 0
        for ts_i in sess_ts:
            minute = ts_i.hour * 60 + ts_i.minute
            is_rth = 570 <= minute < 960
            ov = sess_ov.get(rth_local) if is_rth else None
            if ov is not None:
                o, hi, lo, c = ov
            else:
                drift = bias / 390.0
                ret = rng.normal(drift, 0.9)
                o = price
                c = price + ret
                hi = max(o, c) + abs(rng.normal(0, 0.5))
                lo = min(o, c) - abs(rng.normal(0, 0.5))
            vol = abs(rng.normal(400, 100)) + (250 if is_rth else 40)
            all_ts.append(ts_i); all_o.append(o); all_h.append(hi); all_l.append(lo)
            all_c.append(c); all_v.append(vol)
            price = c
            if is_rth:
                rth_local += 1
        cur_last = sess_ts[-1]
        nxt = pd.Timestamp(year=cur_last.year, month=cur_last.month, day=cur_last.day,
                           hour=18, tz='US/Eastern')
        if nxt <= cur_last:
            nxt = nxt + pd.Timedelta(days=1)
        cur = nxt
    idx = pd.DatetimeIndex(all_ts)
    return (np.array(all_o), np.array(all_h), np.array(all_l), np.array(all_c),
            np.array(all_v), idx)


@pytest.fixture(scope="module")
def tape():
    return build_tape()


KNOB_VARIANTS = [
    {},
    {"exit_mode": "trail", "trail_bars": 10, "be_R": 0.5},
    {"exit_mode": "target", "target_R": 3.0},
    {"stop_buf_atr": 0.25, "min_risk_atr": 0.5},
    {"end_min": 30},
    {"vol_mult": 1.0},
    {"first_bar": "skip", "base_bars": 3},
]


# ─────────────────────────────────────────────────────────────────────────────
# contract smoke
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", FILES)
@pytest.mark.parametrize("knobs_idx", range(len(KNOB_VARIANTS)))
def test_contract_smoke(mods, tape, name, knobs_idx):
    o, h, l, c, v, idx = tape
    knobs = KNOB_VARIANTS[knobs_idx]
    m = mods[name]
    res = m.run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True, **knobs)
    assert res is None or isinstance(res, dict)
    if res is None:
        return
    for k in ("total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown",
             "avg_pnl", "wins", "losses", "trades"):
        assert k in res
    exp_side = 1 if m.DIRECTION == "LONG" else -1
    sess, minute, starts, ends, barlen = _sessions(idx)
    rth = (minute >= 570) & (minute < 960)
    seen_sessions = set()
    for t in res["trades"]:
        assert len(t) == 5
        fb, xb, pnl, side, entry = t
        assert side == exp_side
        assert rth[fb], "fill bar must be in RTH"
        assert xb >= fb, "exit bar must be at or after the fill bar"
        s_fb = sess[fb]
        assert sess[xb] == s_fb, "exit must be in the same session as the fill"
        assert xb >= starts[s_fb] and xb < ends[s_fb]
        assert s_fb not in seen_sessions, "at most one trade per session"
        seen_sessions.add(s_fb)


def _sessions(idx):
    from augur_engine import setup_kit as SK
    return SK.sessions(idx)


# ─────────────────────────────────────────────────────────────────────────────
# raises without index / without volumes when vol_mult>0
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", FILES)
def test_raises_without_index(mods, tape, name):
    o, h, l, c, v, idx = tape
    m = mods[name]
    with pytest.raises(ValueError):
        m.run_backtest(o, h, l, c, volumes=v, index=None)


@pytest.mark.parametrize("name", FILES)
def test_raises_vol_mult_needs_volumes(mods, tape, name):
    o, h, l, c, v, idx = tape
    m = mods[name]
    with pytest.raises(ValueError):
        m.run_backtest(o, h, l, c, volumes=None, index=idx, vol_mult=2.0)


# ─────────────────────────────────────────────────────────────────────────────
# A0: causality -- perturbing every bar strictly after k must not change any trade
# fully decided at or before k.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", FILES)
def test_a0_causality(mods, tape, name):
    o, h, l, c, v, idx = tape
    m = mods[name]
    n = len(c)
    base = m.run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True)
    base_trades = base["trades"] if base else []
    rng = np.random.default_rng(99)
    for k in (n // 4, n // 2, 3 * n // 4, n - 5):
        o2, h2, l2, c2, v2 = o.copy(), h.copy(), l.copy(), c.copy(), v.copy()
        tail = slice(k + 1, n)
        bump = rng.normal(0, 5.0, size=n - (k + 1))
        o2[tail] += bump; c2[tail] += bump
        h2[tail] = np.maximum(o2[tail], c2[tail]) + np.abs(rng.normal(0, 1.0, n - (k + 1)))
        l2[tail] = np.minimum(o2[tail], c2[tail]) - np.abs(rng.normal(0, 1.0, n - (k + 1)))
        v2[tail] = np.abs(rng.normal(400, 150, n - (k + 1))) + 50

        res2 = m.run_backtest(o2, h2, l2, c2, volumes=v2, index=idx, return_trades=True)
        trades2 = res2["trades"] if res2 else []

        base_by_fill = {t[0]: t for t in base_trades if t[0] <= k}
        new_by_fill = {t[0]: t for t in trades2 if t[0] <= k}
        # every trade filled at or before k must still exist, unchanged in fill/entry
        for fb, t in base_by_fill.items():
            assert fb in new_by_fill, "trade filled at bar %d vanished after perturbing bar>%d" % (fb, k)
            t2 = new_by_fill[fb]
            assert t2[0] == t[0]
            assert abs(t2[4] - t[4]) < 1e-9, "entry price changed for a trade filled at/before k"
            if t[1] <= k:      # exit also at/before k -> the WHOLE trade must be identical
                assert t2[1] == t[1]
                assert abs(t2[2] - t[2]) < 1e-9
        # no NEW trade with fill<=k appears that wasn't in the base run
        for fb in new_by_fill:
            assert fb in base_by_fill, "a new trade with fill<=%d appeared after perturbing bar>%d" % (k, k)


# ─────────────────────────────────────────────────────────────────────────────
# A2: mirror parity -- the short file run on the ORIGINAL tape reproduces the long
# file run on the INVERTED tape, trade for trade.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("long_name,short_name", [("CBUQ_1M_1_0", "CBDQ_1M_1_0"),
                                                  ("ENGU_2_0", "ENGU_2_0_D")])
def test_a2_mirror_parity(mods, tape, long_name, short_name):
    o, h, l, c, v, idx = tape
    long_m = mods[long_name]; short_m = mods[short_name]
    o2, h2, l2, c2 = -o, -l, -h, -c
    r_long_inv = long_m.run_backtest(o2, h2, l2, c2, volumes=v, index=idx, return_trades=True)
    r_short = short_m.run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True)
    t1 = r_long_inv["trades"] if r_long_inv else []
    t2 = r_short["trades"] if r_short else []
    assert len(t1) == len(t2) and len(t1) > 0, "mirror produced no comparable trades -- widen the tape"
    for a, b in zip(t1, t2):
        fa, xa, pa, sa, ea = a
        fb, xb, pb, sb, eb = b
        assert fa == fb and xa == xb
        assert abs(pa - pb) < 1e-9
        assert sa == 1 and sb == -1
        assert abs(ea - (-eb)) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# exit-rule unit tests on a hand-built tape (direct setup_kit.walk_trade calls)
# ─────────────────────────────────────────────────────────────────────────────
def test_exit_stop_first_gap_fill():
    from augur_engine import setup_kit as SK
    o = np.array([100., 101, 102, 90, 103])
    h = np.array([102., 103, 103, 103, 105])
    l = np.array([99., 100, 101, 94, 102])
    c = np.array([101., 102, 101, 96, 104])
    xb, pnl = SK.walk_trade(o, h, l, c, 0, 100.0, 95.0, 5.0, 'ride', 1.0, 3, 2.0, 4)
    assert xb == 3 and abs(pnl - (90 - 100)) < 1e-9, "a bar opening beyond the stop must fill at its open"


def test_exit_stop_via_low_not_gap():
    from augur_engine import setup_kit as SK
    o = np.array([100., 101, 96.])
    h = np.array([102., 103, 97.])
    l = np.array([99., 100, 93.])
    c = np.array([101., 102, 95.])
    xb, pnl = SK.walk_trade(o, h, l, c, 0, 100.0, 95.0, 5.0, 'ride', 1.0, 3, 2.0, 2)
    assert xb == 2 and abs(pnl - (95.0 - 100.0)) < 1e-9, "a bar whose low (not open) touches the stop fills AT the stop"


def test_exit_breakeven_armed_next_bar_only():
    from augur_engine import setup_kit as SK
    # bar0 closes at 106 (>= entry+be_R*risk=105) -> arms; armed stop(=entry=100) applies
    # from bar1 onward, NOT at bar0 itself.
    o = np.array([100., 101, 101.0])
    h = np.array([102., 107, 102.0])
    l = np.array([99.5, 100.5, 99.5])
    c = np.array([101., 106, 100.0])
    xb, pnl = SK.walk_trade(o, h, l, c, 0, 100.0, 95.0, 5.0, 'ride', 1.0, 3, 2.0, 2)
    assert xb == 2 and abs(pnl - 0.0) < 1e-9


def test_exit_target_fills_at_target_on_gap():
    from augur_engine import setup_kit as SK
    o = np.array([100., 101, 102, 115.])
    h = np.array([102., 103, 103, 116.])
    l = np.array([99., 100, 101, 114.])
    c = np.array([101., 102, 101, 115.5])
    xb, pnl = SK.walk_trade(o, h, l, c, 0, 100.0, 95.0, 5.0, 'target', 1.0, 3, 2.0, 3)
    assert xb == 3 and abs(pnl - 10.0) < 1e-9, "target fills AT the target price, even on a gap above it"


def test_exit_flat_at_session_close():
    from augur_engine import setup_kit as SK
    o = np.array([100., 101, 102.])
    h = np.array([102., 103, 104.])
    l = np.array([99.5, 100.5, 101.5])
    c = np.array([101., 102, 103.5])
    xb, pnl = SK.walk_trade(o, h, l, c, 0, 100.0, 95.0, 5.0, 'ride', 1.0, 3, 2.0, 2)
    assert xb == 2 and abs(pnl - 3.5) < 1e-9


def test_exit_trail_ratchets_and_never_loosens():
    from augur_engine import setup_kit as SK
    o = np.array([100., 107, 102, 103, 104])
    h = np.array([108., 108, 104, 105, 106])
    l = np.array([99.5, 106, 101, 102.5, 103.5])
    c = np.array([106., 107.5, 103, 104.5, 105])
    lo_roll = pd.Series(l).rolling(2, min_periods=1).min().to_numpy()
    xb, pnl = SK.walk_trade(o, h, l, c, 0, 100.0, 95.0, 5.0, 'trail', 1.0, 2, 2.0, 4,
                            lo_roll_trail=lo_roll)
    assert xb == 4 and abs(pnl - 5.0) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# signal-bar precision: each rule fires on the intended bar, not one bar early
# ─────────────────────────────────────────────────────────────────────────────
def test_cbu_signal_not_one_bar_early(mods):
    """A close above the premarket high but still inside the day's own range so far must
    NOT fire; the next bar that ALSO clears the day's own high fires, filled at the
    following open."""
    m = mods["CBUQ_1M_1_0"]
    # build_tape's overrides are keyed by RTH-local index only (>=0); premarket bars are
    # generated by the random walk, so pin the premarket window's range directly below.
    o, h, l, c, v, idx = build_tape(n_sessions=3, seed=5)
    # locate session 0's premarket bars (minute 240..569) and pin their range to make a
    # clean premarket high of 100.0
    from augur_engine import setup_kit as SK
    sess, minute, starts, ends, barlen = SK.sessions(idx)
    a0, b0 = starts[0], ends[0]
    pm_idx = np.flatnonzero((minute[a0:b0] >= 240) & (minute[a0:b0] < 570)) + a0
    h[pm_idx] = 99.0; h[pm_idx[len(pm_idx) // 2]] = 100.0     # premarket high = 100.0
    l[pm_idx] = 90.0; o[pm_idx] = 95.0; c[pm_idx] = 95.0

    rth_idx = np.flatnonzero((minute[a0:b0] >= 570) & (minute[a0:b0] < 960)) + a0
    # bar0 (09:30, first_bar='allow' default): the level test STILL applies there, so its
    # own close must stay AT or BELOW the premarket high, or it would fire immediately.
    # High=105 still establishes a high day range (rth_hi_before is HIGH-based, not close-
    # based) for the bars that follow.
    o[rth_idx[0]], h[rth_idx[0]], l[rth_idx[0]], c[rth_idx[0]] = 95.0, 105.0, 94.0, 98.0
    # bar1: closes above the premarket high (100) but inside the day's own range (<=105)
    o[rth_idx[1]], h[rth_idx[1]], l[rth_idx[1]], c[rth_idx[1]] = 100.0, 102.0, 99.0, 101.0
    # bar2: closes at a NEW day high (>105) and above the premarket high -> fires
    o[rth_idx[2]], h[rth_idx[2]], l[rth_idx[2]], c[rth_idx[2]] = 101.0, 107.0, 100.0, 106.0
    # keep the rest of the session flat so nothing else confuses the single-trade check
    for j in range(3, len(rth_idx) - 1):
        o[rth_idx[j]] = h[rth_idx[j]] = l[rth_idx[j]] = c[rth_idx[j]] = 106.0

    res = m.run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True,
                         level_mode='pm', vol_mult=0.0, base_bars=0)
    assert res is not None
    sess_trades = [t for t in res["trades"] if starts[0] <= t[0] < ends[0]]
    assert len(sess_trades) == 1, "exactly one CBU signal expected in session 0"
    fb = sess_trades[0][0]
    assert fb == rth_idx[3], "CBU must fire at bar2's close (fill at bar3's open), not one bar early"


def test_ebu_signal_not_one_bar_early(mods):
    """A close that breaks the brk_n-bar local high must not fire until it ALSO clears
    that local high; a bar that merely matches the recent high must not fire."""
    m = mods["EBUQ_1M_1_0"]
    o, h, l, c, v, idx = build_tape(n_sessions=3, seed=6)
    from augur_engine import setup_kit as SK
    sess, minute, starts, ends, barlen = SK.sessions(idx)
    a0, b0 = starts[0], ends[0]
    rth_idx = np.flatnonzero((minute[a0:b0] >= 570) & (minute[a0:b0] < 960)) + a0
    brk_n = 3
    # bar0: a high spike (103) that sets the DAY's high-so-far without entering the
    # brk_n=3 lookback of any bar tested below (j>=4, so its window is bars[j-3..j-1] >= 1).
    o[rth_idx[0]], h[rth_idx[0]], l[rth_idx[0]], c[rth_idx[0]] = 100.0, 103.0, 99.0, 100.0
    # bars 1-3: flat chop, local high 101 -- the lookback window for bar4 and bar5.
    for j in (1, 2, 3):
        o[rth_idx[j]], h[rth_idx[j]], l[rth_idx[j]], c[rth_idx[j]] = 100.0, 101.0, 99.5, 100.5
    # bar4: closes exactly AT the recent (bars1-3) local high (101) -- must NOT fire
    # (EBU needs close > the brk_n-bar high, not >=).
    o[rth_idx[4]], h[rth_idx[4]], l[rth_idx[4]], c[rth_idx[4]] = 100.5, 101.0, 100.0, 101.0
    # bar5: closes above the local high (bars2-4 max 101) AND stays inside the day's own
    # high so far (bars0-4 max 103, from bar0's spike) -> fires.
    o[rth_idx[5]], h[rth_idx[5]], l[rth_idx[5]], c[rth_idx[5]] = 101.0, 102.5, 100.5, 102.0
    for j in range(6, len(rth_idx) - 1):
        o[rth_idx[j]] = h[rth_idx[j]] = l[rth_idx[j]] = c[rth_idx[j]] = 102.0

    res = m.run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True,
                         brk_n=brk_n, vol_mult=0.0, base_bars=0)
    assert res is not None
    sess_trades = [t for t in res["trades"] if starts[0] <= t[0] < ends[0]]
    assert len(sess_trades) == 1
    fb = sess_trades[0][0]
    assert fb == rth_idx[6], "EBU must fire at bar5's close (fill at bar6's open), not at bar4 (close==local high, not >)"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))


# ─────────────────────────────────────────────────────────────────────────────
# contract switch (roll day): the 24-hour masters switch contracts at 00:00 UTC INSIDE a
# session; that session's prior-day level (old contract) must be blanked, no other.
# ─────────────────────────────────────────────────────────────────────────────
def test_contract_switch_blanks_only_the_switch_session():
    from augur_engine import setup_kit as SK
    rng = np.random.default_rng(5)
    ts = pd.date_range('2024-06-09 18:00', '2024-06-21 16:59', freq='1min', tz='US/Eastern')
    ts = ts[ts.hour != 17]
    n = len(ts)
    c = 19000.0 + np.cumsum(rng.normal(0, 1.0, n))
    k_sw = int(np.flatnonzero(ts == pd.Timestamp('2024-06-16 20:00', tz='US/Eastern'))[0])
    c[k_sw:] += 250.0                                  # the switch: +250 at 00:00 UTC
    o = np.r_[c[0], c[:-1]]
    o[k_sw] = c[k_sw]                                  # the jump is open vs prior close
    h = np.maximum(o, c) + 0.5
    l = np.minimum(o, c) - 0.5
    v = np.full(n, 300.0)
    sess, minute, starts, ends, _ = SK.sessions(ts)
    sw = SK.contract_switch_sessions(o, c, ts, sess)
    assert sw == {int(sess[k_sw])}
    P = SK.prep(o, h, l, c, v, ts)
    rth_first = np.flatnonzero(P['is_first_rth'])
    blank = [str(ts[i].date()) for i in rth_first[1:] if np.isnan(P['priorday_hi'][i])]
    assert blank == ['2024-06-17']
