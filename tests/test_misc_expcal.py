"""MISC_EXPCAL_1_0 (opus hunt 58, cell 58c, expiry-calendar long on NQ): ONE config and no search space, the plugin
gate lets it through, the contract's synthetic 24-hour tape never opens the FOMC file, the FOMC file is pinned (wrong
or missing file raises; its CRLF form hashes to the harness's pin), the calendar gives the prereg's hand-checked days
and does not depend on the year range it is built for, a toy tape trades by hand arithmetic, and the four look-ahead
checks of the build brief:
  (a) truncation      - bars cut at day D: every trade that exits before D is identical; a cut inside a day = no trade;
  (b) future scramble - every price after a trade's exit bar (and, separately, every price after the 15:55 OPEN of
                        its day) replaced at random: the trade list up to and including that trade is unchanged;
  (c) calendar        - every price multiplied by random noise: trade dates, entry and exit bars unchanged;
  (d) intrabar        - the 15:55 bar's high / low / close and every bar strictly between entry and exit replaced
                        at random: every P&L unchanged (it reads two opens only);
and three broken variants are caught by them. (a)-(d) run on a synthetic exchange-calendar clock (2017-2019, always)
and on the real NQ 5m RTH db_noadj_rth master when it is on this machine (bars 2016-07-01 .. 2019-12-31 only).
The engine-path parity test reads bars only to 2025-06-30. Nothing after 2025-06-30 carries a real price here."""
import datetime as dt
import hashlib
import os
import sqlite3
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "augur_strategies", "MISC_EXPCAL_1_0.py")
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
TRADES = "C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S58/trades_58c.csv"
sys.path.insert(0, os.path.join(REPO, "tools"))

from augur_engine import session_calendar as SC  # noqa: E402

METRIC_KEYS = {"total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown", "avg_pnl", "wins", "losses"}
PX = ("open", "high", "low", "close")


def fresh_plugin():
    import importlib.util
    spec = importlib.util.spec_from_file_location("misc_expcal_1_0_test", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._CACHE.clear()
    return mod


def _clock_arrays(days, last_min, seed=58, first_min=570, base_px=7000.0):
    """An NQ-like 5m clock on the given dates: bars from first_min to each session's own last bar, random-walk
    prices."""
    rng = np.random.default_rng(seed)
    nb = (np.asarray(last_min, np.int64) - first_min) // 5 + 1
    base = pd.to_datetime(pd.Series([str(d) for d in days])).to_numpy()
    off = (np.concatenate([np.arange(k) for k in nb]) * 5 + first_min).astype("timedelta64[m]")
    idx = pd.DatetimeIndex(np.repeat(base, nb) + off).tz_localize("US/Eastern")
    n = len(idx)
    close = base_px + rng.normal(0, 4.0, n).cumsum()
    openp = close + rng.normal(0, 2.0, n)
    return {"open": openp, "high": np.maximum(openp, close) + 1.0, "low": np.minimum(openp, close) - 1.0,
            "close": close, "volume": np.full(n, 1000.0), "day_id": np.repeat(np.arange(len(days)), nb).astype("int64"),
            "index": idx, "meta": {"name": "SYN", "roll_mode": "none"}}


def _exchange_clock(d0, d1, seed=58):
    """Every CME RTH session d0 .. d1 from the published calendar: holiday short sessions and the scheduled early
    closes stop at 12:55, everything else at 15:55."""
    mod = fresh_plugin()
    days = SC.exchange_sessions(d0, d1)
    last = [775 if (SC.is_holiday_session(d) or mod._early_close(d)) else 955 for d in days]
    return _clock_arrays(days, last, seed=seed)


@pytest.fixture(scope="module")
def syn():
    return _exchange_clock("2017-01-03", "2019-12-31")


@pytest.fixture(scope="module")
def master():
    """The NQ 5m RTH db_noadj_rth master (the job's), 2016-07-01 .. 2019-12-31 only. A worktree has no registry or
    uploads of its own, so the row is read (read-only) from the shared checkout's registry."""
    return _master_arrays("2016-07-01", "2019-12-31")


def _master_arrays(date_from, date_to, source="db_noadj_rth"):
    assert date_to <= "2025-06-30"
    db = os.path.join(SHARED, "optimizer_history.db")
    if not os.path.exists(db):
        pytest.skip("master registry not on this machine")
    row = None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
        try:
            row = con.execute("SELECT id, filename, source, session, instrument, timeframe FROM csv_files "
                              "WHERE is_master=1 AND instrument='NQ' AND timeframe='5m' AND lower(session)='rth' "
                              "AND source=?", (source,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        row = None
    path = os.path.join(SHARED, "augur_uploads", row[1]) if row else None
    if path is None or not os.path.exists(path):
        pytest.skip("NQ 5m master not on this machine")
    from augur_engine.data import load_master_arrays
    m = dict(zip(("id", "filename", "source", "session", "instrument", "timeframe"), row))
    arr = load_master_arrays(dict(m, filename=path), date_from=date_from, date_to=date_to)
    arr["meta"] = m
    assert pd.DatetimeIndex(arr["index"]).max() < pd.Timestamp(date_to, tz="US/Eastern") + pd.Timedelta(days=1)
    return arr


def _good(mod):
    return lambda a: mod._trades(a["index"], a["open"])


def _key(r):
    return (r["e"], r["x"], r["D"], r["typ"], r["p_in"], r["p_out"], r["net"])


# ------------------------------------------------------------------------------------------------ the file itself
def test_one_config_no_search_space():
    mod = fresh_plugin()
    assert {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()} == {"cost_pts": 0.533, "point_value": 20}
    for k, v in mod.DEFAULT_PARAMS.items():
        assert v["min"] == v["max"] == v["default"] == v["hard_min"] == v["hard_max"], k
    from augur_engine.auto import _auto_space_from_params
    size = 1
    for spec in _auto_space_from_params(mod.DEFAULT_PARAMS).values():
        size *= len(spec[1]) if spec[0] == "cat" else int(round((spec[2] - spec[1]) / spec[3])) + 1
    assert size == 1                                              # a SINGLE: the runner refuses Auto-Validate on it
    assert list(mod.PARAM_GRID_PRESETS.values()) == [{"cost_pts": [0.533], "point_value": [20]}]
    assert mod.PNL_UNITS == "usd" and mod.ROLL_SIGNAL == "difference"
    assert mod._AUGUR_MARKET == {"instrument": "NQ", "timeframe": "5m", "session": "rth", "source": "db_noadj_rth"}
    assert "_PINNED" not in os.path.basename(PLUGIN) and not hasattr(mod, "_AUGUR_PARENT")
    doc = mod.__doc__
    for must in ("FAIL", "83rd percentile", "P(lift) 0.68", "5 of 8 folds", "105 pct", "28.6 a year", "$5,499 a year",
                 "WEAK or a FAIL takes this leg"):
        assert must in doc, must


def test_plugin_gate_lets_it_through():
    from augur_engine import plugin_gate as G
    with open(PLUGIN, "rb") as f:
        src = G.lf_bytes(f.read()).decode("utf-8")
    assert G.MARKER_RX.search(src).group(1) == "claude-review"
    assert G.lookahead_check(src) == []
    G.gate_plugin(PLUGIN)                                         # raises PluginGateError on a refusal


def test_family_is_misc():
    import api.runner as R
    assert R.FirestoreQueue._family_of(None, "MISC_EXPCAL_1_0.py") == "MISC"


def test_contract_tape_and_eth_tape_take_no_trade_and_never_open_the_fomc_file():
    rng = np.random.default_rng(7)                                # tests/test_strategy_contract.py _make_arrays()
    n = 780
    close = 15000 + rng.normal(0, 1, n).cumsum()
    idx = pd.date_range("2026-03-02 09:30", periods=n, freq="5min", tz="US/Eastern")
    mod = fresh_plugin()
    r = mod.run_backtest(close, close + 1, close - 1, close, np.full(n, 1000.0),
                         np.repeat(np.arange(10), 78).astype("int64"), idx, return_trades=True)
    assert r is None and "fomc" not in mod._CACHE
    days = [d for d in SC.exchange_sessions("2019-03-01", "2019-03-29")]
    a = _clock_arrays(days, [1195] * len(days), first_min=240)    # 04:00 .. 19:55 ET: no session is RTH
    assert mod.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True) is None
    assert "fomc" not in mod._CACHE
    assert mod.run_backtest(a["open"], a["high"], a["low"], a["close"], return_trades=True) is None   # no index


def test_fomc_file_is_pinned(tmp_path):
    mod = fresh_plugin()
    with open(mod.FOMC_PATH, "rb") as f:
        lf = f.read().replace(b"\r\n", b"\n")
    assert hashlib.sha256(lf).hexdigest() == mod.FOMC_SHA256_LF
    assert hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest() == mod.FOMC_SHA256_CRLF        # the harness's pin
    assert mod.FOMC_SHA256_CRLF == "9cf8e527a141db26bf3330f5a9c78772421c97720ef133535ac73ae4e42b575f"
    days = mod._fomc()
    assert days[0] == dt.date(2010, 1, 27) and dt.date(2019, 3, 20) in days and len(days) == len(set(days)) > 100
    a = _exchange_clock("2019-03-01", "2019-03-29")
    bad = tmp_path / "fomc_dates.txt"
    bad.write_bytes(lf.replace(b"2019-03-20", b"2019-03-21"))     # one decision day moved
    m2 = fresh_plugin()
    m2.FOMC_PATH = str(bad)
    with pytest.raises(RuntimeError, match="not the pinned content"):
        m2.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True)
    m3 = fresh_plugin()
    m3.FOMC_PATH = str(tmp_path / "nope.txt")
    with pytest.raises(RuntimeError, match="missing"):
        m3.run_backtest(a["open"], a["high"], a["low"], a["close"], index=a["index"], return_trades=True)


def test_calendar_hand_checks_and_range_independence():
    mod = fresh_plugin()
    cal = mod._calendar(2010, 2025)
    kind = cal["kind"]
    assert "OPEXTUE" in kind[20190312]                            # third Friday 2019-03-15, its Tuesday
    assert "VIXEVE" in kind[20190319] and 20190319 in cal["fomcx"]     # settle Wed 03-20; also the FOMC eve
    assert "VIXEVE" in kind[20240617] and "VIXEVE" not in kind[20240618]  # Juneteenth 2024-06-19: settle 06-18, eve 06-17
    assert kind[20181204] == ["PREHOL"] and kind[20181206] == ["POSTHOL"]          # the 2018-12-05 mourning closure
    assert kind[20250108] == ["PREHOL"] and kind[20250110] == ["POSTHOL"]          # 2025-01-09
    assert "PREHOL" not in kind.get(20121026, []) and "POSTHOL" not in kind.get(20121031, [])   # Sandy: neither
    assert "PREHOL" in kind[20190118] and "POSTHOL" in kind[20190122]              # MLK 2019-01-21
    assert 20190122 in cal["pm"] and 20190118 in cal["full"]
    assert "PREHOL" in kind[20191224] and "POSTHOL" in kind[20191226]              # Christmas 2019 (12-24: half day)
    assert 20190320 in cal["fomcx"] and 20190319 in cal["fomcx"] and 20190321 not in cal["fomcx"]
    assert not (cal["full"] & cal["pm"])
    for y in (2012, 2019, 2024):                                  # membership never depends on the range built
        one = mod._calendar(y, y)
        lo, hi = y * 10000, (y + 1) * 10000
        for k in ("full", "pm", "fomcx"):
            assert {d for d in one[k] if lo < d < hi} == {d for d in cal[k] if lo < d < hi}, (y, k)
    assert cal["fomc_last"] == 20271208


def test_toy_tape_hand_arithmetic():
    """2019-01-15 .. 2019-01-23: Tue 01-15 = OPEXTUE (third Friday 01-18) and the VIX eve -> FULL; Fri 01-18 = PREHOL
    (MLK 01-21) -> FULL; Mon 01-21 = holiday short session -> nothing; Tue 01-22 = POSTHOL -> PM; the rest nothing."""
    mod = fresh_plugin()
    days = SC.exchange_sessions("2019-01-14", "2019-01-23")
    a = _clock_arrays(days, [775 if SC.is_holiday_session(d) else 955 for d in days])
    loc = a["index"].tz_localize(None)
    o = a["open"]

    def bar(day, hm):
        return int(np.flatnonzero(loc == pd.Timestamp("%s %s" % (day, hm)))[0])

    from augur_engine import run_backtest
    res = run_backtest(mod, arrays=a, params={}, return_trades=True)
    want = [(bar("2019-01-15", "09:30"), bar("2019-01-15", "15:55")),
            (bar("2019-01-18", "09:30"), bar("2019-01-18", "15:55")),
            (bar("2019-01-22", "14:00"), bar("2019-01-22", "15:55"))]
    assert [(t[0], t[1]) for t in res["trades"]] == want
    for t, (e, x) in zip(res["trades"], want):
        assert t[2] == ((o[x] - o[e]) - 0.533) * 20 and t[3] == 1 and t[4] == o[e] and t[5] == o[x]
    assert METRIC_KEYS <= set(res) and res["num_trades"] == 3
    assert res["total_pnl"] == pytest.approx(sum(t[2] for t in res["trades"]))
    assert mod.mark_open_trades(res["trades"], a["open"], a["high"], a["low"], a["close"]) == [[], [], []]
    # a FULL day with no 14:00 bar is not eligible (the harness's test), nor is a day whose last bar is not 15:55
    k = ~((loc.normalize() == pd.Timestamp("2019-01-15")) & (loc.hour == 14) & (loc.minute == 0))
    b = {kk: (v[k] if hasattr(v, "__len__") and not isinstance(v, dict) and len(v) == len(k) else v)
         for kk, v in a.items()}
    assert [r["D"] for r in mod._trades(b["index"], b["open"])] == [20190118, 20190122]
    k = ~((loc.normalize() == pd.Timestamp("2019-01-18")) & (loc.hour == 15) & (loc.minute == 55))
    b = {kk: (v[k] if hasattr(v, "__len__") and not isinstance(v, dict) and len(v) == len(k) else v)
         for kk, v in a.items()}
    assert [r["D"] for r in mod._trades(b["index"], b["open"])] == [20190115, 20190122]


# ------------------------------------------------------------------------------------------------ look-ahead checks
def _cut(arr, n):
    return {k: (v[:n] if hasattr(v, "__len__") and not isinstance(v, dict) and len(v) == len(arr["close"]) else v)
            for k, v in arr.items()}


def check_truncation(fn, arr, n_cuts=24, seed=1):
    """(a) For cuts at session starts and inside sessions: the trades on the cut bars == the full run's trades that
    exit before the cut, field for field."""
    base = fn(arr)
    rng = np.random.default_rng(seed)
    exits = np.array([r["x"] for r in base])
    entries = np.array([r["e"] for r in base])
    cuts = set(int(c) for c in rng.integers(100, len(arr["close"]) - 1, n_cuts))
    for i in rng.choice(len(base), min(n_cuts, len(base)), replace=False):
        r = base[int(i)]
        cuts |= {r["e"], r["e"] + 1, r["x"], r["x"] + 1, r["x"] + 2, r["e"] - 1}   # around each picked trade
    bad = []
    for c in sorted(cuts):
        if c < 2 or c > len(arr["close"]):
            continue
        got = fn(_cut(arr, c))
        want = [b for b in base if b["x"] < c]
        if [_key(g) for g in got] != [_key(w) for w in want]:
            bad.append(c)
    open_at_cut = int(sum(((entries < c) & (exits >= c)).any() for c in cuts))
    return bad, len(cuts), open_at_cut


def check_future_scramble(fn, arr, picks, seed=2, from_exit_open=False):
    """(b) Replace at random every price after trade r's exit bar (from_exit_open: every price after the 15:55 OPEN
    of r's day - the exit bar keeps its open only). Trades up to and including r must be identical."""
    base = fn(arr)
    bad = []
    for k, i in enumerate(picks):
        r = base[i]
        rng = np.random.default_rng(seed + k)
        a = dict(arr)
        for c in PX:
            v = np.array(arr[c], float)
            s = r["x"] if (from_exit_open and c != "open") else r["x"] + 1
            v[s:] = v[s:] * rng.uniform(0.5, 1.5, len(v) - s)
            a[c] = v
        got = fn(a)
        if [_key(g) for g in got if g["x"] <= r["x"]] != [_key(b) for b in base if b["x"] <= r["x"]]:
            bad.append(r["D"])
        elif [(g["e"], g["x"], g["D"], g["typ"]) for g in got] != [(b["e"], b["x"], b["D"], b["typ"]) for b in base]:
            bad.append(-r["D"])                                   # a LATER trade's day or bars moved with future prices
    return bad


def check_price_independent_calendar(fn, arr, seeds=(3, 4, 5)):
    """(c) Multiply every price by random noise: the trade dates and the entry / exit bars must not move."""
    base = [(b["e"], b["x"], b["D"], b["typ"]) for b in fn(arr)]
    bad = []
    for s in seeds:
        rng = np.random.default_rng(s)
        a = dict(arr)
        for c in PX:
            a[c] = np.array(arr[c], float) * rng.uniform(0.2, 5.0, len(arr[c]))
        if [(g["e"], g["x"], g["D"], g["typ"]) for g in fn(a)] != base:
            bad.append(s)
    return bad, len(base)


def check_intrabar(fn, arr, seed=6):
    """(d) Replace at random the high / low / close of every entry and exit bar and all four prices of every bar
    strictly between a trade's entry and exit (their existence stays): every trade is identical, P&L included."""
    base = fn(arr)
    rng = np.random.default_rng(seed)
    a = {c: np.array(arr[c], float) for c in PX}
    touched = 0
    for b in base:
        for c in ("high", "low", "close"):
            a[c][b["e"]] *= rng.uniform(0.5, 1.5)
            a[c][b["x"]] *= rng.uniform(0.5, 1.5)
        s, n = b["e"] + 1, b["x"] - b["e"] - 1
        for c in PX:
            a[c][s:s + n] = a[c][s:s + n] * rng.uniform(0.5, 1.5, n)
        touched += 6 + 4 * n
    got = fn(dict(arr, **a))
    return [_key(g) for g in got] == [_key(b) for b in base], touched


def _run_all(fn, arr, min_trades):
    base = fn(arr)
    assert len(base) >= min_trades
    picks = list(range(2, len(base), max(1, len(base) // 12)))
    out = {}
    out["a_bad"], out["a_cuts"], out["a_open"] = check_truncation(fn, arr)
    out["b_exit_bad"] = check_future_scramble(fn, arr, picks, seed=200)
    out["b_open_bad"] = check_future_scramble(fn, arr, picks, seed=300, from_exit_open=True)
    out["c_bad"], out["c_n"] = check_price_independent_calendar(fn, arr)
    out["d_ok"], out["d_touched"] = check_intrabar(fn, arr)
    out["n"] = len(base)
    out["picks"] = len(picks)
    return out


def _assert_clean(o):
    assert o["a_bad"] == [] and o["a_cuts"] > 40 and o["a_open"] > 0, o
    assert o["b_exit_bad"] == [] and o["b_open_bad"] == [] and o["picks"] >= 10, o
    assert o["c_bad"] == [], o
    assert o["d_ok"] and o["d_touched"] > 1000, o


def test_lookahead_checks_on_the_synthetic_exchange_clock(syn):
    mod = fresh_plugin()
    _assert_clean(_run_all(_good(mod), syn, min_trades=70))


def test_lookahead_checks_on_the_real_master(master):
    mod = fresh_plugin()
    o = _run_all(_good(mod), master, min_trades=90)
    _assert_clean(o)
    print("REAL MASTER 2016-07..2019-12:", o)


def test_run_backtest_matches_trades_and_scrambles_through_the_public_entry(syn):
    """The same four facts through run_backtest itself (the trade tuples), not only the _trades helper."""
    mod = fresh_plugin()

    def fn(a):
        r = mod.run_backtest(a["open"], a["high"], a["low"], a["close"], a.get("volume"), a.get("day_id"),
                             a["index"], return_trades=True)
        loc = pd.DatetimeIndex(a["index"]).tz_localize(None)
        return [{"e": t[0], "x": t[1], "D": int(loc[t[1]].strftime("%Y%m%d")),
                 "typ": "F" if loc[t[0]].hour == 9 else "P", "p_in": t[4], "p_out": t[5], "net": t[2]}
                for t in (r or {}).get("trades", [])]
    assert [_key(x) for x in fn(syn)] == [_key(x) for x in _good(mod)(syn)]
    _assert_clean(_run_all(fn, syn, min_trades=70))


def test_the_checks_catch_broken_variants(syn):
    """Teeth. A: a day is dropped when its 15:55 open is below its entry open (the exit print picks the days) ->
    caught by (c). B: the exit is the 15:55 bar's CLOSE -> caught by (d) and by (b, from the 15:55 open). C: a day is
    dropped when the NEXT session opens lower -> caught by (a) and (b)."""
    mod = fresh_plugin()
    good = _good(mod)

    def broken_a(a):
        return [r for r in good(a) if r["p_out"] >= r["p_in"]]

    def broken_b(a):
        out = []
        for r in good(a):
            r = dict(r, p_out=float(a["close"][r["x"]]))
            r["net"] = ((r["p_out"] - r["p_in"]) - 0.533) * 20
            out.append(r)
        return out

    def broken_c(a):
        o = a["open"]
        return [r for r in good(a) if r["x"] + 1 < len(o) and o[r["x"] + 1] >= o[r["x"]]]

    assert check_price_independent_calendar(broken_a, syn)[0] != []
    assert not check_intrabar(broken_b, syn)[0]
    assert check_future_scramble(broken_b, syn, list(range(2, 60, 5)), seed=300, from_exit_open=True) != []
    assert check_truncation(broken_c, syn)[0] != []
    assert check_future_scramble(broken_c, syn, list(range(2, len(broken_c(syn)), 4)), seed=200) != []
    assert check_price_independent_calendar(good, syn)[0] == [] and check_intrabar(good, syn)[0]


# ------------------------------------------------------------------------------------------------ parity
def test_engine_path_parity_with_the_harness_trade_file():
    """The plugin through the engine's loader and run_backtest on the job's master, bars 2016-07-01 .. 2025-06-30:
    the harness's 257 WF trades, same dates, same type, same dollars."""
    if not os.path.exists(TRADES):
        pytest.skip("harness trade file not on this machine")
    arr = _master_arrays("2016-07-01", "2025-06-30")
    import augur_engine as ae
    mod = ae.load_strategy(PLUGIN)
    res = ae.run_backtest(mod, params={}, arrays=arr, return_trades=True)
    loc = pd.DatetimeIndex(arr["index"]).tz_convert("US/Eastern").tz_localize(None)
    ref = pd.read_csv(TRADES, parse_dates=["d"], float_precision="round_trip")   # the default parser is 1 ulp off
    ref = ref[(ref.d >= "2016-07-01") & (ref.d <= "2025-06-30")].reset_index(drop=True)
    tr = res["trades"]
    assert len(tr) == len(ref) == 257
    assert [loc[t[1]].normalize() for t in tr] == list(ref.d)
    assert ["F" if loc[t[0]].hour == 9 else "P" for t in tr] == list(ref.typ)
    assert all(loc[t[1]].hour == 15 and loc[t[1]].minute == 55 for t in tr)
    d = np.abs(np.array([t[2] for t in tr]) - ref.usd.values)
    assert float(d.max()) == 0.0
    assert round(float(sum(t[2] for t in tr)), 2) == 49470.38
    assert len(tr) / 9.0 >= 20
