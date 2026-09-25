"""The DIP files value their OWN open trades for a book - and those values rebuild their closed P&L exactly.

WHY (2026-09-25). A book values an open multi-day trade at each day's close as side x (close - entry) x
mult (augur_engine/book.py _mtm_increments, v73.899). The DIP files size themselves - whole MNQ micros
or shares for a fixed notional - and return DOLLARS, so a book runs them at mult 1 and that formula
valued their open positions at $1 a point: DIP on NQ #423's pre-lockbox drawdown read $36,497 instead
of $57,455, DIP on ES #425's lockbox $11,800 instead of $22,371. NQDIP also leaves each quarterly roll
gap out of its P&L. So each of these files now declares PNL_UNITS = "usd" and values its own open
positions in mark_open_trades(), which the book prefers to the price formula (book._plugin_marks).

What is guarded:
  1. RECONSTRUCTION - for every trade, the last open value plus the exit night's move minus the file's
     own costs equals the closed P&L the backtest returned, to the cent. A hook whose sizing drifted from
     run_backtest's, or that forgot a roll gap, cannot pass this.
  2. SHORTS - ETFDIP_RSI2 records a short's side as -1 (it recorded +1, which inverted every open short).
  3. COVERAGE - every strategy file with a `notional` knob (i.e. one that sizes itself) has the hook, so
     a new dollar-P&L file cannot quietly fall back to $1-a-point marks.
"""
import importlib.util
import os
import re

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT = os.path.join(ROOT, "augur_strategies")


def _load(fname):
    spec = importlib.util.spec_from_file_location("_dipmark_" + fname[:-3], os.path.join(STRAT, fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _daily_tape(n=900, seed=7):
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.011, n)))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    return open_, high, low, close


# ── 1 + 2. the ETF files (one bar per session) ─────────────────────────────────────────
@pytest.mark.parametrize("fname,extra", [("ETFDIP_DBL7_1_0.py", {}), ("ETFDIP_PB20_1_0.py", {}),
                                         ("ETFDIP_RSI2_1_0.py", {"allow_shorts": False}),
                                         ("ETFDIP_RSI2_1_0.py", {"allow_shorts": True})])
def test_etf_marks_rebuild_the_closed_dollars(fname, extra):
    mod = _load(fname)
    o, h, l, c = _daily_tape()
    n = len(c)
    res = mod.run_backtest(o, h, l, c, day_id=np.arange(n), return_trades=True, **extra)
    trades = res["trades"]
    marks = mod.mark_open_trades(trades, o, h, l, c, day_id=np.arange(n), **extra)
    assert mod.PNL_UNITS == "usd" and len(marks) == len(trades) > 5
    for t, mk in zip(trades, marks):
        e, x, pnl, side, ep, xp = t
        assert side in (1, -1)
        sh = 100000.0 / ep
        assert [k for k, _ in mk] == list(range(e, x))                    # every close it is held through
        for k, v in mk:
            assert v == pytest.approx(side * (c[k] - ep) * sh, abs=1e-9)
        # 1: last open value + the exit night's move - the file's own 2 bps round trip = closed $
        assert mk[-1][1] + side * (xp - c[x - 1]) * sh - 20.0 == pytest.approx(pnl, abs=1e-6)
    if extra.get("allow_shorts"):
        assert any(t[3] == -1 for t in trades), "tape produced no shorts - the side test is vacuous"


# ── 1. NQDIP on an intraday master, with quarterly roll gaps the file must leave out ────────
def _intraday_tape_with_rolls(sessions=720, seed=11):
    """4 bars a session, NQ-like prices, and a +90-point level shift 6 days before every 3rd
    Wednesday of Mar/Jun/Sep/Dec - the no-adjust master's contract-roll step."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2015-01-02", periods=sessions)
    steps = set()
    for y in sorted({d.year for d in days}):
        for m in (3, 6, 9, 12):
            d0 = pd.Timestamp(year=y, month=m, day=1)
            wed3 = d0 + pd.Timedelta(days=(2 - d0.weekday()) % 7) + pd.Timedelta(weeks=2)
            hit = days[(days >= wed3 - pd.Timedelta(days=6))]
            if len(hit):
                steps.add(hit[0])
    o, h, l, c, idx, did = [], [], [], [], [], []
    px = 4000.0
    for j, d in enumerate(days):
        px += rng.normal(1.2, 6.0)                       # overnight gap, drifting up
        if d in steps:
            px += 90.0                                   # the roll step
        for b, hm in enumerate(("09:30", "11:30", "13:30", "15:55")):
            op = px
            px += rng.normal(0.4, 18.0)
            o.append(op); c.append(px)
            h.append(max(op, px) + abs(rng.normal(0, 4))); l.append(min(op, px) - abs(rng.normal(0, 4)))
            idx.append(pd.Timestamp(f"{d.date()} {hm}", tz="US/Eastern")); did.append(j)
    return (np.array(o), np.array(h), np.array(l), np.array(c), pd.DatetimeIndex(idx), np.array(did))


@pytest.mark.parametrize("fname", ["NQDIP_1_0.py", "NQDIP_1_1.py"])
def test_nqdip_marks_rebuild_the_closed_dollars_across_roll_seams(fname):
    mod = _load(fname)
    o, h, l, c, idx, did = _intraday_tape_with_rolls()
    res = mod.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True)
    trades = res["trades"]
    marks = mod.mark_open_trades(trades, o, h, l, c, day_id=did, index=idx)
    assert mod.PNL_UNITS == "usd" and len(marks) == len(trades) > 20

    bounds = mod._session_bounds(did, len(c))
    do = np.array([o[a] for a, b in bounds]); dc = np.array([c[b - 1] for a, b in bounds])
    seams = set(mod.detect_roll_seams(do, dc, [idx[a] for a, b in bounds]))
    assert len(seams) >= 4, "tape produced no detectable roll seams"
    sess = {a: j for j, (a, b) in enumerate(bounds)}
    crossed = 0
    for t, mk in zip(trades, marks):
        e, x, pnl, side, ep, xp = t
        de, dx = sess[e], sess[x]
        dpp = 2.0 * max(1, int(round(100000.0 / (ep * 2.0))))           # whole MNQ micros at $2/pt
        rolls = sum(1 for s in seams if de < s < dx)
        crossed += rolls > 0
        assert [k for k, _ in mk] == [bounds[j][1] - 1 for j in range(de, dx)]
        # 1: last open value + the exit night's move - 0.783 pt round trip - 0.25 pt per roll = closed $
        rebuilt = mk[-1][1] + dpp * (xp - dc[dx - 1]) - 0.783 * dpp - 0.25 * dpp * rolls
        assert rebuilt == pytest.approx(pnl, abs=1e-6)
    assert crossed >= 1, "no trade crossed a roll seam - the seam branch is untested"


def test_nqdip_on_a_daily_master_values_shares_not_micros():
    """#346 runs NQDIP on QQQ 1d: the file's ETF model (shares for the notional, no roll seams)."""
    mod = _load("NQDIP_1_0.py")
    o, h, l, c = _daily_tape(n=700, seed=3)
    n = len(c)
    idx = pd.date_range("2016-01-04 09:30", periods=n, freq="B", tz="US/Eastern")
    did = np.arange(n)
    trades = mod.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True)["trades"]
    marks = mod.mark_open_trades(trades, o, h, l, c, day_id=did, index=idx)
    assert len(marks) == len(trades) > 5
    for t, mk in zip(trades, marks):
        e, x, pnl, side, ep, xp = t
        sh = 100000.0 / ep
        assert mk[-1][1] + (xp - c[x - 1]) * sh - 20.0 == pytest.approx(pnl, abs=1e-6)


# ── 3. coverage: a file that sizes itself must value its own open trades ──────────────────
def test_every_self_sizing_strategy_file_values_its_own_open_trades():
    missing = []
    for f in sorted(os.listdir(STRAT)):
        if not f.endswith(".py"):
            continue
        src = open(os.path.join(STRAT, f), encoding="utf-8", errors="replace").read()
        if re.search(r"""["']notional["']\s*:\s*\{""", src):
            if not (re.search(r"""^PNL_UNITS\s*=\s*["']usd["']""", src, re.M)
                    and re.search(r"^def mark_open_trades\(", src, re.M)):
                missing.append(f)
    assert not missing, ("these files size themselves (a `notional` knob) but do not declare "
                         "PNL_UNITS = 'usd' with a mark_open_trades() hook: %s" % missing)
