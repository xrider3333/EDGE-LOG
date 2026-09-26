"""NQDIP 1.2 / 1.3 take contract rolls from the committed switch table, remove ONLY the offset, and value
their own open trades on the same adjusted series.

WHY (2026-09-26, ROLL_AUDIT.md 3.6). NQDIP 1.0/1.1 found rolls with the day-level house detector (20 of 65
NQ switches) and dropped the whole overnight gap of each flagged night, which erased real gaps such as the
2020-03-16 NQ limit-down open (-560.5 points against a -12.75 offset) and understated DIP drawdowns 23-29%.

What is guarded:
  1. OFFSET ONLY - on a tape whose true path is known, a switch from tools/data/contract_switches_NQ.csv is
     removed exactly: the back-adjusted series equals the true path, the real gap stays in.
  2. IN-BAR SPLICE - the 2026-09-14 11:30 ET tail row lands on its own bar, not on the session open.
  3. RECONSTRUCTION - last open value + the exit night's adjusted move - costs - 0.25 pt per switch crossed
     equals each closed trade's dollars, and at least one trade crosses a switch.
  4. 1.3 with its three extra legs off reproduces 1.2 exactly (the 1.1 -> 1.0 contract, carried over).
"""
import importlib.util
import os

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT = os.path.join(ROOT, "augur_strategies")
FILES = ["NQDIP_1_2.py", "NQDIP_1_3.py"]


def _load(fname):
    spec = importlib.util.spec_from_file_location("_diproll_" + fname[:-3], os.path.join(STRAT, fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _rth_tape(first, sessions, level, seed, drift=1.0, jumps=None):
    """4 bars a session (09:30 11:30 13:30 15:55 ET). `jumps` = {bar_ts: pts} added to every later bar -
    that is how a no-adjust master looks across a contract switch."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(first, periods=sessions)
    o, h, l, c, idx, did = [], [], [], [], [], []
    px = level
    shift = 0.0
    for j, d in enumerate(days):
        px += rng.normal(drift, level * 0.0015)
        for hm in ("09:30", "11:30", "13:30", "15:55"):
            ts = pd.Timestamp(f"{d.date()} {hm}", tz="US/Eastern")
            for jt, pts in (jumps or {}).items():
                if ts == jt:
                    shift += pts
            op = px + shift
            px += rng.normal(0.2, level * 0.004)
            cl = px + shift
            o.append(op); c.append(cl)
            h.append(max(op, cl) + abs(rng.normal(0, level * 0.001)))
            l.append(min(op, cl) - abs(rng.normal(0, level * 0.001)))
            idx.append(ts); did.append(j)
    return (np.array(o), np.array(h), np.array(l), np.array(c), pd.DatetimeIndex(idx), np.array(did))


# ── 1. offset only ──────────────────────────────────────────────────────────────────────────
def test_a_table_switch_is_removed_exactly_and_the_real_gap_stays():
    mod = _load("NQDIP_1_2.py")
    # NQH0 -> NQM0 at 2020-03-15 18:00 ET, offset -12.75: the first new-contract RTH bar is 03-16 09:30
    sw = pd.Timestamp("2020-03-16 09:30", tz="US/Eastern")
    true = _rth_tape("2020-01-02", 60, 8500.0, seed=5)
    raw = _rth_tape("2020-01-02", 60, 8500.0, seed=5, jumps={sw: -12.75})
    oa, ha, la, ca, ev = mod.roll_adjust(raw[0], raw[1], raw[2], raw[3], raw[4], root="NQ")
    # back-adjusted = the true path expressed in the NEW contract: true - 12.75 before, true after
    k = int(np.searchsorted(raw[4].asi8, sw.value))
    assert [b for b, _ in ev] == [k]
    np.testing.assert_allclose(ca[:k], true[3][:k] - 12.75, atol=1e-9)
    np.testing.assert_allclose(ca[k:], raw[3][k:], atol=1e-9)
    # the overnight gap into the switch session keeps its real move and loses only the offset
    assert (oa[k] - ca[k - 1]) == pytest.approx(true[0][k] - true[3][k - 1], abs=1e-9)


def test_root_is_read_from_the_price_level():
    mod = _load("NQDIP_1_2.py")
    nq = _rth_tape("2020-01-02", 40, 9000.0, seed=1)
    es = _rth_tape("2020-01-02", 40, 3200.0, seed=1)
    assert mod._root_of(nq[4], nq[3]) == "NQ" and mod._root_of(es[4], es[3]) == "ES"


# ── 2. in-bar splice ───────────────────────────────────────────────────────────────────────
def test_the_september_2026_splice_lands_inside_its_session():
    mod = _load("NQDIP_1_2.py")
    t = _rth_tape("2026-08-31", 15, 24000.0, seed=2,
                  jumps={pd.Timestamp("2026-09-14 11:30", tz="US/Eastern"): 295.0})
    oa, ha, la, ca, ev = mod.roll_adjust(*t[:5], root="NQ")
    bar = [b for b, _ in ev]
    assert len(bar) == 1 and t[4][bar[0]] == pd.Timestamp("2026-09-14 11:30", tz="US/Eastern")
    # the session's open-to-close move no longer contains the +295 splice
    s = np.where(t[5] == t[5][bar[0]])[0]
    assert abs((ca[s[-1]] - oa[s[0]]) - ((t[3][s[-1]] - 295.0) - t[0][s[0]])) < 1e-9


# ── 3. reconstruction ──────────────────────────────────────────────────────────────────────
def _long_tape():
    """Five years over real 2016-2020 NQ switches, at NQ-like prices with the table's offsets baked in."""
    import csv
    jumps = {}
    with open(os.path.join(ROOT, "tools", "data", "contract_switches_NQ.csv"), newline="") as f:
        for r in csv.DictReader(f):
            if r["source"] != "databento_raw":
                continue
            et = pd.Timestamp(int(r["switch_sec"]), unit="s", tz="UTC").tz_convert("US/Eastern")
            if pd.Timestamp("2016-01-01", tz="US/Eastern") < et < pd.Timestamp("2020-12-01", tz="US/Eastern"):
                nxt = pd.bdate_range(et.date() + pd.Timedelta(days=1), periods=1)[0]
                jumps[pd.Timestamp(f"{nxt.date()} 09:30", tz="US/Eastern")] = float(r["contract_offset"])
    return _rth_tape("2016-01-04", 1250, 4500.0, seed=11, drift=2.0, jumps=jumps)


@pytest.mark.parametrize("fname", FILES)
def test_marks_rebuild_the_closed_dollars_across_true_switches(fname):
    mod = _load(fname)
    o, h, l, c, idx, did = _long_tape()
    res = mod.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True)
    trades = res["trades"]
    marks = mod.mark_open_trades(trades, o, h, l, c, day_id=did, index=idx)
    assert mod.PNL_UNITS == "usd" and len(marks) == len(trades) > 20
    oa, ha, la, ca, ev = mod.roll_adjust(o, h, l, c, idx)
    rb = np.array([b for b, _ in ev])
    assert len(rb) >= 10
    bounds = mod._session_bounds(did, len(c))
    dca = np.array([ca[b - 1] for a, b in bounds]); doa = np.array([oa[a] for a, b in bounds])
    sess = {a: j for j, (a, b) in enumerate(bounds)}
    crossed = 0
    for t, mk in zip(trades, marks):
        e, x, pnl, side, ep, xp = t
        de, dx = sess[e], sess[x]
        assert ep == o[e] and xp == o[x], "trade prices must be the real traded prices"
        dpp = 2.0 * max(1, int(round(100000.0 / (ep * 2.0))))
        n_roll = int(((rb > e) & (rb <= x)).sum())
        crossed += n_roll > 0
        assert [k for k, _ in mk] == [bounds[j][1] - 1 for j in range(de, dx)]
        rebuilt = mk[-1][1] + dpp * (doa[dx] - dca[dx - 1]) - 0.783 * dpp - 0.25 * dpp * n_roll
        assert rebuilt == pytest.approx(pnl, abs=1e-6)
    assert crossed >= 1, "no trade crossed a switch - the roll branch is untested"


# ── 4. 1.3 contains 1.2 ────────────────────────────────────────────────────────────────────
def test_1_3_with_its_extra_legs_off_is_1_2():
    m12, m13 = _load("NQDIP_1_2.py"), _load("NQDIP_1_3.py")
    o, h, l, c, idx, did = _long_tape()
    a = m12.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True)
    b = m13.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True,
                         use_ibs=False, use_streak=False, use_gapdn=False)
    assert a["trades"] == b["trades"]
