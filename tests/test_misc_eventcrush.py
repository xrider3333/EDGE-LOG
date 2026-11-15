"""MISC_EVENTCRUSH_1_0 (opus hunt strategy 94, cell 94a): defaults = the hunt cell, the plugin gate lets it through,
the frozen event calendar equals its source files, no panel -> no trades, and (when the pinned panel, the VIXY master
and the hunt files are on this machine) the default trades match the harness's 94a trades on 2018, the engine path
returns the same trades, and nothing known only after an entry print changes that trade or the trade list.
Everything real runs on the panel CUT AT 2025-06-30 and the VIXY master loaded to 2025-06-30
(tools/misc_eventcrush_parity.load_plugin_sealed / load_vixy); the synthetic smoke runs on 2019 dates."""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "augur_strategies", "MISC_EVENTCRUSH_1_0.py")
sys.path.insert(0, os.path.join(REPO, "tools"))

import misc_eventcrush_parity as P  # noqa: E402

SHARED_BLS = os.path.join(P.SHARED, "tools", "data", "bls_dates.txt")
HUNT_TRADES = P.HUNT + "trades_94a.csv"
PINNED = ("notional", "cents_share", "fee_bps", "borrow_pct")
DEFAULTS_94A = {"notional": 50000, "cents_share": 0.5, "fee_bps": 0.3, "borrow_pct": 10.0,
                "events": "FOMC+CPI+EMP", "entry_min": 960, "exit_min": 960, "block": "hold", "hedge": False}
OTHER_CFGS = ({"hedge": True, "entry_min": 900, "exit_min": 630}, {"events": "FOMC+EMP", "block": "first"},
              {"events": "CPI+EMP", "entry_min": 840, "exit_min": 720, "block": "single", "hedge": True})


def _fresh_module():
    spec = importlib.util.spec_from_file_location("misc_eventcrush_1_0_fresh", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic(days=("2019-03-05", "2019-03-06", "2019-03-07", "2019-03-08", "2019-03-11", "2019-03-12",
                     "2019-03-13")):
    """Seeded random-walk 5m RTH bars on real 2019 sessions (EMP 03-08 and CPI 03-12 inside, both before the seal)."""
    rng = np.random.default_rng(94)
    idx = pd.DatetimeIndex(np.concatenate([pd.date_range(d + " 09:30", periods=78, freq="5min", tz="US/Eastern")
                                           for d in days]))
    n = len(idx)
    c = 3000 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    o = c * (1 + rng.normal(0, 0.0005, n))
    return {"open": o, "high": np.maximum(o, c) * 1.001, "low": np.minimum(o, c) * 0.999, "close": c,
            "volume": np.full(n, 1000.0), "day_id": np.repeat(np.arange(len(days)), 78).astype("int64"),
            "index": idx, "meta": {"name": "SYN", "roll_mode": "none"}}


@pytest.fixture(scope="module")
def real():
    """(module, sealed panel, VIXY 2017-11-01 .. 2018-12-31) or a skip."""
    mod, p = P.load_plugin_sealed()
    if p is None:
        pytest.skip("pinned panel not on this machine")
    arr = P.load_vixy("2017-11-01", "2018-12-31")
    if arr is None:
        pytest.skip("VIXY master not on this machine")
    return mod, p, arr


def test_defaults_are_cell_94a():
    mod = _fresh_module()
    d = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    assert d == DEFAULTS_94A
    grid = 1
    for k, v in mod.DEFAULT_PARAMS.items():
        if "options" in v:
            assert v["default"] in v["options"], k
            grid *= len(v["options"])
        elif v["type"] == "bool":
            grid *= 2
        else:
            assert v["hard_min"] <= v["min"] <= v["default"] <= v["max"] <= v["hard_max"], k
            grid *= int(round((v["max"] - v["min"]) / v["step"])) + 1
        if k in PINNED:
            assert v["min"] == v["max"] == v["default"] == v["hard_min"] == v["hard_max"], k
    assert grid == 2730                                       # 7 event sets x 5 entry x 13 exit x 3 block x 2 hedge
    assert set(mod.DEFAULT_PARAMS["events"]["options"]) == set(mod.EVENT_SETS)
    assert mod.PARAM_GRID_PRESETS["Short  (the hunt cell 94a)"] == {k: [v] for k, v in d.items() if k not in PINNED}
    import inspect
    sig = {k: v.default for k, v in inspect.signature(mod.run_backtest).parameters.items() if k in d}
    assert sig == d
    assert mod.PNL_UNITS == "usd" and mod._AUGUR_MARKET == {"instrument": "VIXY", "timeframe": "5m", "session": "rth",
                                                             "source": "alpaca_split_rth"}


def test_event_calendar_is_the_source_files():
    mod = _fresh_module()
    lo, hi = "2016-01-01", "2026-06-30"
    fomc = [ln.strip() for ln in open(os.path.join(REPO, "tools", "data", "fomc_dates.txt"))
            if ln.strip() and not ln.startswith("#")]
    assert mod.EVENT_DAYS["FOMC"].tolist() == sorted(int(x.replace("-", "")) for x in fomc if lo <= x <= hi)
    assert len(mod.EVENT_DAYS["FOMC"]) == 83
    if not os.path.exists(SHARED_BLS):
        pytest.skip("tools/data/bls_dates.txt (untracked) not in the shared checkout here")
    bls = [ln.strip().split("|") for ln in open(SHARED_BLS) if ln.strip() and not ln.startswith("#")]
    for kind in ("CPI", "EMP"):
        want = sorted(int(b[1].replace("-", "")) for b in bls if b[0] == kind and lo <= b[1] <= hi)
        assert mod.EVENT_DAYS[kind].tolist() == want, kind
        assert len(want) == 125


def test_plugin_gate_lets_it_through():
    from augur_engine import plugin_gate as G
    with open(PLUGIN, "rb") as f:
        src = G.lf_bytes(f.read()).decode("utf-8")
    assert G.MARKER_RX.search(src).group(1) == "claude-review"
    assert G.lookahead_check(src) == []
    G.gate_plugin(PLUGIN)                                         # raises PluginGateError on a refusal


def test_no_panel_no_trades():
    from augur_engine import run_backtest
    mod = _fresh_module()
    mod.PANEL_PATH = os.path.join(REPO, "no_such_dir", "eventcrush_panel_missing.npz")
    mod._CACHE.clear()
    syn = _synthetic()
    assert mod.run_backtest(syn["open"], syn["high"], syn["low"], syn["close"], index=syn["index"]) is None
    assert run_backtest(mod, arrays=syn, params={}, return_trades=True) is None
    assert mod.mark_open_trades([(10, 400, 1.0, -1, 1.0, 1.0)], syn["open"], syn["high"], syn["low"], syn["close"],
                                index=syn["index"]) == [[]]
    assert mod.run_backtest(syn["open"], syn["high"], syn["low"], syn["close"]) is None      # no index -> None


def test_contract_smoke_on_synthetic_2019_bars():
    """Through the engine like a job: well-formed metrics, one short per block from P's close to the event close."""
    from augur_engine import run_backtest
    mod = _fresh_module()
    syn = _synthetic()
    r = run_backtest(mod, arrays=syn, params={}, return_trades=True)
    if mod._panel() is None:
        assert r is None
        pytest.skip("pinned panel not on this machine")
    assert {"total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown", "avg_pnl", "wins",
            "losses"} <= set(r)
    idx = syn["index"]
    got = [(str(idx[t[0]]), str(idx[t[1]]), t[3]) for t in r["trades"]]
    assert got == [("2019-03-07 15:55:00-05:00", "2019-03-08 15:55:00-05:00", -1),     # EMP 03-08
                   ("2019-03-11 15:55:00-04:00", "2019-03-12 15:55:00-04:00", -1)]     # CPI 03-12 (DST)
    for t in r["trades"]:
        assert t[4] == syn["close"][t[0]] and t[5] == syn["close"][t[1]] and np.isfinite(t[2])
    r2 = run_backtest(mod, arrays=syn, params={"entry_min": 900, "exit_min": 630}, return_trades=True)
    got2 = [(str(idx[t[0]]), str(idx[t[1]])) for t in r2["trades"]]
    assert got2 == [("2019-03-07 14:55:00-05:00", "2019-03-08 10:25:00-05:00"),
                    ("2019-03-11 14:55:00-04:00", "2019-03-12 10:25:00-04:00")]
    marks = mod.mark_open_trades(r2["trades"], syn["open"], syn["high"], syn["low"], syn["close"],
                                 index=idx, entry_min=900, exit_min=630)
    for t, m in zip(r2["trades"], marks):                     # one mark: P's 15:55 bar, valued short from the entry
        assert [k for k, _ in m] == [t[0] + 12]
        assert m[0][1] == pytest.approx(-50000 * (syn["close"][t[0] + 12] / t[4] - 1))
    assert run_backtest(mod, arrays=syn, params={"events": "nope"}) is None


def test_2018_trades_match_harness_94a(real):
    mod, p, arr = real
    if not os.path.exists(HUNT_TRADES):
        pytest.skip("hunt trades not on this machine")
    T = P.plugin_trades(mod, p, arr)
    T = T[T.P.dt.year == 2018].sort_values("P").reset_index(drop=True)
    H = pd.read_csv(HUNT_TRADES, parse_dates=["P", "Ek"])
    H = H[H.P.dt.year == 2018].sort_values("P").reset_index(drop=True)
    assert len(T) == len(H) > 25
    assert (T.P.values == H.P.values).all() and (T.Ek.values == H.Ek.values).all()
    assert np.allclose(T.c0, H.C_P, rtol=1e-12, atol=0) and np.allclose(T.c1, H.C_Ek, rtol=1e-12, atol=0)
    assert (T.net - H.net).abs().max() < 1e-6 and (T.cost - H.cost).abs().max() < 1e-6


def test_engine_path_returns_the_same_trades(real):
    from augur_engine import run_backtest
    mod, p, arr = real
    for kw in ({},) + OTHER_CFGS:
        r = run_backtest(mod, arrays=arr, params=dict(kw), return_trades=True)
        rows = mod._trades(p, arr["index"], arr["close"], **dict({k: v["default"] for k, v in
                                                                  mod.DEFAULT_PARAMS.items()}, **kw))
        assert len(rows) > 5, kw
        assert [(t[0], t[1], round(t[2], 6)) for t in r["trades"]] == \
            [(q["e"], q["x"], round(q["net"], 6)) for q in sorted(rows, key=lambda q: q["x"])], kw


def _scrambled(mod, p, arr, r, entry_min, seed):
    """Copies of the bars and the panel with everything known only after trade r's entry print replaced at random:
    every bar after the entry bar; every panel row after P; P's own daily close LEVELS (raw and split moved by one
    common factor, so the day's corporate-action ratio stays) and SPY's 5m bars on P after the entry clock when the
    entry is before the 16:00 close."""
    rng = np.random.default_rng(seed)
    a = dict(arr)
    e = r["e"]
    for k in ("open", "high", "low", "close"):
        v = np.array(arr[k], float)
        v[e + 1:] *= rng.uniform(0.5, 1.5, len(v) - e - 1)
        a[k] = v
    q = {k: np.array(p[k], float) for k in P.PANEL_KEYS if k != "dates"}
    q["dates"] = p["dates"]
    iP = r["iP"]
    after = len(q["dates"]) - iP - 1
    for k in ("vixy_raw", "vixy_split", "spy_raw", "spy_split"):
        q[k][iP + 1:] *= rng.uniform(0.5, 1.5, after)
    q["spy5"][iP + 1:] *= rng.uniform(0.5, 1.5, q["spy5"][iP + 1:].shape)
    if entry_min < 960:
        for pair in (("vixy_raw", "vixy_split"), ("spy_raw", "spy_split")):
            f = rng.uniform(0.5, 1.5)
            for k in pair:
                q[k][iP] *= f
        slot = (entry_min - 5 - 570) // 5
        q["spy5"][iP, slot + 1:] *= rng.uniform(0.5, 1.5, 78 - slot - 1)
    return a, mod._derive(q)


@pytest.mark.parametrize("kw", ({},) + OTHER_CFGS)
def test_nothing_after_the_entry_print_changes_the_trade(real, kw):
    mod, p, arr = real
    prm = dict({k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}, **kw)
    base = mod._trades(p, arr["index"], arr["close"], **prm)
    assert len(base) > 8
    entry_keys = ("e", "x", "P", "X", "c0", "shares", "beta", "H", "s0")
    for n_cut, r in enumerate(base[::4]):
        a, q = _scrambled(mod, p, arr, r, prm["entry_min"], seed=9400 + n_cut)
        got = mod._trades(q, a["index"], a["close"], **prm)
        before = [g for g in got if g["e"] <= r["e"]]
        want = [b for b in base if b["e"] <= r["e"]]
        assert len(before) == len(want), (kw, r["P"])
        for g, b in zip(before, want):
            for k in entry_keys:
                # bars and dates exactly; prices / sizes to 1e-12: an early entry reads P's raw / split RATIO (the
                # day's split factor), which the common-factor level scramble keeps up to float rounding - a leak
                # of P's close LEVEL would move shares by up to 50 percent
                assert (g[k] == b[k] or (np.isnan(g[k]) and np.isnan(b[k]))
                        or (k not in ("e", "x", "P", "X") and np.isclose(g[k], b[k], rtol=1e-12, atol=0))), \
                    (kw, r["P"], k)
            if b["x"] < r["e"]:                               # closed before the cut: byte-identical
                assert g["net"] == b["net"], (kw, r["P"])
        # the whole trade list (entry and exit bars) is set by the calendar and the clocks, never by prices
        assert [(g["e"], g["x"]) for g in got] == [(b["e"], b["x"]) for b in base], (kw, r["P"])


def test_truncated_bars_keep_the_closed_trades(real):
    """Cut the bars at a session end and inside a session: trades that closed before the cut are unchanged, and a
    trade whose exit session is cut before its exit bar is dropped, never closed early."""
    mod, p, arr = real
    base = mod._trades(p, arr["index"], arr["close"])
    idx = pd.DatetimeIndex(arr["index"])
    r = next(b for b in base[len(base) // 2:] if (idx[b["x"]].hour, idx[b["x"]].minute) == (15, 55))
    for cut in (r["x"] + 1, r["x"]):                          # through the exit bar / one bar short of it
        got = mod._trades(p, arr["index"][:cut], arr["close"][:cut])
        assert [(g["e"], g["x"], g["net"]) for g in got if g["x"] < r["e"]] == \
               [(b["e"], b["x"], b["net"]) for b in base if b["x"] < r["e"]]
        last = [g for g in got if g["e"] == r["e"]]
        assert (len(last) == 1 and last[0]["x"] == r["x"]) if cut == r["x"] + 1 else last == []


def test_marks_value_a_held_run(real):
    """The 2018-06-11 -> 06-13 run (CPI 06-12, FOMC 06-13): marks at P's and 06-12's last bars, short-side values."""
    mod, p, arr = real
    idx = arr["index"]
    res = mod.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"], index=idx, return_trades=True)
    t = [t for t in res["trades"] if str(idx[t[0]].date()) == "2018-06-11"]
    assert len(t) == 1 and str(idx[t[0][1]].date()) == "2018-06-13"
    m = mod.mark_open_trades(t, arr["open"], arr["high"], arr["low"], arr["close"], index=idx)[0]
    assert [str(idx[k]) for k, _ in m] == ["2018-06-11 15:55:00-04:00", "2018-06-12 15:55:00-04:00"]
    assert m[0][1] == 0.0
    assert m[1][1] == pytest.approx(-50000 * (arr["close"][m[1][0]] / t[0][4] - 1))
