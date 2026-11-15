"""MISC_DEFROT_1_0 (OPUS-HUNT strategy 107a): defaults = the hunt cell, the plugin gate passes, and - when the pinned
ETF side panel is on the machine - the z series and trades agree with the hunt's sess.pkl on a few 2016 dates."""
import os

import numpy as np
import pandas as pd
import pytest

from augur_engine import plugin_gate
from augur_engine.paths import STRAT_DIR
from augur_engine.strategies import strategy_params
from augur_engine import load_strategy

FILE = "MISC_DEFROT_1_0.py"
PATH = os.path.join(STRAT_DIR, FILE)


@pytest.fixture(scope="module")
def mod():
    return load_strategy(FILE)


def test_defaults_are_cell_107a(mod):
    d = {k: v["default"] for k, v in strategy_params(mod).items()}
    assert d == {"sig_min": 720, "z_thr": 1.0, "win": 60, "basket": 0, "exit_min": 960, "sides": 0}
    assert mod._DEF[0] == ("XLU", "XLP", "XLV") and mod._CYC[0] == ("XLY", "XLK", "XLI", "XLF")
    assert mod._AUGUR_MARKET == {"instrument": "NQ", "timeframe": "5m", "session": "rth", "source": "db_adj_rth"}
    short = mod.PARAM_GRID_PRESETS["Short  (the hunt cell 107a)"]
    assert {k: v[0] for k, v in short.items()} == d
    for k, v in strategy_params(mod).items():                     # ranged, never pinned
        assert v["min"] < v["max"], k
        assert v["min"] <= v["default"] <= v["max"], k


def test_plugin_gate_passes():
    rep = plugin_gate.inspect_plugin(PATH)
    assert rep["ok"], rep["reasons"]
    assert plugin_gate.lookahead_check(open(PATH, encoding="utf-8").read()) == []


def _panel_or_skip(mod):
    if not os.path.exists(mod.PANEL_PATH):
        pytest.skip("DEFROT side panel not on this machine")
    return mod._panel()


def test_z_matches_hunt_2016(mod):
    p = _panel_or_skip(mod)
    zm = mod._zmap(p, 720, 0, 60)
    assert min(zm) == 20160331                                    # the 61st eligible session, as the hunt
    want = {20160331: -0.012212, 20160401: 0.588914, 20160701: -1.081445, 20160705: 2.310627, 20160707: -1.938179}
    for d, z in want.items():
        assert zm[d] == pytest.approx(z, abs=1e-5), d


def test_trades_follow_z_sign(mod):
    _panel_or_skip(mod)
    days = ["2016-07-01", "2016-07-05", "2016-07-06", "2016-07-07"]
    idx = pd.DatetimeIndex([t for d in days for t in pd.date_range(d + " 09:30", periods=78, freq="5min",
                                                                     tz="US/Eastern")])
    n = len(idx)
    c = 15000.0 + np.arange(n, dtype=float)                       # rising tape: long wins, short loses
    o = c - 0.5
    r = mod.run_backtest(o, c + 1, o - 1, c, index=idx, return_trades=True)
    got = {str(idx[t[0]].date()): (t[3], idx[t[0]].strftime("%H:%M"), idx[t[1]].strftime("%H:%M")) for t in r["trades"]}
    # 07-01 z -1.08 -> long; 07-05 z +2.31 -> short; 07-06 |z| < 1 -> none; 07-07 z -1.94 -> long
    assert got == {"2016-07-01": (1, "12:00", "15:55"), "2016-07-05": (-1, "12:00", "15:55"),
                   "2016-07-07": (1, "12:00", "15:55")}
    t0 = r["trades"][0]
    assert t0[2] == pytest.approx(c[t0[1]] - o[t0[0]])            # exit = close of the 15:55 bar
    r2 = mod.run_backtest(o, c + 1, o - 1, c, index=idx, return_trades=True, sides=1)
    assert [t[3] for t in r2["trades"]] == [-1]
    r3 = mod.run_backtest(o, c + 1, o - 1, c, index=idx, return_trades=True, exit_min=840)
    t3 = r3["trades"][0]
    assert idx[t3[1]].strftime("%H:%M") == "14:00" and t3[5] == o[t3[1]]   # exit = open of the 14:00 bar
