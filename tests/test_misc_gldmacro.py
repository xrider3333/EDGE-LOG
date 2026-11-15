"""MISC_GLDMACRO_1_0 (opus hunt strategy 97, GLD-MACRODAY, cell 97a): defaults = the hunt cell and a 14-point grid, the
frozen release calendar = the source files (and strategy 94's lists), the plugin gate lets it through, the contract's
synthetic 24-hour tape never touches the panel, no panel -> no trades, and - when the pinned panel, the hunt files and
the GLD 5m master are on this machine - the 2019 trades equal the harness's trades_97a.csv to the cent on an RTH clock
and on the real master (97b within the hunt's float32 rounding), slice edges never close a trade early or open it
late, and nothing known only after the entry print moves a trade, with three broken variants caught by the same check.
Everything that reads prices runs on the panel CUT AT 2025-06-30 (tools/misc_gldmacro_parity.load_plugin_sealed) and
on master bars loaded only through 2019."""
import importlib.util
import os
import sqlite3
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "augur_strategies", "MISC_GLDMACRO_1_0.py")
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S97/"
sys.path.insert(0, os.path.join(REPO, "tools"))

import misc_gldmacro_parity as P  # noqa: E402

PINNED = ("notional", "cents_share", "fee_bps")
METRIC_KEYS = {"total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown", "avg_pnl", "wins", "losses"}
ENTRY_KEYS = ("e", "x", "D", "entry_day", "row", "px", "shares", "p_in")


def _defaults(mod):
    return {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}


def _rth_arrays(days, last_min, seed=97):
    """A GLD-like 5m RTH clock on the given yyyymmdd sessions: bars from 09:30 to each session's own last bar (half
    days and the 2019-08-12 hole included), random-walk prices."""
    rng = np.random.default_rng(seed)
    days = np.asarray(days, np.int64)
    nb = (np.asarray(last_min, np.int64) - 570) // 5 + 1
    base = pd.to_datetime(pd.Series(days.astype(str)), format="%Y%m%d").to_numpy()
    off = (np.concatenate([np.arange(k) for k in nb]) * 5 + 570).astype("timedelta64[m]")
    idx = pd.DatetimeIndex(np.repeat(base, nb) + off).tz_localize("US/Eastern")
    n = len(idx)
    close = 150 + rng.normal(0, 0.05, n).cumsum()
    openp = close + rng.normal(0, 0.02, n)
    return {"open": openp, "high": np.maximum(openp, close) + 0.02, "low": np.minimum(openp, close) - 0.02,
            "close": close, "volume": np.full(n, 1000.0), "day_id": np.repeat(np.arange(len(days)), nb).astype("int64"),
            "index": idx, "meta": {"name": "SYN", "roll_mode": "none"}}


def _years(p, y0, y1):
    k = (p["dates"] >= y0 * 10000 + 101) & (p["dates"] <= y1 * 10000 + 1231)
    return p["dates"][k], p["last_min"][k]


def _hunt(cell):
    path = HUNT + "trades_%s.csv" % cell
    if not os.path.exists(path):
        pytest.skip("hunt trades not on this machine")
    H = pd.read_csv(path)
    for c in ("D", "Dm1"):
        H[c] = pd.to_datetime(H[c]).dt.strftime("%Y%m%d").astype("int64")
    return H


def _ymd(ts):
    return int(ts.strftime("%Y%m%d"))


@pytest.fixture(scope="module")
def sealed():
    mod, p = P.load_plugin_sealed()
    if p is None:
        pytest.skip("pinned panel not on this machine")
    assert int(p["dates"].max()) <= 20250630
    return mod, p


@pytest.fixture(scope="module")
def syn(sealed):
    """The RTH clock of every 2018-2019 panel session (2018 gives the first 2019 trade its D-1)."""
    _, p = sealed
    return _rth_arrays(*_years(p, 2018, 2019))


@pytest.fixture(scope="module")
def master_2019():
    """The GLD 5m RTH alpaca_split_rth master, 2018-12-03 .. 2019-12-31 only. A worktree has no registry or uploads of
    its own, so the row is read (read-only) from the shared checkout's registry and the CSV from its augur_uploads;
    the arrays then carry the registry row itself as their meta, exactly as a load in the shared checkout would."""
    db = os.path.join(SHARED, "optimizer_history.db")
    if not os.path.exists(db):
        pytest.skip("master registry not on this machine")
    row = None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
        try:
            row = con.execute("SELECT id, filename, source, session, instrument, timeframe FROM csv_files "
                              "WHERE is_master=1 AND instrument='GLD' AND timeframe='5m' AND lower(session)='rth' "
                              "AND source='alpaca_split_rth'").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        row = None
    path = os.path.join(SHARED, "augur_uploads", row[1]) if row else None
    if path is None or not os.path.exists(path):
        pytest.skip("GLD 5m master not on this machine")
    from augur_engine.data import load_master_arrays
    m = dict(zip(("id", "filename", "source", "session", "instrument", "timeframe"), row))
    arr = load_master_arrays(dict(m, filename=path), date_from="2018-12-03", date_to="2019-12-31")
    arr["meta"] = m
    assert pd.DatetimeIndex(arr["index"]).max() < pd.Timestamp("2020-01-01", tz="US/Eastern")
    return arr


# ---------------------------------------------------------------------------------------------------- contract, ranges
def test_defaults_are_cell_97a():
    mod = P.fresh_plugin()
    d = _defaults(mod)
    assert d == {"notional": 250000, "cents_share": 0.5, "fee_bps": 0.3, "events": "FOMC+CPI+EMP",
                 "entry": "prior_close"}
    for k, v in mod.DEFAULT_PARAMS.items():                     # every default sits inside its range and hard fence
        if "min" in v:
            assert v["min"] <= v["default"] <= v["max"], k
            assert v["hard_min"] <= v["min"] and v["max"] <= v["hard_max"], k
        if k in PINNED:
            assert v["min"] == v["max"] == v["default"] == v["hard_min"] == v["hard_max"], k
    assert mod.PARAM_GRID_PRESETS["Short  (the hunt cell 97a)"] == {"events": ["FOMC+CPI+EMP"],
                                                                    "entry": ["prior_close"]}
    from augur_engine.auto import _auto_space_from_params
    space = _auto_space_from_params(mod.DEFAULT_PARAMS)
    size = 1
    for spec in space.values():
        size *= len(spec[1]) if spec[0] == "cat" else int(round((spec[2] - spec[1]) / spec[3])) + 1
    assert size == 14                                            # 7 release calendars x 2 entry clocks
    assert {"FOMC+CPI+EMP", "CPI+EMP"} <= set(space["events"][1])  # cells 97a and 97b on the grid
    assert space["entry"][1] == ["prior_close", "release_open"]
    assert mod.PNL_UNITS == "usd" and mod._AUGUR_MARKET == {"instrument": "GLD", "timeframe": "5m",
                                                            "session": "rth", "source": "alpaca_split_rth"}


def test_release_calendar_is_the_source_files():
    """The frozen lists = tools/data/fomc_dates.txt (tracked) and the shared checkout's bls_dates.txt (untracked: checked
    when present) on 2016-01 .. 2026-06-30, and = strategy 94's lists when MISC_EVENTCRUSH_1_0.py is in this tree."""
    mod = P.fresh_plugin()
    lo, hi = 20160101, 20260630
    fomc = set()
    with open(os.path.join(REPO, "tools", "data", "fomc_dates.txt")) as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                fomc.add(int(ln[:10].replace("-", "")))
    assert mod.EVENT_DAYS["FOMC"].tolist() == sorted(x for x in fomc if lo <= x <= hi)
    bls = os.path.join(SHARED, "tools", "data", "bls_dates.txt")
    if os.path.exists(bls):
        got = {"CPI": set(), "EMP": set()}
        with open(bls) as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    t, dd, _ = ln.split("|")
                    if t in got:
                        got[t].add(int(dd.replace("-", "")))
        for t in got:
            assert mod.EVENT_DAYS[t].tolist() == sorted(x for x in got[t] if lo <= x <= hi), t
    assert [len(mod.EVENT_DAYS[t]) for t in ("FOMC", "CPI", "EMP")] == [83, 125, 125]
    sib = os.path.join(REPO, "augur_strategies", "MISC_EVENTCRUSH_1_0.py")
    if os.path.exists(sib):
        spec = importlib.util.spec_from_file_location("misc_eventcrush_for_97", sib)
        s = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(s)
        for t in ("FOMC", "CPI", "EMP"):
            assert np.array_equal(s.EVENT_DAYS[t], mod.EVENT_DAYS[t]), t


def test_plugin_gate_lets_it_through():
    from augur_engine import plugin_gate as G
    with open(PLUGIN, "rb") as f:
        src = G.lf_bytes(f.read()).decode("utf-8")
    assert G.MARKER_RX.search(src).group(1) == "claude-review"
    assert G.lookahead_check(src) == []
    G.gate_plugin(PLUGIN)                                         # raises PluginGateError on a refusal


def test_synthetic_contract_arrays_never_touch_the_panel():
    """tests/test_strategy_contract.py hands every plugin a continuous 5m tape dated 2026-03 (inside the engine's
    lockbox). None of its days is an RTH session, so the plugin returns None BEFORE it opens the panel."""
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
    mod.PANEL_PATH = os.path.join(REPO, "no_such_dir", "gldmacro_panel_v1.npz")
    a = _rth_arrays([20190604, 20190605, 20190606, 20190607], [955] * 4)      # payrolls 2019-06-07
    from augur_engine import run_backtest
    assert run_backtest(mod, arrays=a, params={}, return_trades=True) is None
    assert mod._CACHE.get("panel", "missing") is None
    assert mod.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"],
                            events="nope", return_trades=True) is None


# ---------------------------------------------------------------------------------------------------- parity
def test_2019_trades_match_harness_97a_on_an_rth_clock(sealed, syn):
    mod, p = sealed
    from augur_engine import run_backtest
    r = run_backtest(mod, arrays=syn, params={}, return_trades=True)
    assert METRIC_KEYS <= set(r)
    idx = pd.DatetimeIndex(syn["index"]).tz_localize(None)
    got = {_ymd(idx[t[1]]): t for t in r["trades"] if idx[t[1]].year == 2019}
    H = _hunt("97a")
    H = H[(H.D >= 20190101) & (H.D <= 20191231)]
    assert sorted(got) == sorted(H.D.tolist()) and len(H) > 25
    row_of = {int(x): i for i, x in enumerate(p["dates"])}
    for h in H.itertuples():
        t = got[h.D]
        e, x = idx[t[0]], idx[t[1]]
        assert _ymd(e) == h.Dm1 and _ymd(x) == h.D                       # D-1 -> D, one night
        assert e.hour * 60 + e.minute == p["last_min"][row_of[h.Dm1]]     # D-1's last bar (15:25 on 2019-08-12)
        assert x.hour * 60 + x.minute == p["last_min"][row_of[h.D]]       # D's last bar
        assert t[3] == 1 and abs(t[2] - h.net) < 1e-9, h.D
    rows = {q["D"]: q for q in mod._trades(p, syn["index"], syn["open"], syn["close"])}
    for h in H.itertuples():
        q = rows[h.D]
        assert q["shares"] == h.shares and abs(q["px"] - h.px) < 1e-9, h.D
        assert abs(q["gross"] - h.gross) < 1e-9 and abs(q["cost"] - h.cost) < 1e-9, h.D
    marks = mod.mark_open_trades(r["trades"], syn["open"], syn["high"], syn["low"], syn["close"],
                                 index=syn["index"])
    assert marks == [[(t[0], 0.0)] for t in r["trades"]]             # held through ONE close, worth 0 there
    rel = {int(x) for t in ("FOMC", "CPI", "EMP") for x in mod.EVENT_DAYS[t]}
    assert all(_ymd(idx[t[1]]) in rel for t in r["trades"])          # never rolled off a release day


def test_2019_master_slice_matches_harness_97a_and_97b(sealed, master_2019):
    mod, p = sealed
    arr = master_2019
    from augur_engine import run_backtest
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    for cell, kw, tol in (("97a", {}, 1e-9), ("97b", {"events": "CPI+EMP", "entry": "release_open"}, 5.0)):
        r = run_backtest(mod, arrays=arr, params=dict(kw), return_trades=True)
        got = {_ymd(idx[t[1]]): t for t in r["trades"] if idx[t[1]].year == 2019}
        H = _hunt(cell)
        H = H[(H.D >= 20190101) & (H.D <= 20191231)]
        assert sorted(got) == sorted(H.D.tolist()) and len(H) > 15, cell
        for h in H.itertuples():
            t = got[h.D]
            assert _ymd(idx[t[0]]) == h.Dm1, (cell, h.D)              # the hunt's entry session (97b files D itself)
            assert abs(t[2] - h.net) < tol, (cell, h.D)               # 97b: the hunt rounded 5m prices to float32
        if cell == "97b":
            assert all((idx[t[0]].hour, idx[t[0]].minute) == (9, 30) for t in r["trades"])
            assert mod.mark_open_trades(r["trades"], arr["open"], arr["high"], arr["low"], arr["close"],
                                        index=arr["index"]) == [[]] * len(r["trades"])


# ---------------------------------------------------------------------------------------------------- slice edges
def test_slice_edges_never_close_a_trade_early_or_open_it_late(sealed, syn):
    """Payrolls 2019-06-07 (D-1 2019-06-06). A slice that ends one bar short of D's close, or starts at D's open, takes
    no trade for D; one that ends on D's last bar, or starts inside D-1, takes the same trade. The release-open trade
    needs D's 09:30 bar and D's last bar inside the slice."""
    mod, p = sealed
    idx = pd.DatetimeIndex(syn["index"]).tz_localize(None)
    day = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy()
    d1, d = np.flatnonzero(day == 20190606), np.flatnonzero(day == 20190607)
    x = int(d[-1])

    def trade_on(a, b, entry="prior_close"):
        rows = mod._trades(p, syn["index"][a:b], syn["open"][a:b], syn["close"][a:b], entry=entry)
        hit = [q for q in rows if q["D"] == 20190607]
        return [(q["e"] + a, q["x"] + a, q["net"]) for q in hit]

    full = trade_on(0, len(idx))
    assert len(full) == 1 and full[0][0] == int(d1[-1]) and full[0][1] == x
    assert trade_on(0, x + 1) == full                              # through D's last bar
    assert trade_on(0, x) == []                                    # one bar short: never closed early
    assert trade_on(int(d1[0]) + 10, len(idx)) == full             # starts inside D-1: the entry bar is still there
    assert trade_on(int(d[0]), len(idx)) == []                     # starts at D's open: D-1's close is gone
    ro = trade_on(0, len(idx), "release_open")
    assert len(ro) == 1 and ro[0][0] == int(d[0]) and ro[0][1] == x
    assert trade_on(int(d[0]) + 1, len(idx), "release_open") == []  # no 09:30 bar
    assert trade_on(0, x, "release_open") == []                    # D cut short


# ---------------------------------------------------------------------------------------------------- look-ahead
def _scramble(p, arr, r, entry, seed):
    """Copies of the panel and the bars with everything known only after trade r's entry print replaced at random:
    the official and raw closes of D and of every later session, and every bar price after the entry print
    (prior_close: every bar after D-1's last bar; release_open: the 09:30 bar's high / low / close and every later
    bar - its open IS the print). Factors 0.5 .. 0.9: every scrambled price moves down by 10 pct or more."""
    rng = np.random.default_rng(seed)
    q = {k: np.array(p[k]) for k in P.PANEL_KEYS}
    i = r["row"]
    for k in ("close", "raw"):
        q[k][i:] = q[k][i:] * rng.uniform(0.5, 0.9, len(q[k]) - i)
    a = dict(arr)
    e = r["e"]
    for k in ("open", "high", "low", "close"):
        v = np.array(arr[k], float)
        first = e + 1 if (entry == "prior_close" or k == "open") else e
        v[first:] = v[first:] * rng.uniform(0.5, 0.9, len(v) - first)
        a[k] = v
    return q, a


def _check(mod, p, arr, prm, base, r, seed):
    """(entry side of every trade entered by r's entry bar unchanged and every trade closed by then byte-identical,
    trade r's net moved) after the scramble."""
    q, a = _scramble(p, arr, r, prm["entry"], seed)
    got = mod._trades(mod._derive(q), a["index"], a["open"], a["close"], **prm)
    want = [tuple(b[k] for k in ENTRY_KEYS) for b in base if b["e"] <= r["e"]]
    have = [tuple(g[k] for k in ENTRY_KEYS) for g in got if g["e"] <= r["e"]]
    closed = ([b["net"] for b in base if b["x"] <= r["e"]] == [g["net"] for g in got if g["x"] <= r["e"]])
    same = (g for g in got if g["e"] == r["e"] and g["x"] == r["x"])
    moved = next((g["net"] != r["net"] for g in same), False)
    return have == want and closed, moved


@pytest.mark.parametrize("entry", ["prior_close", "release_open"])
def test_nothing_after_the_entry_print_moves_a_trade(sealed, syn, entry):
    mod, p = sealed
    prm = dict(_defaults(mod), entry=entry)
    base = mod._trades(p, syn["index"], syn["open"], syn["close"], **prm)
    assert len(base) > 40
    picks = base[3::7]
    results = [_check(mod, p, syn, prm, base, r, seed=9700 + k) for k, r in enumerate(picks)]
    assert all(ok for ok, _ in results), [r["D"] for r, (ok, _) in zip(picks, results) if not ok]
    assert all(mv for _, mv in results)                           # the scramble really reached each trade's P&L


def test_the_lookahead_check_catches_broken_variants(sealed, syn):
    """The check above has teeth: shares from D's raw close, a release day skipped when D closes down, and a release-
    open trade sized on the 09:35 bar's open each FAIL it."""
    _, p = sealed
    m1 = P.fresh_plugin()
    m1._prior_close_terms = lambda pp, i: (float(pp["close"][i - 1]), float(pp["raw"][i]))
    m2 = P.fresh_plugin()
    rows2 = m2._event_rows
    m2._event_rows = lambda pp, ev: np.array([i for i in rows2(pp, ev) if pp["close"][i] >= pp["close"][i - 1]],
                                             dtype=np.int64)
    m3 = P.fresh_plugin()
    m3._open_terms = lambda op, e: float(op[e + 1])
    for mod, entry in ((m1, "prior_close"), (m2, "prior_close"), (m3, "release_open")):
        prm = dict(_defaults(mod), entry=entry)
        base = mod._trades(p, syn["index"], syn["open"], syn["close"], **prm)
        assert len(base) > 20, entry
        caught = [not _check(mod, p, syn, prm, base, r, seed=9750 + k)[0] for k, r in enumerate(base[3::7])]
        assert all(caught), (entry, caught)
