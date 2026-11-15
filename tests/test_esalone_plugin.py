"""MISC_ESALONE_1_0.py (opus hunt strategy 73, cell 73d): defaults = the cell, the file passes the plugin gate's
static checks, the pinned NQ panel decodes, and the transcribed walk equals its parent ENGUQ_1M_ETH_R2_1_0.py
trade for trade on synthetic bars. Real-data parity vs the hunt is tools/esalone_nq_panel.py parity (slow)."""
import importlib.util
import os

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "augur_strategies", "MISC_ESALONE_1_0.py")
PARENT = os.path.join(ROOT, "augur_strategies", "ENGUQ_1M_ETH_R2_1_0.py")

CELL_73D = dict(er_len=100, er_th=0.0, limit_atr=0.55, tl_len=206, vol_mult=1.1, stop_mult=1.0, act_R=1.5,
                trail_frac=2.5, buf_atr=0.3, min_brk=1.6, ema_len=220, atr_len=52, regime_len=10, breakeven_R=2.0,
                nq_gate=0)


def _load(path, name):
    if not os.path.exists(path):
        pytest.skip("%s missing" % path)
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def mod():
    return _load(PLUGIN, "MISC_ESALONE_1_0_t")


def _bars(n=60000, seed=3):
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.normal(0, 0.05, n // 500 + 1), 500)[:n]
    c = 3000 + np.cumsum(rng.normal(0, 0.6, n) + drift)
    c = np.round(c * 4) / 4
    o = np.concatenate([[c[0]], c[:-1]]) + np.round(rng.normal(0, 0.3, n) * 4) / 4
    h = np.maximum(o, c) + np.round(np.abs(rng.normal(0, 0.5, n)) * 4) / 4
    l = np.minimum(o, c) - np.round(np.abs(rng.normal(0, 0.5, n)) * 4) / 4
    v = np.abs(rng.normal(1000, 400, n)) + 1
    idx = pd.date_range("2024-01-02 18:00", periods=n, freq="1min", tz="US/Eastern")
    return o, h, l, c, v, idx


def test_defaults_are_cell_73d(mod):
    d = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    assert d == CELL_73D
    for k, v in mod.DEFAULT_PARAMS.items():                      # every default sits on its own grid
        assert v["min"] <= v["default"] <= v["max"], k
        q = (v["default"] - v["min"]) / v["step"]
        assert abs(q - round(q)) < 1e-9, k
    assert mod._AUGUR_MARKET == {"instrument": "ES", "timeframe": "1m", "session": "eth", "source": "db_adj_eth"}


def test_parent_defaults_unchanged():
    par = _load(PARENT, "ENGUQ_R2_t")
    d = {k: v["default"] for k, v in par.DEFAULT_PARAMS.items()}
    assert d == {k: v for k, v in CELL_73D.items() if k != "nq_gate"}


def test_gate_static_checks_pass():
    from augur_engine.plugin_gate import safety_check, lookahead_check, provenance
    src = open(PLUGIN, encoding="utf-8").read()
    assert src.startswith("# AUGUR-SOURCE: claude-review")
    assert safety_check(src) == []
    assert lookahead_check(src) == []
    assert provenance(PLUGIN, src) is None                       # claude-review = reviewed source, not gated


def test_panel_decodes(mod):
    st, en = mod._nq_intervals()
    assert len(st) == mod._NQ_HEAD[2] > 1500
    assert np.all(en > st) and np.all(st[1:] >= en[:-1])
    assert st[0] >= mod._NQ_HEAD[0]                               # head[0] = first NQ bar, not first trade
    end = pd.Timestamp("2026-06-30 17:00", tz="America/New_York").tz_convert("UTC").tz_localize(None)
    assert mod._NQ_HEAD[1] == end.value // 60_000_000_000
    assert en[-1] <= mod._NQ_HEAD[1]


@pytest.mark.parametrize("prm", [
    dict(tl_len=60, min_brk=0.8, buf_atr=0.1, vol_mult=0.0, ema_len=140, atr_len=36, regime_len=0),
    dict(tl_len=60, min_brk=0.8, buf_atr=0.1, vol_mult=0.9, ema_len=140, atr_len=36, regime_len=5, limit_atr=0.0),
    dict(tl_len=80, min_brk=1.0, buf_atr=0.2, vol_mult=0.0, ema_len=200, atr_len=40, regime_len=0, stop_mult=0.8,
         act_R=1.0, trail_frac=1.5, breakeven_R=1.5, er_th=0.1, er_len=60),
])
def test_walk_equals_parent(mod, prm):
    par = _load(PARENT, "ENGUQ_R2_t")
    o, h, l, c, v, idx = _bars()
    full = dict(CELL_73D); full.update(prm)
    mine = mod.run_backtest(o, h, l, c, v, index=idx, return_trades=True, **full)
    pp = {k: x for k, x in full.items() if k != "nq_gate"}
    ref = par.run_backtest(o, h, l, c, v, return_trades=True, **pp)
    assert ref is not None and len(ref["trades"]) >= 20
    a = [(t[0], t[1], round(t[2], 9)) for t in mine["trades"]]
    b = [(t[0], t[1], round(t[2], 9)) for t in ref["trades"]]
    assert a == b


def test_gates_on_synthetic(mod):
    o, h, l, c, v, idx = _bars()
    base = dict(CELL_73D, tl_len=60, min_brk=0.8, buf_atr=0.1, vol_mult=0.0, ema_len=140, atr_len=36, regime_len=0)
    r0 = mod.run_backtest(o, h, l, c, v, index=idx, return_trades=True, **base)
    r1 = mod.run_backtest(o, h, l, c, v, index=idx, return_trades=True, **dict(base, nq_gate=1))
    t0 = {(t[0], t[1]) for t in r0["trades"]}
    t1 = set() if r1 is None else {(t[0], t[1]) for t in r1["trades"]}
    assert t1 <= t0                                               # the shadow gate only drops trades
    late = pd.date_range("2026-07-06 18:00", periods=len(c), freq="1min", tz="US/Eastern")
    assert mod.run_backtest(o, h, l, c, v, index=late, **dict(base, nq_gate=1)) is None   # past the panel: no trades
    assert mod.run_backtest(o, h, l, c, v, index=late, **dict(base, nq_gate=2)) is None
    assert mod.run_backtest(o, h, l, c, v, index=None, **dict(base, nq_gate=1)) is None   # no clock: refuse
