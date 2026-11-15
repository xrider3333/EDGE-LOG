"""MISC_ERFLIP_1_0 (hunt 44d) and MISC_SMALLLEGS_1_0 (hunt 55a): defaults = the hunt cells, the plugin gate
passes, the copied calendar equals the house calendar, the vote matches an independent re-implementation of the
hunt rule, and nothing reads a later bar. Synthetic tapes only (no data on disk, < 10 s).
Real-data parity vs the hunt series: tools/parity_erflip_smalllegs.py."""
import datetime as dt
import os

import numpy as np
import pandas as pd
import pytest

from augur_engine import plugin_gate as G
from augur_engine import session_calendar as SC
from augur_engine import load_strategy
from augur_engine.paths import STRAT_DIR

FILES = ("MISC_ERFLIP_1_0.py", "MISC_SMALLLEGS_1_0.py")
HUNT = {"MISC_ERFLIP_1_0.py": {"entry_min": 150, "exit_before": 5, "cut_pct": 33, "vote_need": 2, "rank_len": 250},
        "MISC_SMALLLEGS_1_0.py": {"prefade_k": 2.0, "late_range_mult": 1.0, "erflip_cut_pct": 33,
                                  "use_prefade": True, "use_late30": True, "use_erflip": True}}


def _path(f):
    return os.path.join(STRAT_DIR, f)


def _src(f):
    with open(_path(f), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def mods():
    return {f: load_strategy(f) for f in FILES}


# ------------------------------------------------------------------------------------------- gate + params
@pytest.mark.parametrize("f", FILES)
def test_gate_whitelist_and_lookahead_clean(f):
    src = _src(f)
    assert G.MARKER_RX.search(src).group(1) == "claude-review"
    assert G.safety_check(src) == []
    assert G.lookahead_check(src) == []
    assert G.inspect_plugin(_path(f))["ok"]


@pytest.mark.parametrize("f", FILES)
def test_defaults_are_the_hunt_cell_and_every_knob_is_ranged(f, mods):
    dp = mods[f].DEFAULT_PARAMS
    assert {k: v["default"] for k, v in dp.items()} == HUNT[f]
    for k, v in dp.items():
        if v["type"] in ("int", "float"):
            assert v["min"] < v["max"], k                                   # ranged, never pinned
            assert v["min"] <= v["default"] <= v["max"], k
            n = (v["default"] - v["min"]) / v["step"]
            assert abs(n - round(n)) < 1e-9, k                             # default sits on the search grid
            assert v.get("hard_min", v["min"]) <= v["min"] and v.get("hard_max", v["max"]) >= v["max"], k
    short = [p for lab, p in mods[f].PARAM_GRID_PRESETS.items() if lab.startswith("Short")][0]
    assert {k: v[0] for k, v in short.items()} == HUNT[f]
    assert mods[f].ROLL_SIGNAL == "ratio" and mods[f].PNL_UNITS == "points"


def test_trial_space_sizes(mods):
    def size(dp):
        s = 1
        for v in dp.values():
            s *= 2 if v["type"] == "bool" else int(round((v["max"] - v["min"]) / v["step"])) + 1
        return s
    assert size(mods["MISC_ERFLIP_1_0.py"].DEFAULT_PARAMS) == 5 * 5 * 9 * 3 * 3 == 2025
    assert size(mods["MISC_SMALLLEGS_1_0.py"].DEFAULT_PARAMS) == 7 * 4 * 9 * 8 == 2016


def _early(d):
    """s44_lib.nyse_early_close: day after Thanksgiving, Dec 24 (weekday, not the observed Christmas), July 3 (July 4 Tue-Fri)."""
    d = pd.Timestamp(d).date(); y = d.year
    return (d == SC._nth_weekday(y, 11, 3, 4) + dt.timedelta(days=1)
            or (d == dt.date(y, 12, 24) and d.weekday() < 5 and d not in SC.closed_days(y))
            or (d == dt.date(y, 7, 3) and dt.date(y, 7, 4).weekday() in (1, 2, 3, 4)))


def _sched_full(d):
    return bool(SC.is_exchange_session(d) and not SC.is_holiday_session(d) and not _early(d))


def test_copied_calendar_equals_house_calendar(mods):
    m = mods["MISC_ERFLIP_1_0.py"]
    s = mods["MISC_SMALLLEGS_1_0.py"]
    days = pd.date_range("2010-01-01", "2026-12-31")
    dn = (days - pd.Timestamp(1970, 1, 1)).days.to_numpy()
    full = np.array([_sched_full(d) for d in days])
    short = np.array([SC.is_holiday_session(d) or (SC.is_exchange_session(d) and _early(d)) for d in days])
    assert (m._sched_full(dn) == full).all() and (s._sched_full(dn) == full).all()
    assert (s._is_short(dn) == short).all()


def test_cut_33_selects_the_hunt_thirds():
    r = np.arange(250) / 249.0
    assert ((r < 0.33) == (r < 1 / 3)).all() and ((r > 1 - 0.33) == (r > 2 / 3)).all()


# ------------------------------------------------------------------------------------------- synthetic tapes
def _sessions(n_days, start="2015-01-05"):
    d = pd.bdate_range(start, periods=int(n_days * 1.1))
    return [x for x in d if SC.is_exchange_session(x)][:n_days]


def _tape(n_days, eth=False, seed=44, drop=()):
    """5m bars; RTH 09:30-15:55 or ETH 18:00(prev)-16:55. Regime-switching vol so the states move."""
    rng = np.random.default_rng(seed)
    stamps = []
    for d in _sessions(n_days):
        if eth:
            t0 = pd.Timestamp(d) - pd.Timedelta(hours=6)                 # 18:00 previous day
            stamps.append(pd.date_range(t0, periods=276, freq="5min"))
        else:
            stamps.append(pd.date_range(pd.Timestamp(d) + pd.Timedelta(hours=9, minutes=30), periods=78, freq="5min"))
    idx = pd.DatetimeIndex(np.concatenate([s.values for s in stamps])).tz_localize("US/Eastern")
    if drop:
        idx = idx[~np.isin(idx.tz_localize(None).normalize(), pd.DatetimeIndex(drop))]
    n = len(idx)
    day = idx.tz_localize(None).normalize()
    codes = pd.factorize(day)[0]
    vol = np.where((codes // 40) % 2 == 0, 4.0, 9.0) * (1 + 0.5 * np.sin(codes / 7.0) ** 2)
    trend = np.where((codes // 13) % 3 == 0, 0.6, 0.0) * np.sign(np.sin(codes / 3.0))
    step = rng.normal(0, 1, n) * vol + trend
    close = 15000 + np.cumsum(step)
    openp = np.r_[close[0], close[:-1]] + rng.normal(0, 0.5, n)
    high = np.maximum(openp, close) + np.abs(rng.normal(0, 2, n))
    low = np.minimum(openp, close) - np.abs(rng.normal(0, 2, n))
    return {"open": openp, "high": high, "low": low, "close": close, "index": idx}


def _hunt_vote_reference(a, warm=370):
    """Independent per-day re-implementation of the S44 rule (s44_lib.build_days / add_state / _rank_next / 44d)."""
    idx = a["index"].tz_localize(None)
    day = idx.normalize()
    hm = idx.hour * 100 + idx.minute
    o, c = a["open"], a["close"]
    rows = []
    for d in pd.unique(day):
        ii = np.flatnonzero((day == d) & (hm >= 930) & (hm <= 1555))
        h = hm[ii]
        rec = {"date": d, "table": bool(len(ii) == 78 and h[0] == 930 and h[-1] == 1555)}
        if rec["table"]:
            r5 = np.diff(np.log(np.concatenate([[o[ii[0]]], c[ii]])))
            r30 = r5.reshape(13, 6).sum(1)
            rec.update(ss5=(r5 ** 2).sum(), ss30=(r30 ** 2).sum(), er=abs(np.log(c[ii[-1]] / o[ii[0]])) / np.abs(r5).sum())
        pos = dict(zip(h, ii))
        need = [g for g in range(930, 1205, 5) if g % 100 < 60]
        rec["ok"] = _sched_full(d) and all(g in pos for g in need)
        if rec["ok"]:
            rec["M"] = c[pos[1155]] - o[pos[930]]
            rec["fwd"] = o[pos[1555]] - o[pos[1200]]
        rows.append(rec)
    T = [r for r in rows if r["table"]]
    ss5 = np.array([r["ss5"] for r in T]); ss30 = np.array([r["ss30"] for r in T]); er = np.array([r["er"] for r in T])
    states = []
    for k in range(len(T) + 1):
        s1 = ss30[k - 20:k].sum() / ss5[k - 20:k].sum() if k >= 20 else np.nan
        s2 = er[k - 5:k].mean() if k >= 5 else np.nan
        s3 = np.sqrt(ss5[k - 5:k].mean()) / np.sqrt(ss5[k - 60:k].mean()) if k >= 60 else np.nan
        states.append((s1, s2, s3))
    S = np.array(states)
    R = np.full(S.shape, np.nan)
    for j in range(3):
        for k in range(warm, len(S)):
            R[k, j] = float((S[max(0, k - 249):k, j] < S[k, j]).mean())
    out = {}
    k = 0
    for r in rows:
        rk = R[k]
        if r["ok"] and not np.isnan(rk).any() and r["M"] != 0:
            v = int((rk > 2 / 3).sum() - (rk < 1 / 3).sum())
            sg = np.sign(r["M"])
            side = -sg if v >= 2 else (sg if v <= -2 else 0)
            if side:
                out[pd.Timestamp(r["date"])] = (int(side), round(float(side * r["fwd"]), 6))
        k += int(r["table"])
    return out


@pytest.fixture(scope="module")
def rth_tape():
    return _tape(470)


def test_erflip_vote_matches_independent_hunt_rule(mods, rth_tape):
    a = rth_tape
    r = mods["MISC_ERFLIP_1_0.py"].run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"],
                                                return_trades=True)
    ref = _hunt_vote_reference(a)
    assert len(ref) >= 10, "synthetic tape too quiet to test the vote"
    got = {}
    ix = a["index"].tz_localize(None)
    for t in r["trades"]:
        assert ix[t[0]].strftime("%H:%M") == "12:00" and ix[t[1]].strftime("%H:%M") == "15:55"
        got[ix[t[0]].normalize()] = (int(t[3]), round(float(t[2]), 6))
    assert got == ref


def test_erflip_needs_rank_len_plus_120_full_sessions(mods, rth_tape):
    a = rth_tape
    ix = a["index"].tz_localize(None)
    r = mods["MISC_ERFLIP_1_0.py"].run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"],
                                                return_trades=True)
    first = min(ix[t[0]].normalize() for t in r["trades"])
    assert int((pd.unique(ix.normalize()) < first).sum()) >= 370


@pytest.mark.parametrize("f,eth", [("MISC_ERFLIP_1_0.py", False), ("MISC_SMALLLEGS_1_0.py", True)])
def test_truncating_the_tail_changes_no_earlier_trade(f, eth, mods):
    a = _tape(400, eth=eth, seed=7)
    p = {"rank_len": 200} if f == "MISC_ERFLIP_1_0.py" else {}
    full = mods[f].run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True, **p)
    assert full and full["trades"]
    cut = int(len(a["close"]) * 0.9)
    b = {k: v[:cut] for k, v in a.items()}
    tr = mods[f].run_backtest(b["open"], b["high"], b["low"], b["close"], index=b["index"], return_trades=True, **p)
    early = {(t[0], t[1], round(t[2], 6)) for t in (tr or {}).get("trades", [])}
    for t in full["trades"]:
        if t[1] < cut:
            assert (t[0], t[1], round(t[2], 6)) in early


def test_smalllegs_one_tuple_per_leg_and_legs_switch_off(mods):
    a = _tape(470, eth=True, seed=3)
    m = mods["MISC_SMALLLEGS_1_0.py"]
    ix = a["index"].tz_localize(None)
    r = m.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True)
    legs = {}
    for t in r["trades"]:
        legs.setdefault(ix[t[0]].strftime("%H:%M"), []).append(t)
        assert len(t) == 6 and t[3] in (1, -1) and abs(t[2] - t[3] * (t[5] - t[4])) < 1e-9
    assert set(legs) == {"09:30", "12:00", "15:00"}
    assert {ix[t[1]].strftime("%H:%M") for t in legs["09:30"]} == {"09:55"}
    assert {ix[t[1]].strftime("%H:%M") for t in legs["15:00"]} == {"15:30"}
    assert {ix[t[1]].strftime("%H:%M") for t in legs["12:00"]} == {"15:55"}
    # the ERFLIP leg of the basket is the ERFLIP file at its defaults (same bars)
    e = mods["MISC_ERFLIP_1_0.py"].run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"],
                                                return_trades=True)
    assert sorted(legs["12:00"]) == sorted(e["trades"])
    # the LATE30 leg is MISC_LATE30_1_0 at its defaults
    l30 = load_strategy("MISC_LATE30_1_0.py").run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"],
                                                         return_trades=True)
    assert sorted((t[0], t[1], round(t[2], 9)) for t in legs["15:00"]) == \
        sorted((t[0], t[1], round(t[2], 9)) for t in l30["trades"])
    only = m.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True,
                          use_late30=False, use_erflip=False)
    assert sorted(only["trades"]) == sorted(legs["09:30"])
    assert m.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], use_prefade=False,
                          use_late30=False, use_erflip=False) is None


def test_prefade_needs_the_pre_open_hour(mods):
    a = _tape(470, eth=False, seed=3)
    r = mods["MISC_SMALLLEGS_1_0.py"].run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"],
                                                   return_trades=True, use_late30=False, use_erflip=False)
    assert r is None                                     # RTH-only tape: no 07:30-09:25 bars, no PREFADE trade


def test_prefade_skips_scheduled_short_sessions(mods):
    m = mods["MISC_SMALLLEGS_1_0.py"]
    a = _tape(470, eth=True, seed=11)
    ix = a["index"].tz_localize(None)
    r = m.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True,
                       use_late30=False, use_erflip=False, prefade_k=1.5)
    d = pd.DatetimeIndex([ix[t[0]].normalize() for t in r["trades"]])
    dn = (d - pd.Timestamp(1970, 1, 1)).days.to_numpy()
    assert not m._is_short(dn).any()
    assert len(d) > 20
