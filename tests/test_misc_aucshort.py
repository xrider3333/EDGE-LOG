"""MISC_AUCSHORT_1_0 (opus hunt 135a / 151 part A, AUCTION-AM short): defaults = the $300k seat and a 3-point grid, the
frozen auction calendar = the source JSON under the stated filter and is point-in-time (every row announced on or
before the session before it), the plugin gate lets it through, the contract's synthetic 24-hour tape and any non-RTH
tape never touch the panel, no panel -> no trades, and - when the pinned panel, the hunt files and the TLT 5m master
are on this machine - the 2019 trades equal the harness's trades.csv (fractional sizing, to 1e-9) on the real master,
slice edges never open a trade late or close it early, and nothing known only after the entry print moves a trade,
with four broken variants caught.
Everything that reads prices runs on the panel CUT AT 2025-06-30 (tools/misc_aucshort_parity.load_plugin_sealed), on
synthetic bars, and on master bars loaded only through 2019."""
import datetime as dt
import os
import sqlite3
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "augur_strategies", "MISC_AUCSHORT_1_0.py")
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S135/"
sys.path.insert(0, os.path.join(REPO, "tools"))

import misc_aucshort_panel as B  # noqa: E402
import misc_aucshort_parity as P  # noqa: E402

PINNED = ("notional", "cents_share", "fee_bps")
METRIC_KEYS = {"total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown", "avg_pnl", "wins", "losses"}
ENTRY_KEYS = ("e", "x", "D", "fund", "row", "px", "shares", "p_in")
PRICE_KEYS = ("TLT_o935", "TLT_o1255", "TLT_prevraw", "IEF_o935", "IEF_o1255", "IEF_prevraw")


def _defaults(mod):
    return {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}


def _rth_arrays(days, nbars, seed=135, first_min=570):
    """A TLT-like 5m clock on the given yyyymmdd sessions: `nbars` bars a session from `first_min`, random-walk
    prices."""
    rng = np.random.default_rng(seed)
    days = np.asarray(days, np.int64)
    nb = np.asarray(nbars, np.int64)
    base = pd.to_datetime(pd.Series(days.astype(str)), format="%Y%m%d").to_numpy()
    off = (np.concatenate([np.arange(k) for k in nb]) * 5 + first_min).astype("timedelta64[m]")
    idx = pd.DatetimeIndex(np.repeat(base, nb) + off).tz_localize("US/Eastern")
    n = len(idx)
    close = 120 + rng.normal(0, 0.05, n).cumsum()
    openp = close + rng.normal(0, 0.02, n)
    return {"open": openp, "high": np.maximum(openp, close) + 0.02, "low": np.minimum(openp, close) - 0.02,
            "close": close, "volume": np.full(n, 1000.0), "day_id": np.repeat(np.arange(len(days)), nb).astype("int64"),
            "index": idx, "meta": {"name": "SYN", "roll_mode": "none"}}


def _hunt():
    path = HUNT + "trades.csv"
    if not os.path.exists(path):
        pytest.skip("hunt trades not on this machine")
    H = pd.read_csv(path)
    H["D"] = pd.to_datetime(H.date).dt.strftime("%Y%m%d").astype("int64")
    return H[H.D <= 20250630]


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
    """A synthetic RTH clock on every 2018-2019 panel session: 78 bars, 42 on the early-close days."""
    _, p = sealed
    k = (p["dates"] >= 20180101) & (p["dates"] <= 20191231)
    return _rth_arrays(p["dates"][k], np.where(p["calskip"][k] == 1, 42, 78))


@pytest.fixture(scope="module")
def master_2019():
    """The TLT 5m RTH alpaca_split_rth master, 2019 only. A worktree has no registry or uploads of its own, so the row
    is read (read-only) from the shared checkout's registry and the CSV from its augur_uploads."""
    db = os.path.join(SHARED, "optimizer_history.db")
    if not os.path.exists(db):
        pytest.skip("master registry not on this machine")
    row = None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
        try:
            row = con.execute("SELECT id, filename, source, session, instrument, timeframe FROM csv_files "
                              "WHERE is_master=1 AND instrument='TLT' AND timeframe='5m' AND lower(session)='rth' "
                              "AND source='alpaca_split_rth'").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        row = None
    path = os.path.join(SHARED, "augur_uploads", row[1]) if row else None
    if path is None or not os.path.exists(path):
        pytest.skip("TLT 5m master not on this machine")
    from augur_engine.data import load_master_arrays
    m = dict(zip(("id", "filename", "source", "session", "instrument", "timeframe"), row))
    arr = load_master_arrays(dict(m, filename=path), date_from="2019-01-02", date_to="2019-12-31")
    arr["meta"] = m
    assert pd.DatetimeIndex(arr["index"]).max() < pd.Timestamp("2020-01-01", tz="US/Eastern")
    return arr


# ---------------------------------------------------------------------------------------------------- contract, ranges
def test_defaults_are_the_300k_seat_and_a_three_point_grid():
    mod = P.fresh_plugin()
    assert _defaults(mod) == {"notional": 300000, "cents_share": 0.5, "fee_bps": 0.3, "funds": "both"}
    for k, v in mod.DEFAULT_PARAMS.items():
        if "min" in v:
            assert v["min"] <= v["default"] <= v["max"], k
            assert v["hard_min"] <= v["min"] and v["max"] <= v["hard_max"], k
        if k in PINNED:
            assert v["min"] == v["max"] == v["default"] == v["hard_min"] == v["hard_max"], k
    assert mod.PARAM_GRID_PRESETS["Short  (the hunt cell 135a)"] == {"funds": ["both"]}
    from augur_engine.auto import _auto_space_from_params
    space = _auto_space_from_params(mod.DEFAULT_PARAMS)
    size = 1
    for spec in space.values():
        size *= len(spec[1]) if spec[0] == "cat" else int(round((spec[2] - spec[1]) / spec[3])) + 1
    assert size == 3
    assert space["funds"][1] == ["both", "IEF_only", "TLT_only"]
    assert mod.PNL_UNITS == "usd" and mod._AUGUR_MARKET == {"instrument": "TLT", "timeframe": "5m",
                                                            "session": "rth", "source": "alpaca_split_rth"}


def test_frozen_calendar_is_point_in_time():
    """In-repo, no data file: every frozen row was announced on or before the NYSE session before its auction date
    (the house exchange calendar), the two same-day-announced rows are not in the table, and the fund map holds."""
    mod = P.fresh_plugin()
    assert [len(mod.AUCTIONS[f]) for f in ("IEF", "TLT")] == [395, 207]
    for f in ("IEF", "TLT"):
        for a, n, ff, t in mod.AUCTIONS[f]:
            ad = dt.date(a // 10000, a // 100 % 100, a % 100)
            prior = int(B.prior_session(ad).strftime("%Y%m%d"))
            assert n <= prior < a, (f, a, n)
            assert B.nyse_session(ad), (f, a)
            assert ff == f and t in ((5, 7, 10) if f == "IEF" else (20, 30)), (f, a, t)
        days = [r[0] for r in mod.AUCTIONS[f]]
        assert days == sorted(days) and 20160101 <= days[0] and days[-1] <= 20261008
    assert 20190621 not in {r[0] for r in mod.AUCTIONS["IEF"]}
    assert 20211202 not in {r[0] for r in mod.AUCTIONS["TLT"]}


def test_frozen_calendar_is_the_source_json():
    if not os.path.exists(B.AUCTIONS):
        pytest.skip("auction JSON not on this machine")
    mod = P.fresh_plugin()
    kept, late = B.auction_calendar()
    assert [(a, n, f, int(t.split("-")[0])) for a, n, f, t in kept] == sorted(
        r for f in ("IEF", "TLT") for r in mod.AUCTIONS[f])
    assert [(r[0], r[2]) for r in late] == [(20190621, "IEF"), (20211202, "TLT")]
    assert all(r[1] >= r[0] for r in late)                   # the harness's '<' rule dropped the same two rows


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
    rng = np.random.default_rng(7)
    n = 780
    close = 15000 + rng.normal(0, 1, n).cumsum()
    idx = pd.date_range("2026-03-02 09:30", periods=n, freq="5min", tz="US/Eastern")
    mod = P.fresh_plugin()
    r = mod.run_backtest(close, close + 1, close - 1, close, np.full(n, 1000.0),
                         np.repeat(np.arange(10), 78).astype("int64"), idx, return_trades=True)
    assert r is None
    assert "panel" not in mod._CACHE


def test_non_rth_bars_return_none():
    """An extended-hours tape on real 2019 auction days (04:00 .. 19:55): no session is RTH, so no trade and the panel
    is never opened."""
    a = _rth_arrays([20190910, 20190911, 20190912], [192] * 3, first_min=240)
    mod = P.fresh_plugin()
    from augur_engine import run_backtest
    assert run_backtest(mod, arrays=a, params={}, return_trades=True) is None
    assert "panel" not in mod._CACHE


def test_no_panel_no_trades():
    mod = P.fresh_plugin()
    mod.PANEL_PATH = os.path.join(REPO, "no_such_dir", "aucshort_panel_v1.npz")
    a = _rth_arrays([20190910, 20190911, 20190912, 20190913], [78] * 4)      # 10-Year 09-11, 30-Year 09-12
    from augur_engine import run_backtest
    assert run_backtest(mod, arrays=a, params={}, return_trades=True) is None
    assert mod._CACHE.get("panel", "missing") is None
    assert mod.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"],
                            funds="nope", return_trades=True) is None


# ---------------------------------------------------------------------------------------------------- parity
def test_2019_on_an_rth_clock(sealed, syn):
    """Synthetic TLT bars, real (sealed) panel: the 2019 trade days are the harness's, IEF trades (panel prices) equal
    trades.csv under the harness's fractional sizing, every trade sits on its day's 09:35 and 12:55 bars with side -1,
    floor(N / prior raw close) shares, and no marks."""
    mod, p = sealed
    from augur_engine import run_backtest
    r = run_backtest(mod, arrays=syn, params={}, return_trades=True)
    assert METRIC_KEYS <= set(r)
    idx = pd.DatetimeIndex(syn["index"]).tz_localize(None)
    for t in r["trades"]:
        e, x = idx[t[0]], idx[t[1]]
        assert (e.hour, e.minute) == (9, 35) and (x.hour, x.minute) == (12, 55) and e.date() == x.date()
        assert t[3] == -1
    H = _hunt()
    H = H[(H.D >= 20190101) & (H.D <= 20191231)]
    rows = [q for q in mod._trades(p, syn["index"], syn["open"]) if q["D"] >= 20190101]
    assert sorted((q["fund"], q["D"]) for q in rows) == sorted(zip(H.fund, H.D)) and len(H) > 45
    for q in rows:
        assert q["shares"] == np.floor(300000 / q["px"]) and q["px"] == p[q["fund"] + "_prevraw"][q["row"]]
        assert abs(q["gross"] - q["shares"] * (q["p_in"] - q["p_out"])) < 1e-9
        assert abs(q["cost"] - 2 * (0.005 + 0.3e-4 * q["px"]) * q["shares"]) < 1e-9
        assert q["announced"] <= p["dates"][q["row"] - 1] < q["D"]          # point-in-time: announced by D-1's close
    frac = {(q["fund"], q["D"]): q for q in mod._trades(p, syn["index"], syn["open"], notional=100000, fractional=True)}
    ief = H[H.fund == "IEF"]
    assert len(ief) > 30
    for h in ief.itertuples():
        q = frac[("IEF", h.D)]
        assert abs(q["gross"] - h.gross) < 1e-9 and abs(q["cost"] - h.cost) < 1e-9 and abs(q["net"] - h.net) < 1e-9
    assert mod.mark_open_trades(r["trades"], syn["open"], syn["high"], syn["low"], syn["close"],
                                index=syn["index"]) == [[]] * len(r["trades"])
    for f, want in (("IEF_only", "IEF"), ("TLT_only", "TLT")):
        assert {q["fund"] for q in mod._trades(p, syn["index"], syn["open"], funds=f)} == {want}


def test_2019_master_slice_matches_the_harness(sealed, master_2019):
    mod, p = sealed
    arr = master_2019
    from augur_engine import run_backtest
    H = _hunt()
    H = H[(H.D >= 20190101) & (H.D <= 20191231)]
    frac = mod._trades(p, arr["index"], arr["open"], notional=100000, fractional=True)
    assert sorted((q["fund"], q["D"]) for q in frac) == sorted(zip(H.fund, H.D))
    want = {(h.fund, h.D): h for h in H.itertuples()}
    for q in frac:
        h = want[(q["fund"], q["D"])]
        assert abs(q["gross"] - h.gross) < 1e-9 and abs(q["cost"] - h.cost) < 1e-9 and abs(q["net"] - h.net) < 1e-9
    r = run_backtest(mod, arrays=arr, params={"notional": 100000}, return_trades=True)
    own = mod._trades(p, arr["index"], arr["open"], notional=100000)
    assert [(t[0], t[1], t[2]) for t in r["trades"]] == [(q["e"], q["x"], q["net"]) for q in
                                                         sorted(own, key=lambda z: (z["x"], z["e"]))]
    for q in own:                                           # whole shares on the prior raw close: a small sizing gap
        h = want[(q["fund"], q["D"])]
        assert abs(q["net"] - h.net) <= 0.05 * abs(h.gross) + 1.0, (q["fund"], q["D"])


def test_two_funds_one_day_are_two_trades_and_a_double_auction_is_one(sealed, syn):
    """No such day exists in the source through 2026-10; the rule is checked on a tampered calendar."""
    _, p = sealed
    mod = P.fresh_plugin()
    day = 20190911                                                   # a real IEF (10-Year) day
    assert day in {r[0] for r in mod.AUCTIONS["IEF"]} and day not in {r[0] for r in mod.AUCTIONS["TLT"]}
    mod.AUCTIONS = {"IEF": tuple(sorted(mod.AUCTIONS["IEF"] + ((day, 20190905, "IEF", 7),))),
                    "TLT": tuple(sorted(mod.AUCTIONS["TLT"] + ((day, 20190905, "TLT", 30),)))}
    q = mod._derive({k: p[k] for k in mod.PANEL_KEYS})
    hit = [r for r in mod._trades(q, syn["index"], syn["open"]) if r["D"] == day]
    assert [r["fund"] for r in hit] == ["IEF", "TLT"]
    assert hit[0]["e"] == hit[1]["e"] and hit[0]["x"] == hit[1]["x"]


# ---------------------------------------------------------------------------------------------------- slice edges
def test_slice_edges_never_open_a_trade_late_or_close_it_early(sealed, syn):
    """10-Year 2019-09-11 (IEF) and 30-Year 2019-09-12 (TLT). A slice needs the day's 09:35 bar, 12:55 bar and 15:55
    last bar: one that starts at the 09:40 bar, or ends before the 15:55 bar, takes no trade for that day."""
    mod, p = sealed
    idx = pd.DatetimeIndex(syn["index"]).tz_localize(None)
    day = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy()
    for D in (20190911, 20190912):
        d = np.flatnonzero(day == D)
        s, last = int(d[0]), int(d[-1])

        def trade_on(a, b):
            rows = mod._trades(p, syn["index"][a:b], syn["open"][a:b])
            return [(q["e"] + a, q["x"] + a, q["net"]) for q in rows if q["D"] == D]

        full = trade_on(0, len(idx))
        assert len(full) == 1 and full[0][0] == s + 1 and full[0][1] == s + 41
        assert trade_on(0, last + 1) == full                       # through the day's 15:55 bar
        assert trade_on(0, last) == []                             # one bar short of a whole session
        assert trade_on(0, s + 42) == []                           # ends right after the 12:55 bar: not whole
        assert trade_on(0, s + 41) == []                           # no 12:55 bar: never closed early
        assert trade_on(s + 1, len(idx)) == full                   # starts at the 09:35 bar itself
        assert trade_on(s + 2, len(idx)) == []                     # starts at 09:40: never opened late


# ---------------------------------------------------------------------------------------------------- look-ahead
def _scramble(p, arr, r, seed):
    """Copies of the panel and the bars with everything known only after trade r's 09:35 entry print replaced at
    random: both funds' 12:55 opens of that day and of every later session, their 09:35 opens of every later session,
    the prior-raw-close column from the next session on (= that day's raw close and later), every bar open after the
    entry bar and the entry bar's own high / low / close and everything after. Factors 1.1 .. 1.5: every scrambled
    price moves UP by 10 pct or more (against the short)."""
    rng = np.random.default_rng(seed)
    q = {k: np.array(p[k]) for k in P.fresh_plugin().PANEL_KEYS}
    i = r["row"]
    for k in PRICE_KEYS:
        first = i if k.endswith("o1255") else i + 1
        q[k][first:] = q[k][first:] * rng.uniform(1.1, 1.5, len(q[k]) - first)
    a = dict(arr)
    e = r["e"]
    for k in ("open", "high", "low", "close"):
        v = np.array(arr[k], float)
        first = e + 1 if k == "open" else e
        v[first:] = v[first:] * rng.uniform(1.1, 1.5, len(v) - first)
        a[k] = v
    return q, a


def _check(mod, p, arr, prm, base, r, seed):
    """(entry side of every trade entered by r's entry bar unchanged and every trade closed by then byte-identical,
    trade r's net moved) after the scramble."""
    q, a = _scramble(p, arr, r, seed)
    got = mod._trades(mod._derive(q), a["index"], a["open"], **prm)
    want = [tuple(b[k] for k in ENTRY_KEYS) for b in base if b["e"] <= r["e"]]
    have = [tuple(g[k] for k in ENTRY_KEYS) for g in got if g["e"] <= r["e"]]
    closed = ([b["net"] for b in base if b["x"] <= r["e"]] == [g["net"] for g in got if g["x"] <= r["e"]])
    same = (g for g in got if g["e"] == r["e"] and g["x"] == r["x"] and g["fund"] == r["fund"])
    moved = next((g["net"] != r["net"] for g in same), False)
    return have == want and closed, moved


def _late_rows(p, rows):
    """Trades whose auction was NOT announced by the close of the session before it (the point-in-time check)."""
    return [(q["fund"], q["D"]) for q in rows if not q["announced"] <= int(p["dates"][q["row"] - 1])]


@pytest.mark.parametrize("funds", ["both", "IEF_only", "TLT_only"])
def test_nothing_after_the_entry_print_moves_a_trade(sealed, syn, funds):
    mod, p = sealed
    prm = dict(_defaults(mod), funds=funds)
    base = mod._trades(p, syn["index"], syn["open"], **prm)
    assert len(base) > 20
    assert _late_rows(p, base) == []
    picks = base[3::7] if funds == "both" else base[1::4]
    results = [_check(mod, p, syn, prm, base, r, seed=13500 + k) for k, r in enumerate(picks)]
    assert all(ok for ok, _ in results), [r["D"] for r, (ok, _) in zip(picks, results) if not ok]
    assert all(mv for _, mv in results)                           # the scramble really reached each trade's P&L


def test_the_checks_catch_broken_variants(sealed, syn):
    """The checks above have teeth. Each of these FAILS them: (1) shares from the 12:55 price; (2) a day skipped when
    the morning went against the short; (3) a TLT entry read from the 09:40 bar's open; (4) a calendar that trades
    auctions announced on the auction day itself (caught by the point-in-time check, and refused at run time by the
    unbroken file)."""
    _, p = sealed
    m1 = P.fresh_plugin()
    m1._sizing_px = lambda pp, f, i: float(pp[f + "_o1255"][i])
    m2 = P.fresh_plugin()
    rows2 = m2._auction_rows
    m2._auction_rows = lambda pp, f: [z for z in rows2(dict(pp, memo={}), f)
                                      if not pp[f + "_o1255"][z[0]] > pp[f + "_o935"][z[0]]]
    m3 = P.fresh_plugin()
    m3._entry_px = lambda op, e: float(op[e + 1])
    for mod, funds in ((m1, "both"), (m2, "both"), (m3, "TLT_only")):
        prm = dict(_defaults(mod), funds=funds)
        base = mod._trades(p, syn["index"], syn["open"], **prm)
        assert len(base) > 15, funds
        caught = [not _check(mod, p, syn, prm, base, r, seed=13550 + k)[0] for k, r in enumerate(base[1::4])]
        assert all(caught), (funds, caught)
    # (4) the two rows Treasury's file dates as announced on the auction day, put back into the calendar
    late = {"IEF": (20190621, 20190621, "IEF", 10), "TLT": (20181213, 20181213, "TLT", 30)}
    good = P.fresh_plugin()
    good.AUCTIONS = {"IEF": tuple(sorted(good.AUCTIONS["IEF"] + (late["IEF"],))),
                     "TLT": tuple(sorted(r for r in good.AUCTIONS["TLT"] if r[0] != 20181213) + [late["TLT"]])}
    good.AUCTIONS["TLT"] = tuple(sorted(good.AUCTIONS["TLT"]))
    rows = good._trades(good._derive({k: p[k] for k in good.PANEL_KEYS}), syn["index"], syn["open"])
    assert not {20190621, 20181213} & {q["D"] for q in rows}      # the run-time guard refuses them
    m4 = P.fresh_plugin()
    m4.AUCTIONS = good.AUCTIONS
    m4._knowable = lambda pp, i, announced: True
    rows = m4._trades(m4._derive({k: p[k] for k in m4.PANEL_KEYS}), syn["index"], syn["open"])
    assert sorted(_late_rows(p, rows)) == [("IEF", 20190621), ("TLT", 20181213)]
