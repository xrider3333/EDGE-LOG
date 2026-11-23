"""MISC_SMALLLEGS_1_1 = MISC_SMALLLEGS_1_0 + the fixed prior-VIX stand-aside (vix_max 15). Synthetic tapes and a
hand-made VIX table only (no data on disk needed, < 10 s): vix_max 0 = 1.0 trade for trade, the rule drops whole
days, reads the VIX row dated BEFORE the session, missing VIX trades, the holiday rows drop, the knob is pinned."""
import numpy as np
import pandas as pd
import pytest

from augur_engine import plugin_gate as G
from augur_engine import load_strategy
from augur_engine import auto as A

from test_misc_erflip_smalllegs import _tape, _src

F0, F1 = "MISC_SMALLLEGS_1_0.py", "MISC_SMALLLEGS_1_1.py"


@pytest.fixture(scope="module")
def mods():
    return load_strategy(F0), load_strategy(F1)


@pytest.fixture(scope="module")
def tape():
    return _tape(470, eth=True, seed=3)


def _dn(s):
    return int((pd.Timestamp(s) - pd.Timestamp(1970, 1, 1)).days)


def test_marker_lookahead_and_pinned_knob(mods):
    src = _src(F1)
    assert G.MARKER_RX.search(src).group(1) == "claude-review"
    assert G.lookahead_check(src) == []
    m0, m1 = mods
    dp = m1.DEFAULT_PARAMS
    assert set(dp) == set(m0.DEFAULT_PARAMS) | {"vix_max"}
    v = dp["vix_max"]
    assert v["default"] == v["min"] == v["max"] == 15 and v["type"] == "int"
    assert A._auto_space_from_params(dp)["vix_max"] == ("int", 15, 15, 1)
    for p in m1.PARAM_GRID_PRESETS.values():
        assert p["vix_max"] == [15]
    for k in m0.DEFAULT_PARAMS:
        assert dp[k] == m0.DEFAULT_PARAMS[k]


def test_vix_max_zero_equals_1_0(mods, tape):
    m0, m1 = mods
    a = tape
    r0 = m0.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True)
    r1 = m1.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True, vix_max=0)
    assert r0["trades"] == r1["trades"] and r1["vix_skip_days"] == 0


def test_rule_drops_whole_days_on_prior_vix(mods, tape, monkeypatch):
    m0, m1 = mods
    a = tape
    ix = a["index"].tz_localize(None)
    r0 = m0.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True)
    tdays = sorted({ix[t[0]].normalize() for t in r0["trades"]})
    # VIX row per weekday: close 10 on odd day numbers, 20 on even -> session d skipped iff its PRIOR row is calm
    cal = pd.bdate_range(ix[0].normalize() - pd.Timedelta(days=10), ix[-1].normalize())
    vd = ((cal - pd.Timestamp(1970, 1, 1)).days).to_numpy(np.int64)
    vv = np.where(vd % 2 == 1, 10.0, 20.0)
    monkeypatch.setattr(m1, "_load_vix", lambda last_day, path=None, sha=None: (vd[vd <= last_day], vv[vd <= last_day]))
    r1 = m1.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True)

    def prior(d):
        dn = _dn(d)
        j = np.searchsorted(vd, dn) - 1
        return vv[j]
    calm = {d for d in tdays if prior(d) < 15}
    assert calm and len(calm) < len(tdays)
    keep = [t for t in r0["trades"] if ix[t[0]].normalize() not in calm]
    assert sorted(r1["trades"]) == sorted(keep)
    assert r1["vix_skip_days"] == len(calm) and r1["vix_missing_days"] == 0


def test_same_day_vix_row_is_never_read(mods):
    m1 = mods[1]
    days = np.array([_dn("2024-03-05"), _dn("2024-03-06")])
    vd = np.array([_dn("2024-03-04"), _dn("2024-03-05"), _dn("2024-03-06")])
    vv = np.array([20.0, 10.0, 30.0])
    skip, miss = m1._vix_skip_rows(days, 15, vix=(vd, vv))
    assert skip.tolist() == [False, True] and not miss.any()


def test_missing_vix_trades_and_is_counted(mods, tape, monkeypatch):
    m0, m1 = mods
    a = tape
    monkeypatch.setattr(m1, "_load_vix", lambda last_day, path=None, sha=None: (np.zeros(0, np.int64), np.zeros(0)))
    r0 = m0.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True)
    r1 = m1.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True)
    ix = a["index"].tz_localize(None)
    assert r1["trades"] == r0["trades"]
    assert r1["vix_missing_days"] == len({ix[t[0]].normalize() for t in r0["trades"]})
    # stale rows (> 7 calendar days old) count as missing too
    skip, miss = m1._vix_skip_rows(np.array([_dn("2024-03-20")]), 15, vix=(np.array([_dn("2024-03-01")]), np.array([9.0])))
    assert miss.tolist() == [True] and skip.tolist() == [False]


def test_cme_holiday_rows(mods):
    m1 = mods[1]
    hol = m1._cme_holiday_days(range(1990, 2027))
    for s in ("2022-05-30", "2024-07-04", "2025-01-20", "2023-11-23"):
        assert _dn(s) in hol
    for s in ("1995-01-16", "2024-11-29", "2024-12-24", "2024-03-29"):   # MLK pre-1998 traded; early closes; Good Friday shut
        assert _dn(s) not in hol
