"""SETUPS round 2 (SETUPS_PREREG_R2.md) -- CBU-Q PTS 1.0 / CBD-Q PTS 1.0: look-ahead for every
filter, long/short mirror parity, the since-low window rule, the 5m/30m EMA reference bar, the
prior-regular-session rule, one trade per session and the plugin contract, on SYNTHETIC data only.
No real masters, no network, no filesystem writes; a few seconds in total.
"""
import importlib.util
import inspect
import itertools
import os

import numpy as np
import pandas as pd
import pytest

from augur_engine import setup_kit as SK

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT_DIR = os.path.join(ROOT, "augur_strategies")
LONG, SHORT = "CBUQ_PTS_1_0", "CBDQ_PTS_1_0"
FILTS = ["none", "trend", "open30", "ema3", "yhigh"]
EXITS = ["ride", "target"]


def _load(name):
    spec = importlib.util.spec_from_file_location("_test_r2_" + name, os.path.join(STRAT_DIR, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def mods():
    return {n: _load(n) for n in (LONG, SHORT)}


@pytest.fixture(autouse=True)
def _fresh_caches(mods):
    """The kit's frame key is a strided checksum; a mutated tail could slip past it, so every
    test starts (and a few clear again mid-test) with empty caches."""
    for m in mods.values():
        m._clear_caches()
    yield


def _clear(mods):
    for m in mods.values():
        m._clear_caches()


# ─────────────────────────────────────────────────────────────────────────────
# synthetic 24-hour tape: one session per date, 18:00 ET the day before -> 16:59 ET on the date
# (no weekend gaps; Jan-Feb 2024 so there is no DST change). `rth_end` maps a date number to the
# (hour, minute) of its LAST regular-session bar: later bars of that date are dropped, which makes
# a holiday stub (12:59), an early close (13:14) or a cut-off day (13:13).
# ─────────────────────────────────────────────────────────────────────────────
class Tape:
    def __init__(self, n_dates, rth_end=None, rand=False, seed=3, base="2024-01-08", start=15000.0):
        rth_end = rth_end or {}
        self.dates = [pd.Timestamp(base) + pd.Timedelta(days=k) for k in range(n_dates)]
        parts = []
        for k, d in enumerate(self.dates):
            t = pd.date_range(d - pd.Timedelta(days=1) + pd.Timedelta(hours=18),
                              d + pd.Timedelta(hours=16, minutes=59), freq="1min")
            if k in rth_end:
                hh, mm = rth_end[k]
                t = t[t <= d + pd.Timedelta(hours=hh, minutes=mm)]
            parts.append(t)
        naive = parts[0].append(parts[1:])
        self.index = naive.tz_localize("US/Eastern")
        n = len(self.index)
        minute = np.asarray(self.index.hour) * 60 + np.asarray(self.index.minute)
        rth = (minute >= 570) & (minute < 960)
        if rand:
            rng = np.random.default_rng(seed)
            day = (np.asarray(self.index.normalize().asi8 // 86_400_000_000_000) % 7)    # a drift per date
            ret = rng.standard_t(3, n) * 0.6 + (day - 3) * 0.04
            c = start + np.cumsum(ret)
            o = np.r_[start, c[:-1]]
            h = np.maximum(o, c) + np.abs(rng.normal(0, 0.5, n))
            l = np.minimum(o, c) - np.abs(rng.normal(0, 0.5, n))
            # big bars trade big volume, so "largest body AND largest volume" fires at a real rate
            v = (150.0 + 400.0 * np.abs(ret) + np.abs(rng.normal(0, 60, n))) * np.where(rth, 4.0, 1.0)
        else:                                       # flat: no bar is green, ATR14 = 1.0
            o = np.full(n, 100.0); c = np.full(n, 100.0)
            h = np.full(n, 100.5); l = np.full(n, 99.5); v = np.full(n, 100.0)
        self.o, self.h, self.l, self.c, self.v = o, h, l, c, v

    @property
    def arrays(self):
        return self.o, self.h, self.l, self.c, self.v, self.index

    def pos(self, d, hhmm):
        return int(self.index.get_loc(pd.Timestamp("%s %s" % (self.dates[d].date(), hhmm), tz="US/Eastern")))

    def set(self, d, hhmm, o, h, l, c, v):
        i = self.pos(d, hhmm)
        self.o[i], self.h[i], self.l[i], self.c[i], self.v[i] = o, h, l, c, v
        return i

    def at(self, d, start_hhmm, k):
        """position of the bar k minutes after start_hhmm on date d"""
        return self.pos(d, start_hhmm) + k


def cands(mods, tape, filt="none", min_win=5, name=LONG):
    _clear(mods)
    o, h, l, c, v, idx = tape.arrays
    if name == LONG:
        P, m = mods[LONG]._candidates(o, h, l, c, v, idx, filt, min_win)
    else:
        P, m = mods[LONG]._candidates(-o, -l, -h, -c, v, idx, filt, min_win)
    return np.flatnonzero(m)


def run(mods, tape, name=LONG, **kw):
    _clear(mods)
    o, h, l, c, v, idx = tape.arrays
    return mods[name].run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True, **kw)


# ─────────────────────────────────────────────────────────────────────────────
# plugin contract
# ─────────────────────────────────────────────────────────────────────────────
def test_plugin_contract_surface(mods):
    for name, m in mods.items():
        sp = inspect.signature(m.run_backtest).parameters
        for p in ("opens", "highs", "lows", "closes", "volumes", "day_id", "index", "filt", "exit_mode",
                  "min_win", "stop_buf_atr", "return_trades", "_stop_event", "_pause_event"):
            assert p in sp, (name, p)
        assert any(q.kind == q.VAR_KEYWORD for q in sp.values())
        assert isinstance(m.STRATEGY_NAME, str) and m.TIMEFRAME == "1m"
        assert m.DIRECTION == ("LONG" if name == LONG else "SHORT")
        for k, spec in m.DEFAULT_PARAMS.items():
            assert spec.get("default") is not None and spec.get("tooltip") and spec.get("label"), k
            assert spec["type"] in ("str", "int", "float")
    assert set(mods[LONG].DEFAULT_PARAMS) == {"filt", "exit_mode", "min_win", "stop_buf_atr"}
    assert mods[SHORT].DEFAULT_PARAMS is mods[LONG].DEFAULT_PARAMS or mods[SHORT].DEFAULT_PARAMS == mods[LONG].DEFAULT_PARAMS


def test_presets_are_the_preregistered_grids(mods):
    for m in mods.values():
        g = m.PARAM_GRID_PRESETS
        tri = g["Triage (pre-registered)"]
        assert tri["filt"] == FILTS and tri["exit_mode"] == EXITS
        assert tri["min_win"] == [5] and tri["stop_buf_atr"] == [0.0]
        assert len(list(itertools.product(*tri.values()))) == 10        # per file and root: 20 per side over NQ+ES
        val = g["Validate (pre-registered)"]
        assert val["min_win"] == [5, 10] and val["stop_buf_atr"] == [0.0, 0.25]
        assert len(list(itertools.product(*val.values()))) == 40
        dp = m.DEFAULT_PARAMS                                             # the knob space IS the grid
        assert dp["filt"]["options"] == FILTS and dp["exit_mode"]["options"] == EXITS
        assert (dp["min_win"]["min"], dp["min_win"]["max"], dp["min_win"]["step"]) == (5, 10, 5)
        assert (dp["stop_buf_atr"]["min"], dp["stop_buf_atr"]["max"], dp["stop_buf_atr"]["step"]) == (0.0, 0.25, 0.25)


@pytest.mark.parametrize("name", [LONG, SHORT])
def test_raises_on_bad_input(mods, name):
    t = Tape(3)
    o, h, l, c, v, idx = t.arrays
    m = mods[name]
    with pytest.raises(ValueError):
        m.run_backtest(o, h, l, c, volumes=v, index=None)
    with pytest.raises(ValueError):
        m.run_backtest(o, h, l, c, volumes=None, index=idx)
    with pytest.raises(ValueError):
        m.run_backtest(o, h, l, c, volumes=v, index=idx, filt="bogus")
    with pytest.raises(ValueError):
        m.run_backtest(o, h, l, c, volumes=v, index=idx, exit_mode="trail")


@pytest.fixture(scope="module")
def rand_tape():
    return Tape(22, rand=True, seed=3)


@pytest.mark.parametrize("name", [LONG, SHORT])
@pytest.mark.parametrize("filt,exit_mode,min_win,buf", [
    (f, e, mw, b) for f in FILTS for e in EXITS for (mw, b) in ((5, 0.0), (10, 0.25))])
def test_contract_smoke_trade_tuples(mods, rand_tape, name, filt, exit_mode, min_win, buf):
    _clear(mods)
    o, h, l, c, v, idx = rand_tape.arrays
    res = mods[name].run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True, filt=filt,
                                  exit_mode=exit_mode, min_win=min_win, stop_buf_atr=buf)
    assert res is None or isinstance(res, dict)
    if res is None:
        return
    for k in ("total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown", "avg_pnl",
              "wins", "losses", "trades"):
        assert k in res
    sess, minute, starts, ends, _ = SK.sessions(idx)
    rth = (minute >= 570) & (minute < 960)
    exp_side = 1 if name == LONG else -1
    seen = set()
    for t in res["trades"]:
        assert len(t) == 5
        fb, xb, pnl, side, entry = t
        assert side == exp_side and rth[fb] and xb >= fb and sess[xb] == sess[fb]
        assert minute[fb] >= 571, "entry is the NEXT bar's open, so never the 09:30 bar"
        assert sess[fb] not in seen, "one trade per session"
        seen.add(sess[fb])
        assert abs(entry - o[fb]) < 1e-9 * (1 + abs(entry)) or abs(entry + o[fb]) < 1e-9 * (1 + abs(entry))


@pytest.mark.parametrize("fname", ["CBUQ_PTS_1_0.py", "CBDQ_PTS_1_0.py"])
def test_files_resolve_to_the_cbu_q_family(fname):
    """No registration lines are needed for a new file in an existing family: the runner's resolver and the
    re-stamp tool both key on the CBUQ / CBDQ filename prefix (CLAUDE.md, family vocabulary)."""
    import api.runner as R
    assert R.FirestoreQueue._family_of(None, fname) == "CBU-Q"
    src = open(os.path.join(ROOT, "tools", "family_rename.py"), encoding="utf-8").read()
    ns = {}
    exec("import re\n" + src[src.index("def resolve("):src.index("\ndef main(")], ns)
    assert ns["resolve"](fname) == "CBU-Q"


# ─────────────────────────────────────────────────────────────────────────────
# look-ahead: mutating any bar at or after k+1 never changes a decision at or before k
# ─────────────────────────────────────────────────────────────────────────────
def _mutate_tail(arrays, k, mode="random", seed=99):
    """Replace every bar after k. mode: 'random' = garbage; 'up' / 'down' = the whole tail shifted by
    +/-1e5 points with volumes x20 / x0.05 (so a decision that peeks at the direction, the size or the
    level of anything after k flips in at least one of the two)."""
    o, h, l, c, v, idx = arrays
    n = len(c)
    o2, h2, l2, c2, v2 = o.copy(), h.copy(), l.copy(), c.copy(), v.copy()
    tail = slice(k + 1, n)
    m = n - (k + 1)
    if mode == "random":
        rng = np.random.default_rng(seed)
        o2[tail] += rng.normal(0, 25.0, m)
        c2[tail] += rng.normal(0, 25.0, m)
        h2[tail] = np.maximum(o2[tail], c2[tail]) + np.abs(rng.normal(0, 3.0, m))
        l2[tail] = np.minimum(o2[tail], c2[tail]) - np.abs(rng.normal(0, 3.0, m))
        v2[tail] = np.abs(rng.normal(900, 400, m)) + 10
    else:
        shift = 1e5 if mode == "up" else -1e5
        for arr in (o2, h2, l2, c2):
            arr[tail] += shift
        v2[tail] *= 20.0 if mode == "up" else 0.05
    return o2, h2, l2, c2, v2, idx


@pytest.mark.parametrize("filt", FILTS)
@pytest.mark.parametrize("side_name", [LONG, SHORT])
def test_no_look_ahead_candidate_mask(mods, rand_tape, filt, side_name):
    """Every filter, both sides: the decision at bar i (candidate mask) is identical when every bar
    after i is replaced -- by garbage, and by the whole tail shifted far up and far down. k is chosen
    at real candidate bars (so a rule that peeks one bar ahead is caught), inside 5-minute and
    30-minute buckets, inside the first half hour and at the session's last bars."""
    base = rand_tape.arrays
    sgn = 1 if side_name == LONG else -1

    def mask(arrs):
        _clear(mods)
        o, h, l, c, v, idx = arrs
        if sgn == 1:
            return mods[LONG]._candidates(o, h, l, c, v, idx, filt, 5)[1]
        return mods[LONG]._candidates(-o, -l, -h, -c, v, idx, filt, 5)[1]

    full = mask(base)
    where = np.flatnonzero(full)
    assert len(where) > 3, "synthetic tape must fire this rule (not a vacuous test)"
    picks = where[np.linspace(0, len(where) - 1, 3).astype(int)]
    ks = sorted({int(k) for k in picks} | {rand_tape.pos(9, "10:17")})
    for k in ks:
        for mode in ("random", "up", "down"):
            m2 = mask(_mutate_tail(base, k, mode))
            assert np.array_equal(full[:k + 1], m2[:k + 1]), "decision at/before %d changed by a bar after it (%s)" % (k, mode)


@pytest.mark.parametrize("name", [LONG, SHORT])
@pytest.mark.parametrize("filt", FILTS)
@pytest.mark.parametrize("exit_mode", EXITS)
def test_no_look_ahead_trades(mods, rand_tape, name, filt, exit_mode):
    base = rand_tape.arrays
    o, h, l, c, v, idx = base

    def trades(arrs):
        _clear(mods)
        a = mods[name].run_backtest(arrs[0], arrs[1], arrs[2], arrs[3], volumes=arrs[4], index=idx,
                                    return_trades=True, filt=filt, exit_mode=exit_mode)
        return a["trades"] if a else []

    t0 = trades(base)
    assert len(t0) > 0
    for k, mode in ((rand_tape.pos(11, "11:11"), "random"), (rand_tape.pos(17, "13:00"), "up"),
                    (rand_tape.pos(20, "10:42"), "down")):
        t1 = trades(_mutate_tail(base, k, mode))
        b0 = {t[0]: t for t in t0 if t[0] <= k}
        b1 = {t[0]: t for t in t1 if t[0] <= k}
        assert set(b0) == set(b1), "a trade filled at or before bar %d appeared or vanished" % k
        for fb, t in b0.items():
            assert abs(b1[fb][4] - t[4]) < 1e-9
            if t[1] <= k:
                assert b1[fb][1] == t[1] and abs(b1[fb][2] - t[2]) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# mirror parity: the short file on the tape == the long file on the price-inverted tape
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("filt", FILTS)
@pytest.mark.parametrize("exit_mode", EXITS)
@pytest.mark.parametrize("min_win,buf", [(5, 0.0), (10, 0.25)])
def test_mirror_parity_by_price_inversion(mods, rand_tape, filt, exit_mode, min_win, buf):
    o, h, l, c, v, idx = rand_tape.arrays
    _clear(mods)
    r_long_inv = mods[LONG].run_backtest(-o, -l, -h, -c, volumes=v, index=idx, return_trades=True,
                                         filt=filt, exit_mode=exit_mode, min_win=min_win, stop_buf_atr=buf)
    _clear(mods)
    r_short = mods[SHORT].run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True,
                                       filt=filt, exit_mode=exit_mode, min_win=min_win, stop_buf_atr=buf)
    t1 = r_long_inv["trades"] if r_long_inv else []
    t2 = r_short["trades"] if r_short else []
    assert len(t1) == len(t2)
    for a, b in zip(t1, t2):
        assert a[0] == b[0] and a[1] == b[1] and abs(a[2] - b[2]) < 1e-9
        assert a[3] == 1 and b[3] == -1 and abs(a[4] + b[4]) < 1e-6


@pytest.mark.parametrize("name", [LONG, SHORT])
def test_signal_bar_semantics_in_original_prices(mods, rand_tape, name):
    """Checked from the ORIGINAL prices with a brute-force reading of the rule: the signal bar (the bar
    before the fill) is green/red, has the largest body and volume since today's regular-session
    low/high (latest bar holding it), the window holds >= min_win bars, open30 is 09:30-09:59, and ema3
    compares the close with brute-force 200 EMAs of the 1m/5m/30m series (above for long, below for short)."""
    o, h, l, c, v, idx = rand_tape.arrays
    sgn = 1 if name == LONG else -1
    sess, minute, starts, ends, _ = SK.sessions(idx)
    rth = (minute >= 570) & (minute < 960)
    e1, r5, r30 = _brute_ema_refs(c, idx)
    ar = np.arange(len(c))
    n_checked = 0
    for filt in FILTS:
        _clear(mods)
        res = mods[name].run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True, filt=filt, min_win=5)
        for fb, xb, pnl, side, entry in (res["trades"] if res else []):
            i = fb - 1
            assert side == sgn and rth[i] and sess[i] == sess[fb] and abs(entry - o[fb]) < 1e-9
            assert sgn * (c[i] - o[i]) > 0, "green for a long, red for a short"
            day = np.flatnonzero((sess == sess[i]) & rth & (ar <= i))
            ext = l[day].min() if sgn == 1 else h[day].max()
            j = day[np.flatnonzero((l[day] if sgn == 1 else h[day]) == ext)[-1]]    # LATEST bar holding the extreme
            win = np.arange(j, i + 1)
            assert len(win) >= 5
            assert abs(c[i] - o[i]) >= np.abs(c[win] - o[win]).max() - 1e-12
            assert v[i] >= v[win].max() - 1e-12
            if filt == "open30":
                assert 570 <= minute[i] < 600
            if filt == "ema3":
                assert sgn * c[i] > sgn * e1[i] and sgn * c[i] > sgn * r5[i] and sgn * c[i] > sgn * r30[i]
            n_checked += 1
    assert n_checked >= 10, "too few trades to be a meaningful check"


# ─────────────────────────────────────────────────────────────────────────────
# the trigger and the since-low window (hand-built bars)
# ─────────────────────────────────────────────────────────────────────────────
def test_window_starts_at_todays_regular_session_low_not_premarket(mods):
    t = Tape(3)
    d = 1
    t.set(d, "05:00", 100.0, 100.5, 50.0, 100.0, 100.0)                  # a far lower PREMARKET low
    t.set(d, "09:30", 100.0, 103.2, 99.9, 103.0, 900.0)                  # huge green body + volume at the open
    t.set(d, "09:31", 100.0, 100.3, 95.0, 99.6, 100.0)                   # the regular-session low
    t.set(d, "09:36", 100.0, 101.7, 99.8, 101.5, 500.0)                  # trigger: window 09:31..09:36 = 6 bars
    got = cands(mods, t, "none", 5)
    assert t.pos(d, "09:36") in got, "premarket low must not anchor the window (09:30 bar is outside it)"
    assert t.pos(d, "09:30") not in got


def test_window_length_boundary_and_min_win(mods):
    """After a low bar at 10:00, bar k (k=0..7) has a window of k+1 bars and a larger body and volume
    than every earlier bar in it, so it is a candidate iff k+1 >= min_win."""
    t = Tape(3)
    d = 1
    for k in range(8):
        t.set(d, "10:%02d" % k, 100.0, 100.0 + 0.1 * (k + 1) + 0.05, 98.0 if k == 0 else 99.6,
              100.0 + 0.1 * (k + 1), 100.0 + 10.0 * k)
    first = t.pos(d, "10:00")
    for mw in range(1, 9):
        got = sorted(int(i - first) for i in cands(mods, t, "none", mw) if first <= i < first + 8)
        assert got == [k for k in range(8) if k + 1 >= mw], (mw, got)


def test_a_bar_that_makes_a_new_low_has_a_one_bar_window(mods):
    t = Tape(3)
    d = 1
    i = t.set(d, "10:00", 100.0, 101.2, 97.0, 101.0, 900.0)             # green, big, AND the day's new low
    assert i in cands(mods, t, "none", 1)
    assert i not in cands(mods, t, "none", 2)


def test_latest_low_wins_ties(mods):
    t = Tape(3)
    d = 1
    t.set(d, "10:00", 100.0, 100.2, 95.0, 99.9, 100.0)                  # low A
    t.set(d, "10:01", 100.0, 103.2, 99.9, 103.0, 900.0)                 # huge green body + volume, between the two lows
    t.set(d, "10:03", 100.0, 100.2, 95.0, 99.9, 100.0)                  # low B, equal to A: the window starts HERE
    trig = t.set(d, "10:07", 100.0, 101.7, 99.8, 101.5, 500.0)         # window 10:03..10:07 = 5 bars
    assert trig in cands(mods, t, "none", 5)
    assert trig not in cands(mods, t, "none", 6)
    # with only ONE bar holding the low (the earlier one), the huge bar IS in the window and blocks it
    t2 = Tape(3)
    t2.set(d, "10:00", 100.0, 100.2, 95.0, 99.9, 100.0)
    t2.set(d, "10:01", 100.0, 103.2, 99.9, 103.0, 900.0)
    trig2 = t2.set(d, "10:07", 100.0, 101.7, 99.8, 101.5, 500.0)
    assert trig2 not in cands(mods, t2, "none", 5)


def test_trigger_needs_green_largest_body_and_largest_volume_with_ties_allowed(mods):
    def day(body, vol, o=100.0):
        t = Tape(3)
        t.set(1, "10:00", 100.0, 100.2, 98.0, 99.9, 100.0)
        t.set(1, "10:03", 100.0, 101.2, 99.8, 101.0, 500.0)               # in-window bar: body 1.0, volume 500
        i = t.set(1, "10:06", o, o + body + 0.2, 99.8, o + body, vol)
        return t, i
    t, i = day(1.0, 500.0)
    assert i in cands(mods, t, "none", 5), "equal body and equal volume still fire (>=)"
    t, i = day(0.75, 500.0)
    assert i not in cands(mods, t, "none", 5), "smaller body than a bar in the window"
    t, i = day(1.0, 499.0)
    assert i not in cands(mods, t, "none", 5), "smaller volume than a bar in the window"
    t, i = day(1.5, 600.0)
    assert i in cands(mods, t, "none", 5)
    t = Tape(3)                                                           # a RED bar with the biggest body and volume
    t.set(1, "10:00", 100.0, 100.2, 98.0, 99.9, 100.0)
    i = t.set(1, "10:06", 101.5, 101.7, 99.8, 100.0, 600.0)
    assert i not in cands(mods, t, "none", 5), "a red bar is never a long signal"


def test_decision_bars_include_1558_but_not_1559(mods):
    t = Tape(3)
    d = 1
    t.set(d, "15:50", 100.0, 100.2, 98.0, 99.9, 100.0)
    i58 = t.set(d, "15:58", 100.0, 101.2, 99.8, 101.0, 500.0)
    i59 = t.set(d, "15:59", 101.0, 102.4, 100.8, 102.2, 900.0)
    got = cands(mods, t, "none", 5)
    assert i58 in got and i59 not in got
    res = run(mods, t, LONG, filt="none")
    tr = [x for x in res["trades"] if x[0] == i59]
    assert len(tr) == 1 and tr[0][1] == i59, "a 15:58 signal enters at the 15:59 open and is flat at its close"
    assert abs(tr[0][4] - 101.0) < 1e-9 and abs(tr[0][2] - (102.2 - 101.0)) < 1e-9


def test_one_trade_per_session_and_risk_skip_continues_the_scan(mods):
    t = Tape(4)
    d = 1
    t.set(d, "10:00", 100.0, 100.2, 98.0, 99.9, 100.0)
    a = t.set(d, "10:05", 100.0, 101.2, 99.8, 101.0, 500.0)               # first signal
    t.set(d, "10:06", 99.0, 99.5, 98.9, 99.2, 100.0)                       # next open BELOW its stop -> risk <= 0, no trade
    t.set(d, "11:00", 100.0, 100.2, 97.0, 99.9, 100.0)                     # a new low restarts the window
    b = t.set(d, "11:05", 100.0, 102.2, 99.8, 102.0, 900.0)                # second signal, valid
    t.set(2, "10:00", 100.0, 100.2, 98.0, 99.9, 100.0)
    c2 = t.set(2, "10:05", 100.0, 101.2, 99.8, 101.0, 500.0)
    t.set(2, "11:00", 100.0, 100.2, 97.0, 99.9, 100.0)
    t.set(2, "11:05", 100.0, 102.2, 99.8, 102.0, 900.0)
    got = cands(mods, t, "none", 5)
    assert a in got and b in got and c2 in got
    res = run(mods, t, LONG, filt="none")
    fills = [x[0] for x in res["trades"]]
    assert b + 1 in fills and a + 1 not in fills, "a signal that only fails the risk check does not use up the session"
    assert c2 + 1 in fills and (t.pos(2, "11:05") + 1) not in fills, "one trade per session: the first valid signal only"
    sess = SK.sessions(t.index)[0]
    assert len({int(sess[f]) for f in fills}) == len(fills)


# ─────────────────────────────────────────────────────────────────────────────
# short side in original prices (hand-built): fills, stop, target and signs
# ─────────────────────────────────────────────────────────────────────────────
def _short_day(post):
    t = Tape(3)
    t.set(1, "10:00", 100.0, 102.0, 99.8, 100.1, 100.0)                   # the day's high
    t.set(1, "10:05", 100.0, 100.2, 98.8, 99.0, 500.0)                    # red, biggest body and volume since the high
    for k, bar in enumerate(post):
        t.set(1, "10:%02d" % (6 + k), *bar)
    return t


def test_short_target_and_stop_and_entry():
    m = _load(SHORT); mm = {SHORT: m, LONG: _load(LONG)}
    # entry at the 10:06 open = 100.0; stop = high(i) = 100.2 (risk 0.2); target = 99.8
    t = _short_day([(100.0, 100.1, 99.7, 99.9, 100.0)])
    t.set(1, "10:07", 99.9, 99.9, 99.9, 99.9, 100.0)
    res = run(mm, t, SHORT, filt="none", exit_mode="target")
    tr = [x for x in res["trades"] if x[0] == t.pos(1, "10:06")]
    assert len(tr) == 1
    fb, xb, pnl, side, entry = tr[0]
    assert side == -1 and abs(entry - 100.0) < 1e-9 and xb == t.pos(1, "10:06") and abs(pnl - 0.2) < 1e-9
    t = _short_day([(100.0, 100.3, 99.7, 99.9, 100.0)])                    # one bar touches both: stop first
    res = run(mm, t, SHORT, filt="none", exit_mode="target")
    tr = [x for x in res["trades"] if x[0] == t.pos(1, "10:06")]
    assert len(tr) == 1 and abs(tr[0][2] - (-0.2)) < 1e-9, "stop-first when one bar touches both"
    t = _short_day([(100.0, 100.1, 99.9, 99.95, 100.0), (100.4, 100.5, 100.3, 100.4, 100.0)])
    res = run(mm, t, SHORT, filt="none", exit_mode="target")
    tr = [x for x in res["trades"] if x[0] == t.pos(1, "10:06")]
    assert len(tr) == 1 and abs(tr[0][2] - (100.0 - 100.4)) < 1e-9, "a bar opening beyond the stop fills at its open"


def test_short_trend_and_yhigh_mirror_conditions(mods):
    """Short `yhigh` = close BELOW the prior regular session's LOW; short `trend` = the prior regular
    session's high AND low both BELOW the session before it."""
    t = Tape(5)
    t.set(0, "09:40", 100.0, 104.0, 96.0, 100.0, 100.0)
    t.set(1, "09:40", 100.0, 102.0, 94.0, 100.0, 100.0)
    t.set(2, "09:40", 100.0, 101.0, 98.9, 100.0, 100.0)
    sig = {}
    for d, (anchor_h, close, low) in {2: (101.4, 99.0, 98.95), 3: (101.3, 99.0, 98.95), 4: (101.3, 98.5, 98.4)}.items():
        t.set(d, "10:00", 100.0, anchor_h, 99.8, 100.1, 100.0)                  # the day's high
        sig[d] = t.set(d, "10:05", 100.0, 100.2, low, close, 500.0)             # red, biggest body/volume since it
    # d2: P1 = d1 (102, 94), P2 = d0 (104, 96): both lower -> down-trend; its close 99.0 is not below d1's low 94
    assert sig[2] in cands(mods, t, "trend", 5, name=SHORT) and sig[2] not in cands(mods, t, "yhigh", 5, name=SHORT)
    # d3: P1 = d2 (101.4, 98.9), P2 = d1 (102, 94): high lower but low HIGHER -> no; 99.0 is not below 98.9
    assert sig[3] not in cands(mods, t, "trend", 5, name=SHORT) and sig[3] not in cands(mods, t, "yhigh", 5, name=SHORT)
    # d4: P1 = d3 (101.3, 98.95), P2 = d2 (101.4, 98.9): low higher -> no trend; 98.5 IS below 98.95
    assert sig[4] not in cands(mods, t, "trend", 5, name=SHORT) and sig[4] in cands(mods, t, "yhigh", 5, name=SHORT)
    for d in (2, 3, 4):
        assert sig[d] in cands(mods, t, "none", 5, name=SHORT)


# ─────────────────────────────────────────────────────────────────────────────
# the prior REGULAR session: stubs and cut-off days skipped, a 13:14 early close kept, strictly earlier
# ─────────────────────────────────────────────────────────────────────────────
def test_prior_regular_session_rule(mods):
    rth_end = {2: (12, 59),      # holiday 09:30-13:00 stub
               3: (13, 14),      # early close, last bar 13:14 -> kept
               4: (13, 13)}      # cut-off day, last bar 13:13 -> skipped
    t = Tape(8, rth_end=rth_end)
    hl = [(110, 90), (112, 92), (200, 10), (115, 95), (300, 5), (111, 97), (113, 98), (110, 96)]
    for d, (hi, lo) in enumerate(hl):
        t.set(d, "09:40", 100.0, float(hi), float(lo), 100.0, 100.0)
    o, h, l, c, v, idx = t.arrays
    _clear(mods)
    P = SK.prep(o, h, l, c, v, idx)
    hi1, lo1, trend = mods[LONG]._prior_session_levels(h, l, P)
    sess = P['sess']
    sid = {d: int(sess[t.pos(d, "09:40")]) for d in range(8)}
    expect_p1 = {0: None, 1: 0, 2: 1, 3: 1, 4: 3, 5: 3, 6: 5, 7: 6}      # stub d2 and 13:13 day d4 never serve as a prior session
    expect_trend = {0: False, 1: False, 2: True, 3: True, 4: True, 5: True, 6: False, 7: True}
    for d in range(8):
        s = sid[d]
        if expect_p1[d] is None:
            assert np.isnan(hi1[s]) and np.isnan(lo1[s])
        else:
            assert (hi1[s], lo1[s]) == hl[expect_p1[d]], "session %d: prior regular session" % d
        assert bool(trend[s]) == expect_trend[d], "session %d trend" % d
    # strictly earlier: a session's own high never reaches its own level
    for d in range(8):
        assert hi1[sid[d]] != hl[d][0] or np.isnan(hi1[sid[d]])


# ─────────────────────────────────────────────────────────────────────────────
# the 5m/30m EMA reference bar and the ema3 / open30 filters
# ─────────────────────────────────────────────────────────────────────────────
def _brute_ema_refs(c, index, span=200):
    """Pure-Python reference: EMA recurrence over wall-clock 5m / 30m bucket closes; the reference for a
    bar is the EMA as of the latest bucket that STARTS before the bucket holding the bar."""
    wall = pd.DatetimeIndex(index).tz_localize(None)
    a = 2.0 / (span + 1.0)

    def refs(minutes):
        key = [int(ts.value // (minutes * 60_000_000_000)) for ts in wall]
        closes = {}
        order = []
        for k, x in zip(key, c):
            if k not in closes:
                order.append(k)
            closes[k] = x                                              # last close in the bucket
        e, prev = {}, None
        for k in order:
            prev = closes[k] if prev is None else (1 - a) * prev + a * closes[k]
            e[k] = prev
        pos = {k: j for j, k in enumerate(order)}
        out = np.full(len(c), np.nan)
        for i, k in enumerate(key):
            if pos[k] > 0:
                out[i] = e[order[pos[k] - 1]]
        return out
    ema1 = np.empty(len(c))
    ema1[0] = c[0]
    for i in range(1, len(c)):
        ema1[i] = (1 - a) * ema1[i - 1] + a * c[i]
    return ema1, refs(5), refs(30)


def test_ema_reference_is_the_bar_before_the_one_holding_bar_i(mods):
    t = Tape(6, rand=True, seed=21)
    o, h, l, c, v, idx = t.arrays
    e1, r5, r30 = mods[LONG]._ema_refs(c, idx)
    b1, b5, b30 = _brute_ema_refs(c, idx)
    np.testing.assert_allclose(e1, b1, rtol=1e-12)
    np.testing.assert_allclose(r5, b5, rtol=1e-12, equal_nan=True)
    np.testing.assert_allclose(r30, b30, rtol=1e-12, equal_nan=True)
    # explicit boundary bars: bars 10:00..10:04 share one 5m reference; 10:05 moves on to the 10:00-10:04 EMA;
    # bars 10:00..10:29 share one 30m reference
    base = t.pos(3, "10:00")
    assert len({r5[base + k] for k in range(5)}) == 1 and r5[base + 5] != r5[base]
    assert len({r30[base + k] for k in range(30)}) == 1 and r30[base + 30] != r30[base]
    # the 30m reference at 10:00..10:29 is the EMA through the 09:30 bucket, which closed at 09:59
    assert r30[base] == pytest.approx(b30[base], rel=1e-12)


def test_ema_reference_ignores_the_rest_of_the_bucket(mods):
    """Replacing every bar after 10:10 (inside the 10:00 30m bucket and 10:10 5m bucket) leaves the
    ema filter at 10:10 unchanged -- and the 5m/30m references at 10:10 reach back, not forward."""
    t = Tape(6, rand=True, seed=21)
    i = t.pos(3, "10:10")
    o, h, l, c, v, idx = t.arrays
    _, r5, r30 = mods[LONG]._ema_refs(c, idx)
    o2, h2, l2, c2, v2, _ = _mutate_tail(t.arrays, i)
    e1b, r5b, r30b = mods[LONG]._ema_refs(c2, idx)
    assert r5b[i] == r5[i] and r30b[i] == r30[i]
    assert np.array_equal(mods[LONG]._ema_above(c, idx)[:i + 1], mods[LONG]._ema_above(c2, idx)[:i + 1])


def test_open30_and_ema3_filters_on_hand_bars(mods):
    t = Tape(3)
    d = 1
    t.set(d, "09:45", 100.0, 100.2, 98.0, 99.9, 100.0)
    a = t.set(d, "09:50", 100.0, 101.2, 99.8, 101.0, 500.0)                 # in the first half hour, above the (flat 100) EMAs
    t.set(d, "10:30", 100.0, 100.2, 97.0, 99.9, 100.0)
    b = t.set(d, "10:35", 100.0, 101.2, 99.8, 101.0, 500.0)                 # later, above the EMAs
    t.set(d, "11:30", 99.2, 99.4, 96.0, 99.1, 100.0)
    cbar = t.set(d, "11:35", 99.0, 99.8, 98.8, 99.6, 500.0)                 # green and big, but BELOW the flat-100 EMAs
    assert {a, b, cbar} <= set(cands(mods, t, "none", 5))
    assert a in cands(mods, t, "open30", 5) and b not in cands(mods, t, "open30", 5)
    ok = set(cands(mods, t, "ema3", 5))
    assert a in ok and b in ok and cbar not in ok


def test_trend_and_yhigh_filters_on_hand_bars(mods):
    t = Tape(6)
    for d, (hi, lo) in enumerate([(100.9, 97.0), (101.5, 98.0), (101.0, 98.5)]):    # three regular sessions
        t.set(d, "09:40", 100.0, hi, lo, 100.0, 100.0)
    # d3 signal closes at 101.0: above d2's high 101.0? no (equal); make it 101.1
    t.set(3, "10:00", 100.0, 100.2, 98.0, 99.9, 100.0)
    s3 = t.set(3, "10:05", 100.0, 101.3, 99.8, 101.1, 500.0)
    assert s3 in cands(mods, t, "yhigh", 5)                                         # 101.1 > 101.0 (prior session d2)
    t.set(4, "10:00", 100.0, 100.2, 98.0, 99.9, 100.0)
    s4 = t.set(4, "10:05", 100.0, 101.0, 99.8, 100.9, 500.0)
    assert s4 not in cands(mods, t, "yhigh", 5)                                     # 100.9 < d3's high (101.3)
    # trend: d3's P1 = d2 (101.0, 98.5), P2 = d1 (101.5, 98.0): high lower -> False; d2's P1 = d1, P2 = d0: both higher -> True
    t.set(2, "10:00", 100.0, 100.2, 97.5, 99.9, 100.0)
    s2 = t.set(2, "10:05", 100.0, 101.0, 99.8, 100.9, 500.0)
    assert s2 in cands(mods, t, "trend", 5) and s3 not in cands(mods, t, "trend", 5)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
