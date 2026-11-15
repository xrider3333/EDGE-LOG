"""Parity: augur_strategies/MISC_EVENTCRUSH_1_0.py at its defaults vs the opus-hunt S94 harness, cell 94a.

The harness (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S94) saved
  trades_94a.csv  every 94a trade (P, E1, Ek, k, days, C_P, C_Ek, raw_P, shares, shares_exit, gross, cross, borrow,
                  cost, net ...), P >= 2016-07-01 and Ek <= 2025-06-30; trades_94b.csv / trades_94c.csv the same for
                  the beta-hedged cell and the FOMC + payrolls cell
  series.pkl      {'94a', '94b', '94b-lit', '94c'} -> net $ a session 2016-07-01 .. 2025-06-30, zero days included
Checks, all on 2016-07-01 .. 2025-06-30 only:
  1. TRADES: the plugin's own trades (its _trades) at the defaults vs trades_94a.csv, matched on (P, Ek): identical
     entry / exit closes, shares, gross, cost and net; total net plugin vs hunt.
  2. ENGINE: the plugin through augur_engine.run_backtest on the VIXY 5m RTH alpaca_split_rth master (loaded by the
     engine's own load_master_arrays from the shared checkout's registry), one trade per block booked on its exit
     day, vs series '94a' zero-filled over every session: days matched, max abs diff, daily correlation.
  3. The prereg's other cells through the plugin's switches: hedge ON vs 94b, events FOMC+EMP vs 94c (trades + series).
THE SEAL: the plugin's panel runs to 2026-06-30; this tool hands the plugin a copy cut at 2025-06-30 before anything
is computed, and loads the master only to 2025-06-30. No return / PnL after 2025-06-30 is computed or printed.
    python tools/misc_eventcrush_parity.py
"""
import importlib.util
import os
import pickle
import sqlite3
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S94/"
LO, HI = 20160701, 20250630
SEAL_DAY = "2025-06-30"
PANEL_KEYS = ("dates", "vixy_raw", "vixy_split", "spy_raw", "spy_split", "spy5")
CELLS = {"94a": {}, "94b": {"hedge": True}, "94c": {"events": "FOMC+EMP"}}


def load_plugin_sealed(seal=HI):
    """Import the plugin from this checkout and give it the panel cut at `seal` (nothing later is ever used)."""
    spec = importlib.util.spec_from_file_location("misc_eventcrush_1_0_parity",
                                                  os.path.join(REPO, "augur_strategies", "MISC_EVENTCRUSH_1_0.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = mod._panel()
    if p is None:
        return mod, None
    k = p["dates"] <= seal
    mod._CACHE.clear()
    mod._CACHE["panel"] = mod._derive({key: p[key][k] for key in PANEL_KEYS})
    return mod, mod._CACHE["panel"]


def vixy_master_row():
    """The VIXY 5m RTH alpaca_split_rth master row of the shared checkout's registry, read-only (None if absent)."""
    db = os.path.join(SHARED, "optimizer_history.db")
    if not os.path.exists(db):
        return None
    con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
    try:
        cur = con.execute("SELECT * FROM csv_files WHERE is_master=1 AND instrument='VIXY' AND timeframe='5m' "
                          "AND lower(session)='rth' AND source='alpaca_split_rth'")
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return rows[0] if rows else None


def load_vixy(date_from="2016-01-01", date_to=SEAL_DAY):
    """The VIXY master's bars in [date_from, date_to] (ET dates), parsed like augur_engine.data.load_master_arrays.
    date_to is capped at the seal. None when the master is not on this machine."""
    date_to = min(str(date_to), SEAL_DAY)
    m = vixy_master_row()
    if m is None:
        return None
    path = os.path.join(SHARED, "augur_uploads", m["filename"])
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df.index = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df[(df.index >= pd.Timestamp(date_from, tz="US/Eastern"))
            & (df.index < pd.Timestamp(date_to, tz="US/Eastern") + pd.Timedelta(days=1))]
    return {"open": df["open"].values.astype(float), "high": df["high"].values.astype(float),
            "low": df["low"].values.astype(float), "close": df["close"].values.astype(float),
            "volume": df["volume"].values.astype(float),
            "day_id": pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64"), "index": df.index,
            "meta": {"name": m.get("name"), "roll_mode": "none"}}


def plugin_trades(mod, p, arr, **kw):
    prm = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    prm.update(kw)
    T = pd.DataFrame(mod._trades(p, arr["index"], arr["close"], **prm))
    if len(T):
        T["P"] = pd.to_datetime(T.P.astype(str))
        T["Ek"] = pd.to_datetime(T.X.astype(str))
    return T


def hunt_trades(cell):
    H = pd.read_csv(HUNT + "trades_%s.csv" % cell, parse_dates=["P", "E1", "Ek"])
    return H[(H.P >= pd.Timestamp(str(LO))) & (H.Ek <= pd.Timestamp(str(HI)))]


def compare_trades(T, H, label):
    T = T[(T.P >= pd.Timestamp(str(LO))) & (T.Ek <= pd.Timestamp(str(HI)))]
    J = T.merge(H, on=["P", "Ek"], how="outer", suffixes=("_p", "_h"), indicator=True)
    both = J[J._merge == "both"]
    same = (np.isclose(both.c0, both.C_P, rtol=1e-12, atol=0) & np.isclose(both.c1, both.C_Ek, rtol=1e-12, atol=0)
            & ((both.shares_p - both.shares_h).abs() < 1e-9)
            & ((both.shares_exit_p - both.shares_exit_h).abs() < 1e-9)
            & ((both.net_p - both.net_h).abs() < 1e-6) & ((both.cost_p - both.cost_h).abs() < 1e-6))
    tp, th = float(T.net.sum()), float(H.net.sum())
    print("%s TRADES 2016-07-01..2025-06-30: plugin %d | hunt %d | matched (P, Ek) %d | only plugin %d | only hunt %d"
          " | identical prices/shares/cost/net %d (%.2f%% of hunt) | max |net diff| $%.2e | net plugin $%.2f vs hunt"
          " $%.2f (%+.6f%%)" % (label, len(T), len(H), len(both), (J._merge == "left_only").sum(),
                                (J._merge == "right_only").sum(), same.sum(), 100.0 * same.sum() / max(1, len(H)),
                                (both.net_p - both.net_h).abs().max() if len(both) else float("nan"), tp, th,
                                100.0 * (tp / th - 1) if th else float("nan")))
    bad = J[(J._merge != "both") | ~J.index.isin(both.index[same])]
    if len(bad):
        print("  mismatches (first 12):")
        print(bad[["P", "Ek", "_merge", "c0", "C_P", "c1", "C_Ek", "net_p", "net_h"]].head(12).to_string())
    return len(bad) == 0 and same.sum() == len(H) == len(T)


def compare_series(got, want, label):
    """got: {exit day: net} from the engine; want: the hunt's zero-filled daily series."""
    s = pd.Series(0.0, index=want.index)
    g = pd.Series(got)
    g = g[(g.index >= want.index[0]) & (g.index <= want.index[-1])]
    extra = g.index.difference(want.index)
    s.loc[g.index.intersection(want.index)] = g.loc[g.index.intersection(want.index)].values
    d = (s - want).abs()
    nz = want != 0
    corr = float(np.corrcoef(s.values, want.values)[0, 1])
    print("%s ENGINE (VIXY 5m master) 2016-07-01..2025-06-30: sessions %d | trade days plugin %d, hunt %d | days within"
          " $0.01 %d of %d (%.2f%%) | max abs diff $%.2e | daily corr %.6f | total plugin $%.2f vs hunt $%.2f"
          % (label, len(want), int((s != 0).sum()), int(nz.sum()), int((d < 0.01).sum()), len(want),
             100.0 * (d < 0.01).mean(), float(d.max()), corr, float(s.sum()), float(want.sum())))
    if len(extra):
        print("  engine trade days outside the hunt's session list:", [str(x.date()) for x in extra[:12]])
    if (d >= 0.01).any():
        print("  days off by >= $0.01 (first 12):", [(str(k.date()), round(float(s[k]), 2), round(float(want[k]), 2))
                                                    for k in d.index[d >= 0.01][:12]])
    return len(extra) == 0 and bool((d < 0.01).all())


def main():
    mod, p = load_plugin_sealed()
    if p is None:
        sys.exit("no panel on this machine")
    arr = load_vixy()
    if arr is None:
        sys.exit("no VIXY master on this machine")
    series = pickle.load(open(HUNT + "series.pkl", "rb"))
    ok = True
    # ---- 1. trades, every cell
    for cell, kw in CELLS.items():
        ok &= compare_trades(plugin_trades(mod, p, arr, **kw), hunt_trades(cell), cell)
    # ---- 2. engine, one trade per block
    os.chdir(SHARED)                                   # the master registry lives in the shared checkout
    sys.path.insert(0, SHARED)
    from augur_engine import data as D
    from augur_engine import run_backtest
    m = D.find_master("VIXY", "5m", "rth", "alpaca_split_rth")
    earr = D.load_master_arrays(m, date_from="2016-01-01", date_to=SEAL_DAY)
    idx = pd.DatetimeIndex(earr["index"]).tz_convert("US/Eastern").tz_localize(None)
    assert idx.max() < pd.Timestamp(SEAL_DAY) + pd.Timedelta(days=1)
    for cell, kw in CELLS.items():
        r = run_backtest(mod, params=dict(kw), arrays=earr, return_trades=True)
        got = {}
        for t in r["trades"]:
            got[idx[t[1]].normalize()] = got.get(idx[t[1]].normalize(), 0.0) + t[2]
        ok &= compare_series(got, series[cell], cell)
    print("PARITY", "PASS" if ok else "GAP (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
