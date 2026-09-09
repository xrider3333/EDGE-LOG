"""Contract tests for the ROUND-25 ETF book plumbing (tools/build_etf_masters.py +
augur_strategies/ETFDIP_*).

Two things can silently break this family and both are cheap to pin:

1. THE DAILY MASTER FORMAT. A daily master is just one row per trading day stamped 09:30
   ET, registered as timeframe "1d" / session "rth" / source "yahoo_adj". If find_master
   stops resolving that shape, or load_master_arrays stops giving it one day_id per bar,
   every ETF leg silently runs on the wrong aggregation. No real data, no network: a
   synthetic 5-day master through the real find_master + load_master_arrays.

2. THE PLUGINS ARE THE r25 RULE. tools/etf_book_parity.py proves this against real bars,
   but it needs the masters and the network. This test proves the same thing offline on a
   synthetic random walk by running r25_weak_edge_book's OWN `run_cell` beside each
   plugin and demanding identical trade lists to the cent.
"""
import importlib.util
import os
import sqlite3

import numpy as np
import pandas as pd
import pytest

import augur_engine.data as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT = os.path.join(ROOT, "augur_strategies")


def _load(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


# ── 1. daily master format round-trips through the registry ──────────────────────────
def test_daily_master_round_trip(tmp_path, monkeypatch):
    days = pd.date_range("2020-01-02", periods=5, freq="B")
    stamps = (days + pd.Timedelta(hours=9, minutes=30)).tz_localize("US/Eastern")
    df = pd.DataFrame({
        # POSIX seconds whatever the index resolution. pandas 3 builds this index in
        # microseconds, so astype("int64") // 10**9 gave 1970-01-19 and put all five bars
        # on one day - CI (unpinned pandas) was red from 2026-09-08 until this line.
        "time": [int(t.timestamp()) for t in stamps],
        "open": [10.0, 11, 12, 13, 14], "high": [10.5, 11.5, 12.5, 13.5, 14.5],
        "low": [9.5, 10.5, 11.5, 12.5, 13.5], "close": [10.2, 11.2, 12.2, 13.2, 14.2],
        "volume": [100, 200, 300, 400, 500],
    })
    df.to_csv(tmp_path / "master_test1d.csv", index=False)

    db = str(tmp_path / "reg.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE csv_files (id INTEGER PRIMARY KEY, name TEXT, filename TEXT,"
                 " instrument TEXT, rows INTEGER, date_from TEXT, date_to TEXT,"
                 " created_at TEXT, timeframe TEXT, is_master INTEGER, source TEXT,"
                 " provenance TEXT, session TEXT)")
    conn.execute("INSERT INTO csv_files (name, filename, instrument, rows, timeframe,"
                 " is_master, source, session) VALUES (?,?,?,?,?,?,?,?)",
                 ("ZZZ 1d (Yahoo total-return)", "master_test1d.csv", "ZZZ", 5,
                  "1d", 1, "yahoo_adj", "rth"))
    conn.commit(); conn.close()
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    monkeypatch.setattr(D, "DB_PATH", db)

    m = D.find_master("ZZZ", "1d", "rth", "yahoo_adj")
    assert m is not None and m["filename"] == "master_test1d.csv"
    assert D.find_master("ZZZ", "5m", "rth", "yahoo_adj") is None      # timeframe is honoured

    a = D.load_master_arrays(m)
    assert a["day_id"].tolist() == [0, 1, 2, 3, 4]                     # one bar per day
    assert [t.hour for t in a["index"]] == [9] * 5                     # 09:30 ET survives UTC
    assert [t.minute for t in a["index"]] == [30] * 5
    assert a["close"][-1] == pytest.approx(14.2)
    assert a["volume"][0] == 100.0
    sliced = D.load_master_arrays(m, date_from="2020-01-06", date_to="2020-01-07")
    assert sliced["day_id"].tolist() == [0, 1]                         # re-factorized 0-based


# ── 2. each plugin IS r25's rule ─────────────────────────────────────────────────────
@pytest.mark.parametrize("cell,fname,extra", [
    ("DBL7L", "ETFDIP_DBL7_1_0.py", {}),
    ("RSI2L", "ETFDIP_RSI2_1_0.py", {"allow_shorts": False}),
    ("RSI2B", "ETFDIP_RSI2_1_0.py", {"allow_shorts": True}),
    ("PB20L", "ETFDIP_PB20_1_0.py", {}),
])
def test_plugin_matches_r25_rule(cell, fname, extra):
    r25 = _load(os.path.join(ROOT, "tools", "r25_weak_edge_book.py"), "r25_for_test")
    plug = _load(os.path.join(STRAT, fname), fname[:-3])

    rng = np.random.default_rng(7)
    n = 900
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.011, n)))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    dates = [d.date() for d in pd.date_range("2015-01-01", periods=n, freq="B")]

    ref = r25.run_cell(open_, high, low, close, dates, cell,
                       shares_fn=lambda de: r25.NOTIONAL / open_[de],
                       cost_fn=lambda de, dx: r25.ETF_COST / (r25.NOTIONAL / open_[de]))
    res = plug.run_backtest(open_, high, low, close, day_id=np.arange(n),
                            return_trades=True, **extra)
    got = [(dates[int(t[1])], float(t[2])) for t in (res or {}).get("trades", [])]

    assert len(ref) > 5, "synthetic tape produced too few trades to be a real test"
    assert [z[0] for z in ref] == [z[0] for z in got]
    assert [round(z[1], 2) for z in ref] == [round(z[1], 2) for z in got]
