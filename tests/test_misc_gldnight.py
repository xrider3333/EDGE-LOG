"""MISC_GLDNIGHT_1_0 (opus hunt 158 / 160, GLD-NIGHT, cell 160a): defaults = the hunt cell and a 3-point grid, the plugin
gate lets it through, the contract's synthetic 24-hour tape and an extended-hours tape never touch the panel, no panel
-> no trades, a fully synthetic panel dated 2026 trades by hand arithmetic, and - when the pinned panel, the daily file
and the GLD 5m master are on this machine - the 2019 trades equal the harness formula (fractional replica x the
whole-share scale) on an RTH clock and on the real master, slice edges never close a trade early or open it late, and
nothing known only after the entry print moves a trade, with three broken variants caught.
Everything that reads real prices runs on the panel CUT AT 2025-06-30 (tools/misc_gldnight_parity.load_plugin_sealed),
on the daily file read to 2025-06-30 and on master bars loaded only through 2019. The one test dated after 2025 uses
made-up prices."""
import os
import sqlite3
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "augur_strategies", "MISC_GLDNIGHT_1_0.py")
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, os.path.join(REPO, "tools"))

import misc_gldnight_parity as P  # noqa: E402

PINNED = ("notional", "cents_share", "fee_bps")
METRIC_KEYS = {"total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown", "avg_pnl", "wins", "losses"}
ENTRY_KEYS = ("e", "x", "D", "entry_day", "row", "px", "shares", "p_in", "gap")
MODES = ("weeknights", "every_night", "weekend_only")


def _defaults(mod):
    return {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}


def _rth_arrays(days, last_min, seed=160, first_min=570):
    """A GLD-like 5m clock on the given yyyymmdd sessions: bars from 09:30 to each session's own last bar (half days
    and the 2019-08-12 hole included), random-walk prices (the plugin never reads them)."""
    rng = np.random.default_rng(seed)
    days = np.asarray(days, np.int64)
    nb = (np.asarray(last_min, np.int64) - first_min) // 5 + 1
    base = pd.to_datetime(pd.Series(days.astype(str)), format="%Y%m%d").to_numpy()
    off = (np.concatenate([np.arange(k) for k in nb]) * 5 + first_min).astype("timedelta64[m]")
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


def _ymd(ts):
    return int(ts.strftime("%Y%m%d"))


def _replica_2019(nights="weeknights"):
    """The harness formula (fractional shares) on the daily file read to 2025-06-30, exit day in 2019."""
    if not os.path.exists(P.RAW):
        pytest.skip("GLD daily file not on this machine")
    r = P.read_daily_sealed()
    R = P.replica(r[r.index >= pd.Timestamp("2016-01-01")], nights)
    R = R[(R.D >= pd.Timestamp("2019-01-01")) & (R.D <= pd.Timestamp("2019-12-31"))].copy()
    R["Dk"] = R.D.dt.strftime("%Y%m%d").astype("int64")
    R["Dm1k"] = R.Dm1.dt.strftime("%Y%m%d").astype("int64")
    return R


@pytest.fixture(scope="module")
def sealed():
    mod, p = P.load_plugin_sealed()
    if p is None:
        pytest.skip("pinned panel not on this machine")
    assert int(p["dates"].max()) <= 20250630
    return mod, p


@pytest.fixture(scope="module")
def syn(sealed):
    """The RTH clock of every 2018-2019 panel session (2018 gives the first 2019 night its D-1)."""
    _, p = sealed
    return _rth_arrays(*_years(p, 2018, 2019))


@pytest.fixture(scope="module")
def master_2019():
    """The GLD 5m RTH alpaca_split_rth master, 2018-12-03 .. 2019-12-31 only. A worktree has no registry or uploads of
    its own, so the row is read (read-only) from the shared checkout's registry and the CSV from its augur_uploads."""
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


def _toy_panel(mod):
    """A made-up panel dated 2026 (inside the lockbox year, so NOTHING real is read): Mon 03-02 .. Fri 03-06, Mon
    03-09, then Wed 03-11 (a pretend mid-week holiday on 03-10); 03-04 is a pretend half day."""
    dates = np.array([20260302, 20260303, 20260304, 20260305, 20260306, 20260309, 20260311], np.int64)
    close = np.array([200.0, 250.0, 300.0, 333.0, 400.0, 500.0, 100.0])
    openp = np.array([199.0, 201.0, 255.0, 297.0, 340.0, 396.0, 505.0])
    gap = np.array([0, 1, 1, 1, 1, 3, 2], np.int64)
    last = np.array([955, 955, 775, 955, 955, 955, 955], np.int64)
    return mod._derive({"dates": dates, "open": openp, "close": close, "raw": close.copy(),
                        "first_min": np.full(7, 570, np.int64), "last_min": last, "gap": gap})


# ---------------------------------------------------------------------------------------------------- contract, ranges
def test_defaults_are_cell_160a():
    mod = P.fresh_plugin()
    d = _defaults(mod)
    assert d == {"notional": 100000, "cents_share": 0.5, "fee_bps": 0.3, "nights": "weeknights"}
    for k, v in mod.DEFAULT_PARAMS.items():                     # every default sits inside its range and hard fence
        if "min" in v:
            assert v["min"] <= v["default"] <= v["max"], k
            assert v["hard_min"] <= v["min"] and v["max"] <= v["hard_max"], k
        if k in PINNED:
            assert v["min"] == v["max"] == v["default"] == v["hard_min"] == v["hard_max"], k
    assert mod.PARAM_GRID_PRESETS["Short  (the hunt cell 160a)"] == {"nights": ["weeknights"]}
    from augur_engine.auto import _auto_space_from_params
    space = _auto_space_from_params(mod.DEFAULT_PARAMS)
    size = 1
    for spec in space.values():
        size *= len(spec[1]) if spec[0] == "cat" else int(round((spec[2] - spec[1]) / spec[3])) + 1
    assert size == 3                                             # the whole honest grid: which nights
    assert space["nights"][1] == list(MODES)
    assert mod.PNL_UNITS == "usd" and mod._AUGUR_MARKET == {"instrument": "GLD", "timeframe": "5m",
                                                            "session": "rth", "source": "alpaca_split_rth"}
    assert "_PINNED" not in os.path.basename(PLUGIN) and not hasattr(mod, "_AUGUR_PARENT")


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


def test_non_rth_bars_return_none():
    """An extended-hours feed (04:00 .. 19:55 ET on the toy panel's own dates): no session is RTH, so no trade and
    the panel is never opened - even though every date and every 09:30 / 15:55 bar is there."""
    mod = P.fresh_plugin()
    a = _rth_arrays([20260302, 20260303, 20260304, 20260305], [1195] * 4, first_min=240)
    r = mod.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True)
    assert r is None and "panel" not in mod._CACHE
    mod._CACHE["panel"] = _toy_panel(mod)                         # and with a panel in hand: still nothing
    assert mod._trades(mod._CACHE["panel"], a["index"], a["open"], a["close"]) == []
    assert mod.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True) is None


def test_no_panel_no_trades():
    mod = P.fresh_plugin()
    mod.PANEL_PATH = os.path.join(REPO, "no_such_dir", "gldnight_panel_v1.npz")
    a = _rth_arrays([20190604, 20190605, 20190606, 20190607], [955] * 4)
    from augur_engine import run_backtest
    assert run_backtest(mod, arrays=a, params={}, return_trades=True) is None
    assert mod._CACHE.get("panel", "missing") is None
    assert mod.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"],
                            nights="nope", return_trades=True) is None


def test_a_wrong_panel_file_is_refused(tmp_path):
    mod = P.fresh_plugin()
    bad = tmp_path / "gldnight_panel_v1.npz"
    np.savez(str(bad), dates=np.array([20260302], dtype="int64"))
    mod.PANEL_PATH = str(bad)
    a = _rth_arrays([20190604, 20190605], [955] * 2)
    with pytest.raises(RuntimeError, match="not the pinned build"):
        mod.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"])


def test_toy_panel_hand_arithmetic_and_night_modes():
    """Made-up prices dated 2026. Weeknights = the four 1-day gaps; weekend_only = the Fri -> Mon night; every_night
    adds the 2-day gap. Shares, gross, cost and net by hand; the half day's entry bar is its 12:55 bar."""
    mod = P.fresh_plugin()
    p = _toy_panel(mod)
    a = _rth_arrays(p["dates"], p["last_min"])
    idx = pd.DatetimeIndex(a["index"]).tz_localize(None)
    got = {m: mod._trades(p, a["index"], a["open"], a["close"], nights=m) for m in MODES}
    assert [q["D"] for q in got["weeknights"]] == [20260303, 20260304, 20260305, 20260306]
    assert [q["D"] for q in got["weekend_only"]] == [20260309]
    assert [q["D"] for q in got["every_night"]] == [20260303, 20260304, 20260305, 20260306, 20260309, 20260311]
    q = got["weeknights"][2]                                      # 03-04 (half day, close 300) -> 03-05 open 297
    assert q["shares"] == 333.0 and q["px"] == 300.0 and q["p_in"] == 300.0 and q["p_out"] == 297.0
    assert abs(q["gross"] - 333 * (297.0 - 300.0)) < 1e-9
    assert abs(q["cost"] - 2 * (0.005 * 333 + 0.3e-4 * 300.0 * 333)) < 1e-9
    assert abs(q["net"] - (-999.0 - 9.324)) < 1e-9
    assert (idx[q["e"]].hour, idx[q["e"]].minute) == (12, 55) and _ymd(idx[q["e"]]) == 20260304
    assert (idx[q["x"]].hour, idx[q["x"]].minute) == (9, 30) and _ymd(idx[q["x"]]) == 20260305
    q = got["weeknights"][3]                                      # close 333 -> floor(100000 / 333) = 300 shares
    assert q["shares"] == 300.0 and abs(q["gross"] - 300 * (340.0 - 333.0)) < 1e-9
    mod._CACHE["panel"] = p
    r = mod.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True)
    assert METRIC_KEYS <= set(r) and r["num_trades"] == 4
    assert [(t[0], t[1], t[2]) for t in r["trades"]] == [(q["e"], q["x"], q["net"]) for q in got["weeknights"]]
    assert all(t[3] == 1 for t in r["trades"])
    marks = mod.mark_open_trades(r["trades"], a["open"], a["high"], a["low"], a["close"], index=a["index"])
    assert marks == [[(t[0], 0.0)] for t in r["trades"]]          # held through ONE close, worth 0 there
    # the bars are the clock only: other bar prices, same trades
    b = _rth_arrays(p["dates"], p["last_min"], seed=5)
    assert mod._trades(p, b["index"], b["open"], b["close"]) == got["weeknights"]


# ---------------------------------------------------------------------------------------------------- parity
def _structure_ok(mod, p, arr, rows):
    """Every trade enters on D-1's last bar (the panel's last_min), exits on D's 09:30 bar, sells at the panel's open
    of D, buys at the panel's close of D-1 and holds floor(N / raw close of D-1) shares."""
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    for q in rows:
        i = q["row"]
        e, x = idx[q["e"]], idx[q["x"]]
        if not (_ymd(e) == int(p["dates"][i - 1]) == q["entry_day"] and _ymd(x) == int(p["dates"][i]) == q["D"]):
            return False
        if e.hour * 60 + e.minute != int(p["last_min"][i - 1]) or x.hour * 60 + x.minute != 570:
            return False
        if q["p_in"] != p["close"][i - 1] or q["p_out"] != p["open"][i]:
            return False
        if q["shares"] != np.floor(100000.0 / p["raw"][i - 1]) or q["px"] != p["raw"][i - 1]:
            return False
    return len(rows) > 0


def test_2019_trades_match_the_harness_formula_on_an_rth_clock(sealed, syn):
    mod, p = sealed
    from augur_engine import run_backtest
    r = run_backtest(mod, arrays=syn, params={}, return_trades=True)
    assert METRIC_KEYS <= set(r)
    idx = pd.DatetimeIndex(syn["index"]).tz_localize(None)
    got = {_ymd(idx[t[1]]): t for t in r["trades"] if idx[t[1]].year == 2019}
    H = _replica_2019()
    assert sorted(got) == sorted(H.Dk.tolist()) and len(H) > 180
    row_of = {int(x): i for i, x in enumerate(p["dates"])}
    rows = {q["D"]: q for q in mod._trades(p, syn["index"], syn["open"], syn["close"])}
    for h in H.itertuples():
        t = got[h.Dk]
        e, x = idx[t[0]], idx[t[1]]
        assert _ymd(e) == h.Dm1k and _ymd(x) == h.Dk                     # D-1 -> D, one night
        assert (x - e.normalize()).days == 1                             # a weeknight: one calendar day apart
        assert e.hour * 60 + e.minute == p["last_min"][row_of[h.Dm1k]]   # D-1's last bar (15:25 on 2019-08-12)
        assert (x.hour, x.minute) == (9, 30)                             # D's opening bar
        q = rows[h.Dk]
        assert q["px"] == h.px and q["shares"] == np.floor(100000.0 / h.px)
        scale = q["shares"] * q["px"] / 100000.0                          # the whole-share floor: the only difference
        assert abs(q["gross"] - h.gross * scale) < 1e-9 and abs(q["cost"] - h.cost * scale) < 1e-9, h.Dk
        assert t[3] == 1 and abs(t[2] - h.net * scale) < 1e-9, h.Dk
    assert _structure_ok(mod, p, syn, list(rows.values()))
    marks = mod.mark_open_trades(r["trades"], syn["open"], syn["high"], syn["low"], syn["close"],
                                 index=syn["index"])
    assert marks == [[(t[0], 0.0)] for t in r["trades"]]


def test_2019_master_slice_matches_the_harness_formula(sealed, master_2019):
    mod, p = sealed
    arr = master_2019
    from augur_engine import run_backtest
    idx = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    for nights in MODES:
        r = run_backtest(mod, arrays=arr, params={"nights": nights}, return_trades=True)
        got = {_ymd(idx[t[1]]): t for t in r["trades"] if idx[t[1]].year == 2019}
        H = _replica_2019(nights)
        assert sorted(got) == sorted(H.Dk.tolist()) and len(H) > 40, nights
        for h in H.itertuples():
            t = got[h.Dk]
            scale = np.floor(100000.0 / h.px) * h.px / 100000.0
            assert _ymd(idx[t[0]]) == h.Dm1k and abs(t[2] - h.net * scale) < 1e-9, (nights, h.Dk)
            assert (idx[t[1]].hour, idx[t[1]].minute) == (9, 30)
        assert _structure_ok(mod, p, arr, mod._trades(p, arr["index"], arr["open"], arr["close"], nights=nights))


def test_night_modes_split_on_the_calendar_gap_only(sealed, syn):
    mod, p = sealed
    rows = {m: mod._trades(p, syn["index"], syn["open"], syn["close"], nights=m) for m in MODES}
    assert {q["gap"] for q in rows["weeknights"]} == {1}
    assert min(q["gap"] for q in rows["weekend_only"]) == 3
    wk, we, ev = ({q["D"] for q in rows[m]} for m in MODES[:1] + MODES[2:] + MODES[1:2])
    assert not (wk & we) and (wk | we) <= ev
    assert {q["gap"] for q in rows["every_night"] if q["D"] not in (wk | we)} <= {2}   # mid-week holidays only
    for q in rows["every_night"]:
        d0, d1 = pd.Timestamp(str(q["entry_day"])), pd.Timestamp(str(q["D"]))
        assert (d1 - d0).days == q["gap"]


# ---------------------------------------------------------------------------------------------------- slice edges
def test_slice_edges_never_close_a_trade_early_or_open_it_late(sealed, syn):
    """The night 2019-06-06 (Thu) -> 2019-06-07 (Fri). A slice that ends on D-1's last bar, or starts at D's open or
    one bar into it, or loses D-1's last bar, takes no trade for that night; one that ends on D's 09:30 bar, or
    starts inside D-1, takes the same trade."""
    mod, p = sealed
    idx = pd.DatetimeIndex(syn["index"]).tz_localize(None)
    day = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy()
    d1, d = np.flatnonzero(day == 20190606), np.flatnonzero(day == 20190607)
    e, x = int(d1[-1]), int(d[0])

    def trade_on(a, b):
        rows = mod._trades(p, syn["index"][a:b], syn["open"][a:b], syn["close"][a:b])
        return [(q["e"] + a, q["x"] + a, q["net"]) for q in rows if q["D"] == 20190607]

    full = trade_on(0, len(idx))
    assert len(full) == 1 and full[0][0] == e and full[0][1] == x
    assert trade_on(0, x + 1) == full                              # through D's 09:30 bar
    assert trade_on(0, x) == []                                    # ends on D-1's last bar: never closed early
    assert trade_on(int(d1[0]) + 10, len(idx)) == full             # starts inside D-1: the entry bar is still there
    assert trade_on(e, len(idx)) == full                           # starts on the entry bar itself
    assert trade_on(x, len(idx)) == []                             # starts at D's open: D-1's close is gone
    assert trade_on(x + 1, len(idx)) == []                         # starts inside D: no entry, no 09:30 bar
    keep = np.r_[0:e, x:len(idx)]                                  # D-1 stops one bar short of its close
    rows = mod._trades(p, syn["index"][keep], syn["open"][keep], syn["close"][keep])
    assert [q for q in rows if q["D"] == 20190607] == []
    keep = np.r_[0:x, x + 1:len(idx)]                              # D has no 09:30 bar (it opens at 09:35)
    rows = mod._trades(p, syn["index"][keep], syn["open"][keep], syn["close"][keep])
    assert [q for q in rows if q["D"] == 20190607] == []
    # every other night of the full run is untouched by a cut placed between two sessions
    a = trade_on(0, len(idx))
    left = mod._trades(p, syn["index"][:x], syn["open"][:x], syn["close"][:x])
    right = mod._trades(p, syn["index"][x:], syn["open"][x:], syn["close"][x:])
    base = mod._trades(p, syn["index"], syn["open"], syn["close"])
    assert len(left) + len(right) == len(base) - 1 and a == full   # one trade lost per slice edge, never more


# ---------------------------------------------------------------------------------------------------- look-ahead
def _scramble(p, arr, r, seed):
    """Copies of the panel and the bars with everything known only after trade r's entry print (D-1's close)
    replaced at random: the official open, close and raw close of D and of every later session, and every bar price
    after D-1's last bar. Factors 0.5 .. 0.9: every scrambled price moves down by 10 pct or more. The calendar
    (dates, gaps, bar minutes) is known in advance and stays."""
    rng = np.random.default_rng(seed)
    q = {k: np.array(p[k]) for k in ("dates", "open", "close", "raw", "first_min", "last_min", "gap")}
    i = r["row"]
    for k in ("open", "close", "raw"):
        q[k][i:] = q[k][i:] * rng.uniform(0.5, 0.9, len(q[k]) - i)
    a = dict(arr)
    e = r["e"]
    for k in ("open", "high", "low", "close"):
        v = np.array(arr[k], float)
        v[e + 1:] = v[e + 1:] * rng.uniform(0.5, 0.9, len(v) - e - 1)
        a[k] = v
    return q, a


def _check(mod, p, arr, prm, base, r, seed):
    """(entry side of every trade entered by r's entry bar unchanged and every trade closed by then byte-identical,
    trade r's net moved) after the scramble."""
    q, a = _scramble(p, arr, r, seed)
    got = mod._trades(mod._derive(q), a["index"], a["open"], a["close"], **prm)
    want = [tuple(b[k] for k in ENTRY_KEYS) for b in base if b["e"] <= r["e"]]
    have = [tuple(g[k] for k in ENTRY_KEYS) for g in got if g["e"] <= r["e"]]
    closed = ([b["net"] for b in base if b["x"] <= r["e"]] == [g["net"] for g in got if g["x"] <= r["e"]])
    same = (g for g in got if g["e"] == r["e"] and g["x"] == r["x"])
    moved = next((g["net"] != r["net"] for g in same), False)
    return have == want and closed, moved


@pytest.mark.parametrize("nights", MODES)
def test_nothing_after_the_entry_print_moves_a_trade(sealed, syn, nights):
    mod, p = sealed
    prm = dict(_defaults(mod), nights=nights)
    base = mod._trades(p, syn["index"], syn["open"], syn["close"], **prm)
    assert len(base) > 80
    picks = base[3::(31 if nights != "weekend_only" else 9)]
    assert len(picks) >= 10
    results = [_check(mod, p, syn, prm, base, r, seed=16000 + k) for k, r in enumerate(picks)]
    assert all(ok for ok, _ in results), [r["D"] for r, (ok, _) in zip(picks, results) if not ok]
    assert all(mv for _, mv in results)                           # the scramble really reached each trade's P&L


def test_the_checks_catch_broken_variants(sealed, syn):
    """The checks above have teeth. Look-ahead scramble: shares from D's open, and a night skipped when D opens
    below D-1's close, each FAIL it. Structure check: a file that exits on the 09:35 bar FAILS it (and the good
    file passes both)."""
    good, p = sealed
    m1 = P.fresh_plugin()
    m1._entry_terms = lambda pp, i: (float(pp["close"][i - 1]), float(pp["open"][i]))
    m2 = P.fresh_plugin()
    rows2 = m2._night_rows
    m2._night_rows = lambda pp, nights: np.array([i for i in rows2(pp, nights) if pp["open"][i] >= pp["close"][i - 1]],
                                                 dtype=np.int64)
    for mod in (m1, m2):
        prm = _defaults(mod)
        base = mod._trades(p, syn["index"], syn["open"], syn["close"], **prm)
        assert len(base) > 80
        caught = [not _check(mod, p, syn, prm, base, r, seed=16050 + k)[0] for k, r in enumerate(base[3::31])]
        assert all(caught), caught
    m3 = P.fresh_plugin()
    m3._exit_bar = lambda starts, jD: int(starts[jD]) + 1
    late = m3._trades(p, syn["index"], syn["open"], syn["close"])
    assert len(late) > 80 and not _structure_ok(m3, p, syn, late)
    m4 = P.fresh_plugin()                                           # shares sized on a notional other than $100k
    assert not _structure_ok(m4, p, syn, m4._trades(p, syn["index"], syn["open"], syn["close"], notional=250000))
    base = good._trades(p, syn["index"], syn["open"], syn["close"])
    assert _structure_ok(good, p, syn, base)
    assert all(_check(good, p, syn, _defaults(good), base, r, seed=16090 + k)[0] for k, r in enumerate(base[5::47]))
