"""MISC_AUCREV_1_0 (opus hunt strategy 85, AUCREV10, cell 85a): defaults = the hunt cell, the plugin gate lets it
through, the contract's synthetic (non-RTH) arrays never touch the panel, no panel -> no trades, and - when the
pinned panel and the hunt files are on this machine - a contract smoke on an RTH clock, the 2019 daily nets equal
the harness's daily_85a.csv, and no pick moves when every print known only after the 15:50 entry is scrambled.
Everything that reads prices runs on the panel CUT AT 2025-06-30 (tools/misc_aucrev_parity.load_plugin_sealed)."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "augur_strategies", "MISC_AUCREV_1_0.py")
HUNT_DAILY = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S85/daily_85a.csv"
sys.path.insert(0, os.path.join(REPO, "tools"))

import misc_aucrev_parity as P  # noqa: E402

PINNED = ("notional", "spread_cents", "fee_bps", "min_names")


def _defaults(mod):
    return {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}


def _rth_arrays(days):
    """A SPY-like 5m RTH clock (09:30 .. 15:55, 78 bars) on the given yyyymmdd sessions."""
    rng = np.random.default_rng(85)
    stamps = [pd.Timestamp(str(d)) + pd.Timedelta(minutes=570 + 5 * j) for d in days for j in range(78)]
    idx = pd.DatetimeIndex(stamps).tz_localize("US/Eastern")
    n = len(idx)
    close = 300 + rng.normal(0, 0.1, n).cumsum()
    openp = close + rng.normal(0, 0.05, n)
    return {"open": openp, "high": np.maximum(openp, close) + 0.05, "low": np.minimum(openp, close) - 0.05,
            "close": close, "volume": np.full(n, 1000.0), "day_id": np.repeat(np.arange(len(days)), 78),
            "index": idx, "meta": {"name": "SYN", "roll_mode": "none"}}


def test_defaults_are_cell_85a():
    mod = P.fresh_plugin()
    d = _defaults(mod)
    assert d == {"notional": 100000, "spread_cents": 1.0, "fee_bps": 0.3, "min_names": 20, "k": 5, "beta_len": 60,
                 "min_price": 40, "beta_adjust": True, "freeze_1540": False, "nasdaq_only": True, "legs": 0}
    for k, v in mod.DEFAULT_PARAMS.items():                     # every default sits inside its range and hard fence
        if "min" in v:
            assert v["min"] <= v["default"] <= v["max"], k
            assert v["hard_min"] <= v["min"] and v["max"] <= v["hard_max"], k
        if k in PINNED:
            assert v["min"] == v["max"] == v["default"], k
    assert mod.PARAM_GRID_PRESETS["Short  (the hunt cell 85a)"] == {k: [v] for k, v in d.items()
                                                                    if k not in PINNED[:3]}
    from augur_engine.auto import _auto_space_from_params
    size = 1
    for spec in _auto_space_from_params(mod.DEFAULT_PARAMS).values():
        size *= len(spec[1]) if spec[0] == "cat" else int(round((spec[2] - spec[1]) / spec[3])) + 1
    assert size == 6720


def test_plugin_gate_lets_it_through():
    from augur_engine import plugin_gate as G
    with open(PLUGIN, "rb") as f:
        src = G.lf_bytes(f.read()).decode("utf-8")
    assert G.MARKER_RX.search(src).group(1) == "claude-review"
    assert G.lookahead_check(src) == []
    G.gate_plugin(PLUGIN)                                         # raises PluginGateError on a refusal


def test_synthetic_contract_arrays_never_touch_the_panel():
    """tests/test_strategy_contract.py hands every plugin a continuous 5m tape dated 2026-03 (inside the engine's
    lockbox). Its days do not end on a 15:55 bar, so the plugin returns None BEFORE it opens the panel."""
    rng = np.random.default_rng(7)                                # the contract test's _make_arrays(), 10 x 78 bars
    n = 780
    close = 15000 + rng.normal(0, 1, n).cumsum()
    idx = pd.date_range("2026-03-02 09:30", periods=n, freq="5min", tz="US/Eastern")
    mod = P.fresh_plugin()
    r = mod.run_backtest(close, close + 1, close - 1, close, np.full(n, 1000.0),
                         np.repeat(np.arange(10), 78).astype("int64"), idx, return_trades=True)
    assert r is None
    assert "panel" not in mod._CACHE


def test_no_panel_no_trades():
    mod = P.fresh_plugin()
    mod.PANEL_PATH = os.path.join(REPO, "no_such_dir", "aucrev_panel_v1.npz")
    a = _rth_arrays([20190304, 20190305, 20190306])
    from augur_engine import run_backtest
    assert run_backtest(mod, arrays=a, params={}, return_trades=True) is None
    assert mod._CACHE.get("panel", "missing") is None


def test_contract_smoke_on_an_rth_clock():
    mod, p = P.load_plugin_sealed()
    if p is None:
        pytest.skip("pinned panel not on this machine")
    days = [int(d) for d in p["days"] if 20190101 <= d <= 20191231]
    a = _rth_arrays(days)
    from augur_engine import run_backtest
    r = run_backtest(mod, arrays=a, params={}, return_trades=True)
    assert {"total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown", "avg_pnl", "wins",
            "losses"} <= set(r)
    want = P.plugin_daily(mod, p)
    want = want[(want.index >= 20190101) & (want.index <= 20191231)]
    assert r["num_trades"] == len(want) > 200
    idx = pd.DatetimeIndex(a["index"]).tz_localize(None)
    for t in r["trades"]:
        e, x = idx[t[0]], idx[t[1]]
        assert e.date() == x.date() and (e.hour, e.minute) == (15, 50) and (x.hour, x.minute) == (15, 55)
        assert abs(t[2] - want[int(e.strftime("%Y%m%d"))]) < 1e-9
    assert mod.mark_open_trades(r["trades"], a["open"], a["high"], a["low"], a["close"]) == [[]] * len(r["trades"])


def test_2019_daily_nets_match_harness_85a():
    mod, p = P.load_plugin_sealed()
    if p is None or not os.path.exists(HUNT_DAILY):
        pytest.skip("pinned panel or hunt daily file not on this machine")
    got = P.plugin_daily(mod, p)
    got = got[(got.index >= 20190101) & (got.index <= 20191231)]
    H = pd.read_csv(HUNT_DAILY)
    H.index = pd.to_datetime(H.iloc[:, 0]).dt.strftime("%Y%m%d").astype("int64")
    H = H[(H.index >= 20190101) & (H.index <= 20191231)]
    assert list(got.index) == list(H.index) and len(H) > 200
    assert (got - H["net"]).abs().max() < 1e-6


def test_picks_ignore_prints_known_after_the_entry():
    """Look-ahead check. For sample sessions t: drop every later session, scramble t's 15:50-bar open and close,
    official close and raw close (all names, SPY included) and rebuild the frames. The long / short picks and the
    day's eligible count must not move. (b) with the official close and the 15:50-bar close scaled by ONE factor
    per name (the hygiene ratio unchanged) and the 15:50-bar open by another, the traded names after the hygiene
    drop must not move either, while the day's net does."""
    mod, p = P.load_plugin_sealed()
    if p is None:
        pytest.skip("pinned panel not on this machine")
    cut = P.sealed_arrays(mod)
    d = _defaults(mod)
    knobs = ("k", "beta_len", "min_price", "beta_adjust", "freeze_1540", "nasdaq_only", "min_names")
    L, S, n = mod._picks(p, *[d[x] for x in knobs])
    rows = np.flatnonzero(L.any(axis=1).to_numpy())
    rng = np.random.default_rng(1085)
    moved_net = 0
    for i in rows[np.linspace(0, len(rows) - 1, 10).astype(int)]:
        for mode in ("independent", "consistent"):
            c = {key: (v[:i + 1].copy() if key in P.SESSION_KEYS else v) for key, v in cut.items()}
            f = {key: rng.uniform(0.5, 1.5, c[key].shape[1]) for key in ("o55", "c55", "split", "raw")}
            if mode == "consistent":
                g = rng.uniform(0.5, 1.5, c["split"].shape[1])
                f["split"] = g
                f["c55"][:-1] = g                                # SPY (last column) keeps its own factor
            for key, fac in f.items():
                c[key][i] = (c[key][i] * fac).astype(c[key].dtype)
            p2 = mod._frames(c)
            L2, S2, n2 = mod._picks(p2, *[d[x] for x in knobs])
            day = p["days"][i]
            assert (L2.iloc[i] == L.iloc[i]).all() and (S2.iloc[i] == S.iloc[i]).all(), (day, mode)
            assert int(n2.iloc[i]) == int(n.iloc[i]), (day, mode)
            if mode == "consistent":
                assert ((L2.iloc[i] & p2["okx"].iloc[i]) == (L.iloc[i] & p["okx"].iloc[i])).all(), day
                assert ((S2.iloc[i] & p2["okx"].iloc[i]) == (S.iloc[i] & p["okx"].iloc[i])).all(), day
                dd1, net1 = mod._daily(p, **d)
                dd2, net2 = mod._daily(p2, **d)
                a1 = net1[np.searchsorted(dd1, day)]
                a2 = net2[np.searchsorted(dd2, day)]
                moved_net += abs(a1 - a2) > 1e-6
    assert moved_net >= 8                                        # the scramble really reached the PnL
